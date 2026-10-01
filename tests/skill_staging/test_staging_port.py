"""P00e: the staged validator is a faithful, self-contained extension of the skill's validator.

* its region-centre model equals the reviewed tools/experiments/regioncentre.py (random layouts);
* it imports only stdlib + numpy + PIL (overwatch copies it over the skill file byte for byte);
* it differs from the skill original only where P00e changed it (coarse: functions, flags, codes, and
  the exact set of original lines that were removed).
"""
import ast
import difflib
import sys

import numpy as np
import pytest

from staging_helpers import ORIGINAL, REPO, STAGED, load_staged

NEW_CODES = {("ERROR", "REGION_CENTRE_DIV0"), ("WARN", "REGION_CENTRE_UNKNOWN"), ("INFO", "REGION_CENTRE_UNKNOWN"),
             ("ERROR", "SEA_REGION_FRACTIONED"), ("ERROR", "PROVINCE_CROSSES_SEAM"), ("WARN", "BBOX_ENGINE_RISK"),
             ("WARN", "ADJ_SEAM_LINK")}
LEVEL = {"err": "ERROR", "warn": "WARN", "info": "INFO"}


def _lines(p):
    return p.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")


def _codes(p):
    """{(level, code)} of every R.err / R.warn / R.info call with a literal code."""
    out = set()
    for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in LEVEL
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "R" and node.args
                and isinstance(node.args[0], ast.Constant)):
            out.add((LEVEL[node.func.attr], node.args[0].value))
    return out


def _functions(p):
    return {n.name for n in ast.parse(p.read_text(encoding="utf-8")).body if isinstance(n, ast.FunctionDef)}


def _flags(p):
    out = {}
    for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
            kw = {}
            for k in node.keywords:
                if k.arg == "type":
                    kw["type"] = k.value.id
                elif k.arg in ("default", "action"):
                    kw[k.arg] = ast.literal_eval(k.value)
            out[node.args[0].value] = kw
    return out


def test_original_present():
    assert ORIGINAL.is_file() and STAGED.is_file()


def test_imports_are_stdlib_numpy_pil_only():
    allowed = set(sys.stdlib_module_names) | {"numpy", "PIL"}
    for node in ast.walk(ast.parse(STAGED.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import"
            mods = [node.module]
        else:
            continue
        for m in mods:
            assert m.split(".")[0] in allowed, m
    text = STAGED.read_text(encoding="utf-8")
    assert "sys.path" not in text and "experiments" not in "".join(
        ln for ln in text.splitlines() if ln.lstrip().startswith(("import ", "from ")))


def test_original_functions_flags_and_codes_kept():
    assert _functions(ORIGINAL) <= _functions(STAGED)
    orig, new = _flags(ORIGINAL), _flags(STAGED)
    assert set(orig) <= set(new)
    for name, kw in orig.items():
        if name == "--min-pixels":
            assert kw["default"] == 8 and new[name]["default"] == 9      # change 4
        else:
            assert {k: v for k, v in new[name].items() if k in kw} == kw, name
    assert new["--no-engine-rules"]["action"] == "store_true"
    o, s = _codes(ORIGINAL), _codes(STAGED)
    assert o <= s
    # no existing code changed or gained a level
    assert {c for c in s if c[1] in {x[1] for x in o}} == o
    assert s - o == NEW_CODES


def test_only_the_listed_lines_of_the_original_were_changed():
    """Every original line survives except the usage line and the --min-pixels argument (change 4)."""
    removed = [ln[2:] for ln in difflib.ndiff(_lines(ORIGINAL), _lines(STAGED)) if ln.startswith("- ")]
    assert removed == ["                           [--bbox-limit 250 --bbox-limit-sea 180] [--min-pixels 8]",
                       '    ap.add_argument("--min-pixels", type=int, default=8)'], removed


# ------------------------------------------------------------------ the port equals regioncentre.py
@pytest.fixture(scope="module")
def models():
    sys.path.insert(0, str(REPO / "tools"))
    rc = pytest.importorskip("experiments.regioncentre")
    return load_staged(), rc


def _random_layout(rng, W, H, n_members, seam):
    k = int(rng.integers(1, n_members + 1))
    x0 = rng.integers(0, W - 40, k)
    x1 = x0 + rng.integers(0, 40, k)
    y0 = rng.integers(0, H - 40, k)
    y1 = y0 + rng.integers(0, 40, k)
    if seam and k >= 2:
        x0[0], x1[-1] = 0, W - 1
    xmin, xmax, ymin, ymax = (np.r_[0, a].astype(np.int64) for a in (x0, x1, y0, y1))
    return list(range(1, k + 1)), (xmin, xmax, ymin, ymax)


@pytest.mark.parametrize("seed", range(6))
def test_region_centre_port_matches_regioncentre(models, seed):
    staged, rc = models
    rng = np.random.default_rng(seed)
    W, H = 256, 128
    checked = {"unsafe": 0, "unknown": 0, "safe": 0}
    for t in range(3000):
        members, boxes = _random_layout(rng, W, H, 4, seam=t % 5 == 0)
        a = staged.region_centre(members, boxes, W)
        b = rc.region_centre(7, members, boxes, W)
        assert a["mean"] == b.mean and a["rect"] == b.rect and (a["dx"], a["dy"]) == (b.dx, b.dy)
        assert a["mean_grid"] == b.mean_g2 and a["rect_grid"] == b.rect_g2 and a["dx_grid"] == b.dx_g2
        assert (a["fallback"], a["fallback_strict"]) == (b.fallback, b.fallback_strict)
        assert (a["fallback_grid"], a["fallback_grid_open"]) == (b.fallback_g2, b.fallback_g2_strict)
        assert a["seam"] == b.seam and a["signature"] == b.signature
        assert a["unsafe"] == b.unsafe and a["unknown"] == b.unknown
        assert any(c.startswith("grid model") for c in a["clauses"]) == b.crash_g2
        checked["unsafe" if b.unsafe else "unknown" if b.unknown else "safe"] += 1
    assert min(checked.values()) > 0, checked       # every branch exercised


def test_port_reproduces_the_dump_province_box(models):
    """EXP-03-24k dump: province 19700 has pixels x 3164..3178, y 1952..1967 (bottom-up), engine box (3164, 1952,
    16, 16); a one-member region's grid rect is that box."""
    staged, rc = models
    boxes = tuple(np.array([0, v], dtype=np.int64) for v in (3164, 3178, 1952, 1967))
    assert staged.region_centre([1], boxes, 5632)["rect_grid"] == rc.DUMP_BOX[1]


def test_grid_only_crash_is_an_error(models):
    """A layout that only the 2-px grid model flags (like EXP-03-div0c, which crashed in game)."""
    staged, rc = models
    rng = np.random.default_rng(99)
    for _ in range(200000):
        members, boxes = _random_layout(rng, 256, 128, 3, seam=False)
        b = rc.region_centre(1, members, boxes, 256)
        if b.crash_g2 and not b.unsafe_old:
            a = staged.region_centre(members, boxes, 256)
            assert a["unsafe"] and len(a["clauses"]) == 1 and a["clauses"][0].startswith("grid model")
            return
    pytest.fail("no grid-only layout found")
