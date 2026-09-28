"""P00c / EXP-09: game-independent checks for the edge-look variants.

Vanilla-dependent checks (namespaces, anchor uniqueness) run only when the game
install is found via $HOI4_GAME_DIR or .claude/settings.local.json; otherwise skipped.
No vanilla text is stored here: the game files are read at test time only.
"""
import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
EXP_DIR = REPO / "assets" / "gfx" / "FX" / "experiments" / "EXP-09"
DEFINES_DIR = REPO / "assets" / "common" / "defines" / "experiments" / "EXP-09"
MANIFEST = EXP_DIR / "variants.json"

sys.path.insert(0, str(REPO / ".claude" / "skills" / "hoi4-map-modding" / "scripts"))
import ee_project  # noqa: E402

CANVAS = ee_project.Canvas(5120, 2304, lon0=10.9, lat_min=-60.0, lat_max=90.0)

# Both roots reach the same tables: vanilla 00_graphics.lua ends with
# `for k,v in pairs( NDefines_Graphics ) do NDefines[k] = v end` (table references are copied).
ROOTS = {"NDefines_Graphics", "NDefines"}
# Lowest outside-map distance that still lets the camera reach the 90N pole line / 60S cut (README "Tuning").
OUTSIDE_FLOOR = float(math.ceil(CANVAS.margin))
# (namespace, key) -> (min, max) allowed value. Only keys under test in EXP-09.
WHITELIST = {
    ("NGraphics", "CAMERA_OUTSIDE_MAP_DISTANCE_TOP"): (OUTSIDE_FLOOR, 200.0),
    ("NGraphics", "CAMERA_OUTSIDE_MAP_DISTANCE_BOTTOM"): (OUTSIDE_FLOOR, 200.0),
    ("NFrontend", "CAMERA_MAX_HEIGHT"): (50.0, 3000.0),
}
ASSIGN_RE = re.compile(r"^(NDefines_Graphics|NDefines)\.([A-Za-z_]\w*)\.([A-Z_][A-Z0-9_]*)\s*=\s*(-?\d+(?:\.\d+)?)\s*$")
MODES = {"before", "after", "replace"}
NO_BEHAVIOUR = "none"  # helper-only patch files (definitions, no visible effect)
FLOAT = r"(-?\d+\.\d+)"


# ---------------------------------------------------------------- helpers
def game_dir():
    gd = os.environ.get("HOI4_GAME_DIR")
    if not gd:
        local = REPO / ".claude" / "settings.local.json"
        if not local.exists():  # worktrees keep the machine-local file only in the main checkout
            for parent in REPO.parents:
                cand = parent / ".claude" / "settings.local.json"
                if cand.exists():
                    local = cand
                    break
        if local.exists():
            gd = json.loads(local.read_text(encoding="utf-8")).get("env", {}).get("HOI4_GAME_DIR")
    if gd and (Path(gd) / "gfx" / "FX").is_dir():
        return Path(gd)
    return None


GAME = game_dir()
needs_game = pytest.mark.skipif(GAME is None, reason="HOI4 game dir not found (HOI4_GAME_DIR)")


def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def all_define_files():
    return sorted({p for v in manifest()["variants"] for p in v["defines"]})


def all_patch_files():
    return sorted({p for v in manifest()["variants"] for p in v["shader_patches"]})


def parse_lua(path):
    """Return [(root, ns, key, value)] for every statement; raise on anything else."""
    out = []
    for n, raw in enumerate(Path(path).read_text(encoding="ascii").splitlines(), 1):
        line = raw.split("--", 1)[0].strip()
        if not line:
            continue
        m = ASSIGN_RE.match(line)
        assert m, f"{path}:{n}: not a plain numeric define assignment: {raw!r}"
        out.append((m.group(1), m.group(2), m.group(3), float(m.group(4))))
    return out


def apply_patch(text, spec):
    """Reference implementation of the P00b patch step: anchors must be unique at apply time."""
    for i, p in enumerate(spec):
        count = text.count(p["anchor"])
        assert count == 1, f"patch {i}: anchor {p['anchor']!r} found {count} times"
        pos = text.index(p["anchor"])
        end = pos + len(p["anchor"])
        if p["mode"] == "before":
            text = text[:pos] + p["text"] + text[pos:]
        elif p["mode"] == "after":
            text = text[:end] + p["text"] + text[end:]
        else:
            text = text[:pos] + p["text"] + text[end:]
    return text


def vanilla_namespace_keys(path):
    """{namespace: set(keys)} for the top-level tables of a vanilla defines file (one table per column-0 'NXxx = {')."""
    ns, table = None, {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^(N[A-Za-z_]\w*)\s*=\s*\{", line)
        if m:
            ns = m.group(1)
            table.setdefault(ns, set())
            continue
        k = re.match(r"^\s+([A-Z_][A-Z0-9_]*)\s*=", line)
        if k and ns:
            table[ns].add(k.group(1))
    return table


# ---------------------------------------------------------------- manifest
def test_manifest_well_formed():
    m = manifest()
    variants = m["variants"]
    assert 3 <= len(variants) <= 5
    ids = [v["id"] for v in variants]
    assert len(set(ids)) == len(ids)
    assert ids[0] == "a"
    for v in variants:
        assert set(v) >= {"id", "label", "changes", "defines", "shader_patches"}
        assert isinstance(v["label"], str) and v["label"].strip()
        assert isinstance(v["changes"], str) and v["changes"].strip()
        assert isinstance(v["defines"], list) and isinstance(v["shader_patches"], list)
    assert variants[0]["defines"] == [] and variants[0]["shader_patches"] == []


def test_manifest_canvas_matches_projection():
    c = manifest()["canvas"]
    assert (c["width"], c["height"]) == (CANVAS.W, CANVAS.H)
    assert c["lon0"] == CANVAS.lon0 and c["lat_min"] == CANVAS.lat_min and c["lat_max"] == CANVAS.lat_max
    assert abs(c["margin_rows"] - CANVAS.margin) < 0.05


def test_manifest_references_exist_and_in_scope():
    for p in all_define_files():
        assert p.startswith("assets/common/defines/experiments/EXP-09/") and p.endswith(".lua"), p
        assert (REPO / p).is_file(), p
    for p in all_patch_files():
        assert p.startswith("assets/gfx/FX/experiments/EXP-09/") and p.endswith(".patch.json"), p
        assert (REPO / p).is_file(), p


def test_every_asset_is_used():
    used = {REPO / p for p in all_define_files() + all_patch_files()}
    on_disk = set(DEFINES_DIR.glob("*.lua")) | set(EXP_DIR.glob("*.patch.json"))
    assert on_disk == used


def file_behaviour(rel):
    """Behaviour id of a patch file: every entry must declare the same `behaviour`."""
    names = {p.get("behaviour") for p in load_spec(rel)}
    assert len(names) == 1 and None not in names, f"{rel}: entries must share one 'behaviour' field, got {names}"
    return names.pop()


def variant_behaviours(v):
    """One define file = one behaviour (one lever); one patch file = its declared behaviour ('none' = helpers)."""
    out = {f"define:{Path(p).name}" for p in v["defines"]}
    out |= {f"shader:{b}" for b in map(file_behaviour, v["shader_patches"]) if b != NO_BEHAVIOUR}
    return out


def test_each_variant_adds_one_behaviour():
    variants = manifest()["variants"]
    beh = [variant_behaviours(v) for v in variants]
    assert beh[0] == set()
    for i in range(1, len(variants)):
        assert any(beh[j] <= beh[i] and len(beh[i] - beh[j]) == 1 for j in range(i)), (variants[i]["id"], beh[i])
    assert len({frozenset(b) for b in beh}) == len(beh), "two variants show the same behaviours"


def test_patch_behaviours_unique_across_files():
    seen = {}
    for rel in all_patch_files():
        b = file_behaviour(rel)
        if b != NO_BEHAVIOUR:
            assert b not in seen, f"{rel} and {seen.get(b)} both declare {b}"
            seen[b] = rel


def test_no_vanilla_shader_files_committed():
    for p in (REPO / "assets" / "gfx").rglob("*"):
        if p.is_file():
            assert p.suffix.lower() in {".json", ".md"}, f"unexpected file (vanilla shader text?): {p}"


# ---------------------------------------------------------------- defines
@pytest.mark.parametrize("rel", all_define_files())
def test_lua_only_whitelisted_numeric_keys(rel):
    stmts = parse_lua(REPO / rel)
    assert stmts, rel
    seen = set()
    for root, ns, key, value in stmts:
        assert root in ROOTS, f"{rel}: unknown root {root}"
        assert (ns, key) in WHITELIST, f"{rel}: {root}.{ns}.{key} not whitelisted"
        assert (ns, key) not in seen, f"{rel}: {key} set twice"
        seen.add((ns, key))
        lo, hi = WHITELIST[(ns, key)]
        assert lo <= value <= hi and math.isfinite(value), f"{rel}: {key} = {value}"


@pytest.mark.parametrize("rel", all_define_files())
def test_lua_sorts_after_vanilla_and_has_reason_comments(rel):
    name = Path(rel).name
    assert name.startswith("zz_") and name > "01_career_profile.lua"
    lines = (REPO / rel).read_text(encoding="ascii").splitlines()
    for i, line in enumerate(lines):
        if ASSIGN_RE.match(line.split("--", 1)[0].strip() or "-"):
            assert i > 0 and lines[i - 1].lstrip().startswith("--"), f"{rel}:{i + 1}: no reason comment above"


def test_define_values_fit_canvas():
    vals = {key: v for rel in all_define_files() for _, _, key, v in parse_lua(REPO / rel)}
    for key in ("CAMERA_OUTSIDE_MAP_DISTANCE_TOP", "CAMERA_OUTSIDE_MAP_DISTANCE_BOTTOM"):
        # the camera must still reach the pole line / 60S cut, i.e. at least the off-globe margin.
        # Same floor as the README tuning rule (15 = ceil(14.3)).
        assert vals[key] >= OUTSIDE_FLOOR == 15.0, key
    assert vals["CAMERA_MAX_HEIGHT"] < 3000.0


@needs_game
def test_lua_namespaces_match_vanilla():
    table = vanilla_namespace_keys(GAME / "common" / "defines" / "00_graphics.lua")
    for rel in all_define_files():
        for root, ns, key, _ in parse_lua(REPO / rel):
            assert root in ROOTS
            assert key in table.get(ns, set()), f"{rel}: {key} is not in vanilla {root}.{ns}"
            others = [n for n, keys in table.items() if key in keys and n != ns]
            assert not others, f"{rel}: {key} also in {others}; check namespace"


# ---------------------------------------------------------------- shader patch specs
def load_spec(rel):
    spec = json.loads((REPO / rel).read_text(encoding="utf-8"))
    assert isinstance(spec, list) and spec
    return spec


@pytest.mark.parametrize("rel", all_patch_files())
def test_patch_spec_well_formed(rel):
    spec = load_spec(rel)
    anchors = [p["anchor"] for r in all_patch_files() for p in load_spec(r)]  # all files: patches get combined
    file_behaviour(rel)  # one declared behaviour per file
    for p in spec:
        assert {"file", "anchor", "mode", "text", "behaviour"} <= set(p)
        assert p["file"].startswith("gfx/FX/") and "\\" not in p["file"] and ".." not in p["file"]
        assert p["mode"] in MODES
        assert p["anchor"].strip() and "\n" not in p["anchor"] and len(p["anchor"]) <= 80, "anchor must be short, one line"
        assert p["text"].strip()
        for a in anchors:
            assert a not in p["text"], f"text re-introduces anchor {a!r}"
        for open_, close in ("{}", "()", "[]"):
            assert p["text"].count(open_) == p["text"].count(close), f"unbalanced {open_}{close}"


@pytest.mark.parametrize("rel", all_patch_files())
def test_patch_is_colour_only(rel):
    """No writes to positions, UVs or depth: geometry and picking stay on the pixel grid."""
    forbidden = re.compile(
        r"(VertexOut\.|\.position\b|\bInput\.pos\s*[-+*/]?=|\buv\w*\s*[-+*/]?=|\bdiscard\b|\bclip\s*\(|SV_Depth|PDX_DEPTH)"
    )
    for p in load_spec(rel):
        code = strip_comments(p["text"])
        assert not forbidden.search(code), forbidden.search(code).group(0)


def strip_comments(text):
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


# ---------------------------------------------------------------- combining patch files
DEF_RE = re.compile(r"\bfloat\d?\s+(EE_\w+)\s*\(")
CALL_RE = re.compile(r"\b(EE_\w+)\s*\(")


def patch_combinations():
    """Every shader_patches list in the manifest, plus helpers + each behaviour alone, plus all behaviour orders."""
    import itertools

    helpers = [r for r in all_patch_files() if file_behaviour(r) == NO_BEHAVIOUR]
    behaviours = [r for r in all_patch_files() if file_behaviour(r) != NO_BEHAVIOUR]
    combos = [tuple(v["shader_patches"]) for v in manifest()["variants"] if v["shader_patches"]]
    for n in range(1, len(behaviours) + 1):
        for perm in itertools.permutations(behaviours, n):
            combos.append(tuple(helpers) + perm)
    return list(dict.fromkeys(combos))


def apply_files(sources, rels):
    """Apply patch files in order; sources = {file: text}. Returns the patched {file: text}."""
    out = dict(sources)
    for rel in rels:
        by_file = {}
        for p in load_spec(rel):
            by_file.setdefault(p["file"], []).append(p)
        for f, patches in by_file.items():
            out[f] = apply_patch(out[f], patches)
    return out


def check_definitions_before_use(text):
    first_def = {}
    for m in DEF_RE.finditer(text):
        first_def.setdefault(m.group(1), m.start(1))
    for name, pos in first_def.items():
        assert re.search(rf"\b{name}\s*\(", text).start() == pos, f"{name} used before its definition"


@pytest.mark.parametrize("combo", patch_combinations(), ids=lambda c: "+".join(Path(r).stem.replace(".patch", "") for r in c))
def test_patch_dependencies(combo):
    """Each patch file only calls EE_* functions defined by itself or an earlier file; nothing is defined twice."""
    defined = set()
    for rel in combo:
        code = "\n".join(strip_comments(p["text"]) for p in load_spec(rel))
        own = set(DEF_RE.findall(code))
        assert not own & defined, f"{rel} redefines {own & defined}"
        missing = set(CALL_RE.findall(code)) - own - defined
        assert not missing, f"{rel} needs {missing} from an earlier patch file"
        defined |= own


@pytest.mark.parametrize("combo", patch_combinations(), ids=lambda c: "+".join(Path(r).stem.replace(".patch", "") for r in c))
def test_patch_combination_applies_on_anchor_stub(combo):
    """Game-independent: the anchors apply in sequence for every combination, on a stub made of the anchors only."""
    anchors = {}
    for rel in all_patch_files():
        for p in load_spec(rel):
            anchors.setdefault(p["file"], [])
            if p["anchor"] not in anchors[p["file"]]:
                anchors[p["file"]].append(p["anchor"])
    order = {"float3 ApplyIce(": 0, "vIceFade *= vMapLimitFade;": 1}  # vanilla order; unknown anchors go last
    stub = {f: "MainCode PixelShader\n" + "\n".join(sorted(a, key=lambda s: order.get(s, 9))) + "\n" for f, a in anchors.items()}
    out = apply_files(stub, combo)
    for rel in combo:
        for p in load_spec(rel):
            assert p["text"] in out[p["file"]]
    for text in out.values():
        check_definitions_before_use(text)


# ---------------------------------------------------------------- shader maths (parsed from the shipped text)
def helper_text():
    texts = [p["text"] for rel in all_patch_files() for p in load_spec(rel) if "EE_OffGlobeDistance( float2" in p["text"]]
    assert len(texts) == 1
    return texts[0]


def _one(pattern, text):
    m = re.search(pattern, text, re.S)
    assert m, f"shader text no longer has the expected shape: {pattern}"
    return [float(g) for g in m.groups()]


def shader_literals(text):
    """Every numeric literal of the EE_* helpers, read from the shipped patch text (not from ee_project)."""
    code = strip_comments(text)
    F = FLOAT
    lit = {}
    lit["y1"], lit["y2"], lit["y3"], lit["y4"] = _one(
        rf"float EE_EqEarthY\( float vT \).*?return vT \* \( {F} - {F} \* vT2 \+ vT6 \* \( {F} \+ {F} \* vT2 \) \);", code)
    lit["d1"], lit["d2"], lit["d3"], lit["d4"] = _one(
        rf"float EE_EqEarthDY\( float vT \).*?return {F} - {F} \* vT2 \+ vT6 \* \( {F} \+ {F} \* vT2 \);", code)
    (lit["t0_div"],) = _one(rf"float vT = vYc / {F};", code)
    lit["pi"], lit["m"] = _one(rf"float vHalfWidth = vScale \* {F} \* cos\( vT \) / \( {F} \* EE_EqEarthDY\( vT \) \);", code)
    for name in ("vScale", "vZEquator", "vYTop", "vYBot"):
        (lit[name],) = _one(rf"float {name} = {F};", code)
    lit["half_w"] = _one(rf"abs\( vCol - {F} \* MAP_SIZE_X \)", code)[0]
    lit["guard_w"], lit["guard_tol_w"], lit["guard_h"], lit["guard_tol_h"] = _one(
        rf"step\( abs\( MAP_SIZE_X - {F} \), {F} \) \* step\( abs\( MAP_SIZE_Y - {F} \), {F} \)", code)
    lit["newton"] = float(code.count("vT -= ( EE_EqEarthY( vT ) - vYc ) / EE_EqEarthDY( vT );"))
    # nothing unaccounted for: every float literal in the helpers is one of the parsed ones
    stray = [float(x) for x in re.findall(r"(?<![\w.])\d+\.\d+", code)]
    known = {abs(v) for v in lit.values()}
    assert all(abs(v) in known for v in stray), sorted(set(abs(v) for v in stray) - known)
    return lit


def test_shader_literals_match_projection():
    lit = shader_literals(helper_text())
    a1, a2, a3, a4, m = ee_project.A1, ee_project.A2, ee_project.A3, ee_project.A4, ee_project.M
    expect = {
        "y1": a1, "y2": -a2, "y3": a3, "y4": a4,                    # y(theta) = theta (A1 + A2 t2 + t6 (A3 + A4 t2))
        "d1": a1, "d2": -3 * a2, "d3": 7 * a3, "d4": 9 * a4,        # dy/dtheta
        "t0_div": a1, "pi": math.pi, "m": m, "half_w": 0.5,
    }
    for k, v in expect.items():
        assert abs(lit[k] - v) < 1e-6, (k, lit[k], v)
    assert abs(lit["vScale"] - CANVAS.scale) < 1e-3
    assert abs(lit["vZEquator"] - (CANVAS.H - CANVAS.margin - CANVAS.y_top * CANVAS.scale)) < 1e-3
    assert abs(lit["vYTop"] - CANVAS.y_top) < 1e-6 and abs(lit["vYBot"] - CANVAS.y_bot) < 1e-6
    assert (lit["guard_w"], lit["guard_h"]) == (float(CANVAS.W), float(CANVAS.H))
    assert 0.0 < lit["guard_tol_w"] < 1.0 and 0.0 < lit["guard_tol_h"] < 1.0
    assert lit["newton"] >= 3


def ee_offglobe_distance(x, z, lit, width=5120.0):
    """numpy port of EE_OffGlobeDistance driven only by the literals parsed from the shader text."""

    def fy(t):
        t2 = t * t
        return t * (lit["y1"] - lit["y2"] * t2 + t2 ** 3 * (lit["y3"] + lit["y4"] * t2))

    def dfy(t):
        t2 = t * t
        return lit["d1"] - lit["d2"] * t2 + t2 ** 3 * (lit["d3"] + lit["d4"] * t2)

    scale = lit["vScale"]
    y = (z - lit["vZEquator"]) / scale
    out_y = np.maximum(y - lit["vYTop"], lit["vYBot"] - y) * scale
    yc = np.clip(y, lit["vYBot"], lit["vYTop"])
    t = yc / lit["t0_div"]
    for _ in range(int(lit["newton"])):
        t = t - (fy(t) - yc) / dfy(t)
    half = scale * lit["pi"] * np.cos(t) / (lit["m"] * dfy(t))
    col = np.mod(x / width, 1.0) * width
    return np.maximum(np.abs(col - lit["half_w"] * width) - half, out_y)


def test_shader_mask_matches_globe_mask():
    """Sign of the shipped shader's distance agrees with ee_project's globe mask away from the 1-px outline."""
    lit = shader_literals(helper_text())
    rows, cols = np.mgrid[0:CANVAS.H:3, 0:CANVAS.W:3]
    rows = rows + 0.5
    cols = cols + 0.5
    lon, _ = CANVAS.to_lonlat(cols, rows)
    y = CANVAS.y_top - (rows - CANVAS.margin) / CANVAS.scale
    on_globe = ~np.isnan(lon) & (y <= CANVAS.y_top) & (y >= CANVAS.y_bot)
    x, z = CANVAS.to_game_xz(0.0, 0.0)  # sanity: equator maps inside
    assert ee_offglobe_distance(np.array([x]), np.array([z]), lit)[0] < 0
    d = ee_offglobe_distance(cols, CANVAS.H - rows, lit)  # to_game_xz: x = col, z = H - row
    assert (d[on_globe] <= 1.0).all(), float(d[on_globe].max())
    assert (d[~on_globe] >= -1.0).all(), float(d[~on_globe].min())
    assert (~on_globe).sum() > 0.05 * on_globe.size  # the corners are really there
    # wrap: a copy of the map shifted by one width gives the same answer
    d2 = ee_offglobe_distance(cols + CANVAS.W, CANVAS.H - rows, lit)
    assert np.allclose(d, d2, atol=1e-6)


# ---------------------------------------------------------------- vanilla (skipped without the game)
@needs_game
@pytest.mark.parametrize("rel", all_patch_files())
def test_patch_anchors_unique_in_vanilla(rel):
    for p in load_spec(rel):
        src = (GAME / p["file"]).read_text(encoding="utf-8", errors="replace")
        assert src.count(p["anchor"]) == 1, f"{p['file']}: anchor {p['anchor']!r} x{src.count(p['anchor'])}"
        # colour work belongs in the pixel shader
        assert src.index(p["anchor"]) > src.index("MainCode PixelShader"), p["anchor"]


@needs_game
@pytest.mark.parametrize("combo", patch_combinations(), ids=lambda c: "+".join(Path(r).stem.replace(".patch", "") for r in c))
def test_patch_combination_applies_on_vanilla(combo):
    """As P00b's build does it: sequential application, each anchor unique at apply time, for every combination."""
    files = {p["file"] for rel in combo for p in load_spec(rel)}
    src = {f: (GAME / f).read_text(encoding="utf-8", errors="replace") for f in files}
    out = apply_files(src, combo)
    for rel in combo:
        for p in load_spec(rel):
            assert p["text"] in out[p["file"]]
    for f in files:
        assert out[f].count("{") - out[f].count("}") == src[f].count("{") - src[f].count("}")
        check_definitions_before_use(out[f])

