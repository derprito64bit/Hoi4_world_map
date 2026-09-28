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

# (root table, namespace, key) -> (min, max) allowed value. Only keys under test in EXP-09.
WHITELIST = {
    ("NDefines_Graphics", "NGraphics", "CAMERA_OUTSIDE_MAP_DISTANCE_TOP"): (0.0, 200.0),
    ("NDefines_Graphics", "NGraphics", "CAMERA_OUTSIDE_MAP_DISTANCE_BOTTOM"): (0.0, 200.0),
    ("NDefines_Graphics", "NFrontend", "CAMERA_MAX_HEIGHT"): (50.0, 3000.0),
}
ASSIGN_RE = re.compile(r"^(NDefines_Graphics|NDefines)\.([A-Za-z_]\w*)\.([A-Z_][A-Z0-9_]*)\s*=\s*(-?\d+(?:\.\d+)?)\s*$")
MODES = {"before", "after", "replace"}


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


def test_each_variant_adds_one_thing():
    variants = manifest()["variants"]
    items = [set(v["defines"]) | set(v["shader_patches"]) for v in variants]
    for i in range(1, len(variants)):
        assert any(items[j] <= items[i] and len(items[i] - items[j]) == 1 for j in range(i)), variants[i]["id"]


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
        assert (root, ns, key) in WHITELIST, f"{rel}: {root}.{ns}.{key} not whitelisted"
        assert (root, ns, key) not in seen, f"{rel}: {key} set twice"
        seen.add((root, ns, key))
        lo, hi = WHITELIST[(root, ns, key)]
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
        # the camera must still reach the pole line / 60S cut, i.e. at least the off-globe margin
        assert vals[key] >= math.ceil(CANVAS.margin), key
    assert vals["CAMERA_MAX_HEIGHT"] < 3000.0


@needs_game
def test_lua_namespaces_match_vanilla():
    table = vanilla_namespace_keys(GAME / "common" / "defines" / "00_graphics.lua")
    for rel in all_define_files():
        for root, ns, key, _ in parse_lua(REPO / rel):
            assert root == "NDefines_Graphics"
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
    anchors = [p["anchor"] for p in spec]
    for p in spec:
        assert {"file", "anchor", "mode", "text"} <= set(p)
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
        code = "\n".join(line.split("//", 1)[0] for line in p["text"].splitlines())
        assert not forbidden.search(code), forbidden.search(code).group(0)


def _shader_consts(text):
    def num(name):
        m = re.search(rf"\b{name}\s*=\s*(-?\d+\.\d+)", text)
        assert m, name
        return float(m.group(1))

    return num("vScale"), num("vZEquator"), num("vYTop"), num("vYBot")


def ee_offglobe_distance(x, z, consts, width=5120.0):
    """numpy port of EE_OffGlobeDistance (same constants, same 3 Newton steps)."""
    scale, z_eq, y_top, y_bot = consts
    a1, a2, a3, a4 = ee_project.A1, ee_project.A2, ee_project.A3, ee_project.A4

    def fy(t):
        t2 = t * t
        return t * (a1 + a2 * t2 + t2 ** 3 * (a3 + a4 * t2))

    def dfy(t):
        t2 = t * t
        return a1 + 3 * a2 * t2 + t2 ** 3 * (7 * a3 + 9 * a4 * t2)

    y = (z - z_eq) / scale
    out_y = np.maximum(y - y_top, y_bot - y) * scale
    yc = np.clip(y, y_bot, y_top)
    t = yc / a1
    for _ in range(3):
        t = t - (fy(t) - yc) / dfy(t)
    half = scale * math.pi * np.cos(t) / (ee_project.M * dfy(t))
    col = np.mod(x / width, 1.0) * width
    return np.maximum(np.abs(col - 0.5 * width) - half, out_y)


def test_shader_constants_match_canvas():
    helper = next(p["text"] for rel in all_patch_files() for p in load_spec(rel) if "EE_OffGlobeDistance( float2" in p["text"])
    scale, z_eq, y_top, y_bot = _shader_consts(helper)
    assert abs(scale - CANVAS.scale) < 1e-3
    assert abs(z_eq - (CANVAS.H - CANVAS.margin - CANVAS.y_top * CANVAS.scale)) < 1e-3
    assert abs(y_top - CANVAS.y_top) < 1e-6 and abs(y_bot - CANVAS.y_bot) < 1e-6
    assert "5120.0" in helper and "2304.0" in helper  # canvas guard


def test_shader_mask_matches_globe_mask():
    """Sign of the shader distance agrees with ee_project's globe mask away from the 1-px outline."""
    helper = next(p["text"] for rel in all_patch_files() for p in load_spec(rel) if "EE_OffGlobeDistance( float2" in p["text"])
    consts = _shader_consts(helper)
    rows, cols = np.mgrid[0:CANVAS.H:3, 0:CANVAS.W:3]
    rows = rows + 0.5
    cols = cols + 0.5
    lon, _ = CANVAS.to_lonlat(cols, rows)
    y = CANVAS.y_top - (rows - CANVAS.margin) / CANVAS.scale
    on_globe = ~np.isnan(lon) & (y <= CANVAS.y_top) & (y >= CANVAS.y_bot)
    x, z = CANVAS.to_game_xz(0.0, 0.0)  # sanity: equator maps inside
    assert ee_offglobe_distance(np.array([x]), np.array([z]), consts)[0] < 0
    d = ee_offglobe_distance(cols, CANVAS.H - rows, consts)  # to_game_xz: x = col, z = H - row
    assert (d[on_globe] <= 1.0).all(), float(d[on_globe].max())
    assert (d[~on_globe] >= -1.0).all(), float(d[~on_globe].min())
    assert (~on_globe).sum() > 0.05 * on_globe.size  # the corners are really there
    # wrap: a copy of the map shifted by one width gives the same answer
    d2 = ee_offglobe_distance(cols + CANVAS.W, CANVAS.H - rows, consts)
    assert np.allclose(d, d2, atol=1e-6)


@needs_game
@pytest.mark.parametrize("rel", all_patch_files())
def test_patch_anchors_unique_in_vanilla(rel):
    spec = load_spec(rel)
    by_file = {}
    for p in spec:
        by_file.setdefault(p["file"], []).append(p)
    for f, patches in by_file.items():
        src = (GAME / f).read_text(encoding="utf-8", errors="replace")
        for p in patches:
            assert src.count(p["anchor"]) == 1, f"{f}: anchor {p['anchor']!r} x{src.count(p['anchor'])}"
            # colour work belongs in the pixel shader
            assert src.index(p["anchor"]) > src.index("MainCode PixelShader"), p["anchor"]
        out = apply_patch(src, patches)  # sequential uniqueness, as P00b's build applies them
        for p in patches:
            assert p["text"] in out
        assert out.count("{") - out.count("}") == src.count("{") - src.count("}")
