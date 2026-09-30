"""P00b-f5: the 2-px-grid engine boxes, the conservative union guard, and the EXP-03-191only / -div0b probes."""
import numpy as np
import pytest

from experiments.common import KitError
from experiments.regioncentre import (DUMP_BOX, DUMP_MEAN, DUMP_RECT, DUMP_REGION, engine_boxes, grid_centre,
                                      guard_failures, pixel_boxes, region_centre, region_centres)


def _boxes(xmin, xmax, ymin, ymax):
    """Pixel-box arrays for IDs 0..n (ID 0 unused), as region_centre() takes them."""
    return tuple(np.array([0] + list(a), dtype=np.int64) for a in (xmin, xmax, ymin, ymax))


def test_engine_box_of_the_dump_province():
    """Province 19700 in EXP-03-24k: pixels x 3164..3178, y 1952..1967 (bottom-up); engine box (3164, 1952, 16, 16)."""
    pid, box = DUMP_BOX
    bx, by, bw, bh = engine_boxes([3164], [3178], [1952], [1967])
    assert (int(bx[0]), int(by[0]), int(bw[0]), int(bh[0])) == box and pid == 19700
    # span + 1 (the old convention A) would give w = 15
    bx, by, bw, bh = engine_boxes([3164], [3178], [1952], [1967], grid=1)
    assert (int(bw[0]), int(bh[0])) == (15, 16)


@pytest.mark.parametrize("xmin,xmax,box", [(4, 5, (4, 2)), (4, 4, (4, 2)), (5, 5, (4, 2)), (5, 6, (4, 4)),
                                           (3, 10, (2, 10))])
def test_engine_boxes_snap_both_ends_to_the_grid(xmin, xmax, box):
    bx, _, bw, _ = engine_boxes([xmin], [xmax], [0], [0])
    assert (int(bx[0]), int(bw[0])) == box


def test_grid_centre_inside_and_outside():
    # box 1 pixels x 0..9 -> grid 0..10; box 2 pixels x 12..13 -> grid 12..14; centres 5 and 13 -> mean 9
    mean, rect, fallback, strict, dx = grid_centre(np.array([0, 12]), np.array([9, 13]), np.array([0, 0]),
                                                   np.array([1, 1]))
    assert mean == (9, 1) and rect == (0, 0, 14, 2) and not fallback and not strict and dx == 9 - 7
    # move box 2 (pixels 16..17 -> grid 16..18, centre 17) so that the mean (11) falls between 10 and 16
    mean, rect, fallback, strict, dx = grid_centre(np.array([0, 16]), np.array([9, 17]), np.array([0, 0]),
                                                   np.array([1, 1]))
    assert mean == (11, 1) and fallback and strict and rect == (0, 0, 18, 2) and dx == 11 - 9


# Two members side by side along one axis (the other axis: pixels 0..9 -> grid 0..10, centre 5).
#   "upper": box 1 pixels 0..9 (grid 0..10, centre 5), box 2 pixels 14..15 (grid 14..16, centre 15):
#            mean 10 = box 1's upper grid edge (bx + bw), outside box 2
#   "lower": box 1 pixels 0..1 (grid 0..2, centre 1), box 2 pixels 6..15 (grid 6..16, centre 11):
#            mean 6 = box 2's lower grid edge (bx), outside box 1
#   None:    box 1 pixels 0..9 (grid 0..10), box 2 pixels 16..17 (grid 16..18, centre 17): mean 11, in no box
EDGE_LAYOUTS = {"upper": ([0, 14], [9, 15], 10), "lower": ([0, 6], [1, 15], 6), None: ([0, 16], [9, 17], 11)}


@pytest.mark.parametrize("axis", ["x", "y"])
@pytest.mark.parametrize("edge", ["upper", "lower", None])
def test_grid_member_test_on_a_box_edge(axis, edge):
    """RVA 0x15A5C20 reads inclusive (bx <= M <= bx + bw): a mean exactly on a grid-box edge is inside; the
    open-bound convention (bx < M < bx + bw) counts it as outside. The model keeps both."""
    lo, hi, m = EDGE_LAYOUTS[edge]
    lo, hi, other0, other1 = np.array(lo), np.array(hi), np.array([0, 0]), np.array([9, 9])
    args = (lo, hi, other0, other1) if axis == "x" else (other0, other1, lo, hi)
    mean, _, fallback, strict, _ = grid_centre(*args)
    assert mean == ((m, 5) if axis == "x" else (5, m))
    assert fallback == (edge is None)          # inclusive: on an edge = inside; between the boxes = outside
    assert strict                              # open bounds: on an edge = outside too


def test_crash_g2_counts_the_open_bound():
    """Grid dx 0 with the mean on a grid-box edge: inside under the inclusive test, outside under the open one.
    crash_g2 must flag it (conservative across compare conventions)."""
    # box 1 pixels x 0..9 (grid 0..10); box 2 pixels x a..a+w; both y 0..9: search the first layout with
    # grid dx 0 and the mean exactly on a grid-box edge
    found = None
    for a in range(10, 60, 2):
        for w in range(0, 20):
            b = _boxes([0, a], [9, a + w], [0, 0], [9, 9])
            c = region_centre(9, [1, 2], b, 1000)
            if c.dx_g2 == 0 and not c.fallback_g2 and c.fallback_g2_strict:
                found = c
                break
        if found:
            break
    assert found is not None
    assert found.crash_g2 and found.unsafe


def test_open_bound_changes_no_grid_verdict_elsewhere():
    """fallback_g2 implies fallback_g2_strict (outside inclusive -> outside open)."""
    rng = np.random.default_rng(7)
    for _ in range(3000):
        k = int(rng.integers(1, 5))
        x0 = rng.integers(0, 60, k)
        y0 = rng.integers(0, 60, k)
        c = region_centre(1, list(range(1, k + 1)), _boxes(x0, x0 + rng.integers(0, 12, k), y0,
                                                           y0 + rng.integers(0, 12, k)), 10_000)
        assert not c.fallback_g2 or c.fallback_g2_strict


def test_grid_mean_is_the_old_mean_or_one_more():
    """Per box the grid centre is the old centre or +1, so ``clear`` (margin >= 1) also keeps the grid mean inside."""
    rng = np.random.default_rng(55)
    for _ in range(3000):
        k = int(rng.integers(1, 6))
        x0 = rng.integers(0, 200, k)
        y0 = rng.integers(0, 200, k)
        b = _boxes(x0, x0 + rng.integers(0, 30, k), y0, y0 + rng.integers(0, 30, k))
        c = region_centre(1, list(range(1, k + 1)), b, 10_000)
        assert c.mean_g2[0] - c.mean[0] in (0, 1) and c.mean_g2[1] - c.mean[1] in (0, 1)
        if c.clear:
            assert not c.fallback_g2 and not c.fallback_g2_strict and not c.crash_g2


def test_unsafe_is_the_union_of_both_models():
    # the grid model alone predicts the crash (old dx -1, grid dx 0) -> unsafe
    a = region_centre(9, [1, 2], _boxes([9, 12], [19, 17], [10, 33], [13, 37]), 1000)
    assert a.dx == -1 and not a.unsafe_old and a.fallback_g2 and a.dx_g2 == 0 and a.crash_g2 and a.unsafe
    # the old rule alone (old dx 0, grid dx +1: the EXP-03-div0 pattern) -> still unsafe (conservative)
    b = region_centre(9, [1, 2], _boxes([32, 13], [37, 22], [4, 12], [5, 17]), 1000)
    assert b.dx == 0 and b.unsafe_old and b.dx_g2 == 1 and not b.crash_g2 and b.unsafe
    assert guard_failures({9: a}) == [9] and guard_failures({9: b}) == [9]


def test_diag03_names_the_clause_that_fired():
    from dataclasses import replace
    from experiments.diag03 import unsafe_why
    a = region_centre(9, [1, 2], _boxes([9, 12], [19, 17], [10, 33], [13, 37]), 1000)   # grid only
    b = region_centre(9, [1, 2], _boxes([32, 13], [37, 22], [4, 12], [5, 17]), 1000)    # old dx only
    assert unsafe_why(a) == "grid dx = 0"
    assert unsafe_why(b) == "dx = 0 (old boxes)"
    # dx 0 but the mean inside a box under the strict old test, dy 0 on the fallback: only "dy" fired
    c = replace(b, fallback_strict=False, fallback=True, dy=0, dx=0, dx_g2=5)
    assert c.unsafe and unsafe_why(c) == "dy = 0 (old boxes, flagged only as caution)"
    e = replace(a, fallback_g2=False, fallback_g2_strict=True)
    assert e.crash_g2 and unsafe_why(e) == "grid dx = 0 (mean on a grid-box edge: open bound only)"


def test_wrapping_region_is_never_a_grid_crash_only_unknown():
    pid = np.full((60, 100), 1, dtype=np.int32)
    pid[10:20, 0:10] = 2
    pid[40:50, 90:100] = 3
    c = region_centres(pid, {5: [2, 3]})[5]
    assert c.seam and not c.crash_g2 and not c.unsafe and c.unknown


# ---------------------------------------------------------------- local_split (synthetic)
def test_local_split_copies_only_the_region_families():
    from test_changes import big_world
    from experiments.exp03 import local_split, subdivide
    pid, d = big_world()
    types = d.types()
    n0 = d.n
    src, root_src = subdivide(pid, types, 12, np.arange(n0), {}, {2, 3}, min_px=40)
    region_of = np.array([-1, 1, 7, 8, 8, 7, 8])                # region 7 = provinces 2 and 5
    out, root, parents = local_split(pid, src, root_src, region_of, 7)
    fam = [i for i in range(n0, len(root_src)) if region_of[root_src[i]] == 7]
    assert parents == sorted({int(root_src[i]) for i in fam}) and set(parents) <= {2, 5}
    assert len(root) == n0 + len(fam) and list(root[n0:]) == [int(root_src[i]) for i in fam]
    m = np.isin(pid, parents)
    assert (out[~m] == pid[~m]).all()                             # everything else stays vanilla
    remap = {i: n0 + j for j, i in enumerate(fam)}
    want = np.vectorize(lambda x: remap.get(int(x), int(x)))(src[m])
    assert (out[m] == want).all()                                 # same pixels, renumbered in source order
    assert np.array_equal(root[out], pid)                         # every piece inside its vanilla parent
    with pytest.raises(KitError):
        local_split(pid, src, root_src, region_of, 1)             # region 1 (sea) has no split province


def test_local_split_rejects_a_source_that_is_not_a_refinement():
    from test_changes import big_world
    from experiments.exp03 import local_split, subdivide
    pid, d = big_world()
    n0 = d.n
    src, root_src = subdivide(pid, d.types(), 4, np.arange(n0), {}, {2, 3}, min_px=40)
    kid = n0                                                      # a piece of some parent
    bad = src.copy()
    bad[pid == 1] = np.where(np.arange(bad[pid == 1].size) == 0, kid, 1)   # one sea pixel claims that piece
    region_of = np.full(n0, 7)
    with pytest.raises(KitError):
        local_split(pid, bad, root_src, region_of, 7)


def test_probe_readmes_state_the_model_values_and_both_outcomes():
    from types import SimpleNamespace
    from experiments.exp03 import Exp03
    model = {"members": 54, "mean": [3141, 1961], "rect": [2990, 1854, 302, 170], "dx": 0, "dy": 22,
             "fallback_all": True, "mean_g2": [3141, 1961], "rect_g2": [2990, 1854, 302, 170], "fallback_g2": True,
             "dx_g2": 0}
    ctx = SimpleNamespace(user=None, vanilla=SimpleNamespace(definition=SimpleNamespace(n=13414)))
    e = Exp03()
    local = e.readme(ctx, "EXP-03-191only", {"local": {"region": 191, "region_file": "191-Northern Norway.txt",
                                                       "parents": [3040, 6015], "pieces": 9,
                                                       "states": ["924-Troms.txt"], "model": model}})
    assert "numbered 13414-13422" in local and "3040, 6015" in local
    assert "mean point (3141, 1961), region rectangle (2990, 1854, 302, 170), divisor 0" in local
    assert "If it loads" in local and "0x15A4CDC" in local and "it is a fit, not proven" in local
    trap = e.readme(ctx, "EXP-03-div0b", {"trap": {"region": 193, "province": 4505, "pieces": 2,
                                                    "region_file": "193-Northern Australia.txt",
                                                    "state_file": "872-North Queensland.txt", "model": model}})
    assert "province 4505" in trap and "into 2 pieces" in trap and "+1 under the corrected one; it loaded" in trap
    assert "If it loads" in trap and "Both models predict this crash" in trap
    assert "EXPECTED IN GAME (both models predict it)" in trap
    grid = dict(model, dx=-3)
    only = e.readme(ctx, "EXP-03-div0c", {"trap": {"region": 193, "province": 1501, "pieces": 2,
                                                    "region_file": "193-Northern Australia.txt",
                                                    "state_file": "x.txt", "model": grid}})
    assert "ONLY the corrected 2-pixel-grid model predicts" in only and "(its divisor is -3)" in only
    assert "The first model would expect it to load" in only and "If it loads" in only
    order = "Run order: EXP-03-191only first, then EXP-03-div0c, then EXP-03-div0b."
    assert all(order in t for t in (local, trap, only))


# ---------------------------------------------------------------- against the game install
@pytest.fixture(scope="module")
def exp03_24k(ctx):
    from experiments.exp03 import Exp03, region_lookup
    v = ctx.vanilla
    pid, root, _, _ = Exp03().make(v, "EXP-03-24k")
    return pid, root, region_lookup(v, v.definition.n)


def test_grid_model_reproduces_every_dump_value(exp03_24k):
    """Mean, rect and province 19700's box from the 24k dumps, all from one rule (2-px grid)."""
    from experiments.exp03 import centres_of
    pid, root, region_of = exp03_24k
    c = centres_of(pid, root, region_of)[DUMP_REGION]
    assert c.mean_g2 == DUMP_MEAN and c.rect_g2 == DUMP_RECT and c.fallback_g2 and c.dx_g2 == 0 and c.crash_g2
    x0, x1, y0, y1 = pixel_boxes(pid, len(root))
    p, box = DUMP_BOX
    assert tuple(int(a[0]) for a in engine_boxes(x0[p:p + 1], x1[p:p + 1], y0[p:p + 1], y1[p:p + 1])) == box
    assert root[p] and region_of[root[p]] == DUMP_REGION
    assert DUMP_BOX[0] in [i for i in range(len(root)) if region_of[root[i]] == DUMP_REGION]


def test_grid_model_explains_the_div0_load(ctx):
    """EXP-03-div0 loaded in game: its region 193 has dx 0 under the old rule but +1 on the grid."""
    from experiments.exp03 import Exp03, centres_of, region_lookup
    v = ctx.vanilla
    pid, root, _, info = Exp03().make(v, "EXP-03-div0")
    c = centres_of(pid, root, region_lookup(v, v.definition.n))[193]
    assert info["trap"]["region"] == 193 and info["trap"]["province"] == 2166
    assert c.dx == 0 and c.unsafe_old and c.fallback_g2 and c.dx_g2 == 1 and not c.crash_g2
    assert c.mean_g2 == (4952, 417) and c.rect_g2 == (4834, 336, 234, 154)


def test_vanilla_has_no_grid_crash_and_the_same_unknown_regions(ctx):
    from experiments.exp03 import region_lookup, vanilla_centres
    v = ctx.vanilla
    cs = vanilla_centres(np.asarray(v.pid), region_lookup(v, v.definition.n))
    assert [r for r, c in cs.items() if c.crash_g2] == []
    assert [r for r, c in cs.items() if c.unknown] == [88, 95, 96, 97, 178, 180]
    assert sum(c.fallback_g2 for c in cs.values()) == 14


def test_191only_is_24k_restricted_to_region_191(ctx, exp03_24k):
    from experiments.exp03 import LOCAL_SIGNATURE, Exp03, centres_of, guard_failures_of
    v = ctx.vanilla
    n0 = v.definition.n
    src, root_src, region_of = exp03_24k
    pid, root, _, info = Exp03().make(v, "EXP-03-191only")
    van = np.asarray(v.pid)
    parents = info["local"]["parents"]
    assert parents == sorted({int(root_src[i]) for i in range(n0, len(root_src)) if region_of[root_src[i]] == 191})
    assert info["local"]["pieces"] == len(root) - n0 == 9
    m = np.isin(van, parents)
    assert (pid[~m] == van[~m]).all()
    kids = [i for i in range(n0, len(root_src)) if region_of[root_src[i]] == 191]
    lut = np.arange(len(root_src))
    lut[kids] = np.arange(n0, n0 + len(kids))
    assert (pid[m] == lut[src[m]]).all()                         # the same pieces, pixel for pixel
    c = centres_of(pid, root, region_of)[191]
    assert c.signature == LOCAL_SIGNATURE == centres_of(src, root_src, region_of)[191].signature
    assert c.mean == c.mean_g2 == DUMP_MEAN and c.rect == c.rect_g2 == DUMP_RECT and c.dx == c.dx_g2 == 0
    assert guard_failures_of(pid, root, region_of, centres_of(van, np.arange(n0), region_of)) == [191]


def test_div0b_divides_by_zero_under_both_models(ctx):
    from experiments.exp03 import Exp03, centres_of, region_lookup
    v = ctx.vanilla
    n0 = v.definition.n
    pid, root, _, info = Exp03().make(v, "EXP-03-div0b")
    t = info["trap"]
    ro = region_lookup(v, n0)
    c = centres_of(pid, root, ro)[t["region"]]
    assert set(root[n0:].tolist()) == {t["province"]} and len(root) - n0 == t["pieces"] - 1
    assert c.fallback_all and c.dx == 0 and c.fallback_g2 and c.dx_g2 == 0 and c.crash_g2
    assert t["province"] != 2166                                   # not the div0 cut
    assert (t["region"], t["province"], t["pieces"]) == (193, 4505, 2)


def test_div0c_divides_by_zero_only_under_the_grid_model(ctx):
    """P00b-f5 r2: the mirror of EXP-03-div0 (old dx 0, grid dx +1, loaded): old model safe, grid dx 0."""
    from experiments.exp03 import Exp03, centres_of, region_lookup
    v = ctx.vanilla
    n0 = v.definition.n
    pid, root, _, info = Exp03().make(v, "EXP-03-div0c")
    t = info["trap"]
    c = centres_of(pid, root, region_lookup(v, n0))[t["region"]]
    assert set(root[n0:].tolist()) == {t["province"]} and len(root) - n0 == t["pieces"] - 1
    assert (t["region"], t["province"], t["pieces"]) == (193, 1501, 2)
    assert c.dx == -1 and c.dy != 0 and not c.unsafe_old                 # the old model: no division by zero
    assert c.fallback_g2 and c.dx_g2 == 0 and c.crash_g2 and c.unsafe   # the grid model: divides by zero
    assert c.mean_g2 == (4951, 419) and c.rect_g2 == (4834, 336, 234, 154)
