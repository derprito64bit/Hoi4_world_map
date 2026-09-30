"""P00b-f6: clean filled shapes and the whole-map rules of EXP-02c (synthetic maps, no game needed)."""
import numpy as np
import pytest

from conftest import make_definition
from experiments.boxfill import (REMNANT, Rect, as_shape, bounding, corner_crossings, donor_splits, ell, fill,
                                 find_ells, find_rects, fractioned_naval, fractioned_parts, kind_ok, naval_regions,
                                 overlaps, shape_candidate)
from experiments.mapdata import LAND, SEA, areas, bboxes, x_crossings
from test_exp02b import grid_world


class FakeV:
    """Just enough of vanilla.Vanilla for ``exp02c.whole_map_problems``."""

    def __init__(self, types, regions, states=None):
        self.types = np.asarray(types)
        self.province_region = {p: (r, f"{r}-r.txt") for r, ps in regions.items() for p in ps}
        self.province_state = {p: (s, f"{s}-s.txt") for s, ps in (states or {}).items() for p in ps}

    def text(self, rel):
        assert rel == "map/adjacencies.csv"
        return "From;To;Type;Through;start_x;start_y;stop_x;stop_y;adjacency_rule_name;Comment\n-1;-1;;-1;-1;-1;-1;-1;-1\n"


# ---------------------------------------------------------------- shapes
def test_find_rects_gives_clean_filled_rectangles():
    pid, d = grid_world()
    types = d.types()
    found = find_rects(pid, types, LAND, 14, 14, set(), limit=5)
    assert found
    n = d.n
    for rect, got in found:
        out = fill(pid, rect, got["host"])
        bb = bboxes(out, n)
        h = got["host"]
        assert (bb[0][h], bb[1][h], bb[2][h], bb[3][h]) == bounding(rect)
        assert (out[rect.window()] == h).all()                          # no enclave
        a = areas(out, n)
        assert all(a[x] >= REMNANT for x in got["donors"])
        assert len(x_crossings(out)[0]) == 0
        from experiments.exp02c import donor_problems
        assert donor_problems(pid, out, got["donors"]) == []
    assert found == find_rects(pid, types, LAND, 14, 14, set(), limit=5)  # deterministic


def test_rectangle_that_would_cut_a_donor_in_two_is_refused():
    pid = np.full((30, 60), 1, dtype=np.int32)
    pid[:, 30:] = 2
    pid[10:14, 20:24] = 3                                   # host 3 inside donor 1
    types = np.array([-1, SEA, SEA, SEA])
    area, bb = areas(pid, 4), bboxes(pid, 4)
    cut = Rect(0, 20, 30, 4)                                # full-height band: donor 1 left and right of it
    n_out, ok = donor_splits(pid, 1, cut, bb)
    assert n_out > 0 and not ok
    assert shape_candidate(pid, types, area, bb, SEA, cut, set()) is None
    notch = Rect(8, 18, 8, 8)                               # a notch: donor 1 stays one piece
    assert donor_splits(pid, 1, notch, bb)[1]
    assert shape_candidate(pid, types, area, bb, SEA, notch, set()) == {"host": 3, "donors": [1]}


def test_shape_candidate_refuses_protected_donors_other_kinds_and_two_whole_provinces():
    pid = np.full((30, 60), 1, dtype=np.int32)
    pid[10:14, 20:24] = 3
    pid[10:14, 26:28] = 4
    types = np.array([-1, SEA, SEA, SEA, SEA])
    area, bb = areas(pid, 5), bboxes(pid, 5)
    one = Rect(8, 18, 8, 8)
    two = Rect(8, 18, 8, 12)                                # holds 3 and 4 wholly: 4 would become an enclave
    assert shape_candidate(pid, types, area, bb, SEA, one, set()) is not None
    assert shape_candidate(pid, types, area, bb, SEA, two, set()) is None
    assert shape_candidate(pid, types, area, bb, SEA, one, {1}) is None             # protected donor
    assert shape_candidate(pid, types, area, bb, LAND, one, set()) is None          # wrong kind
    tiny = pid.copy()
    tiny[:, :] = 3
    tiny[0, 0:8] = 1                                        # donor 1 would keep < REMNANT px
    assert shape_candidate(tiny, types, areas(tiny, 5), bboxes(tiny, 5), SEA, Rect(0, 2, 5, 5), set()) is None


def test_kind_ok_needs_the_ring_and_keeps_off_the_seam():
    t = np.full((20, 40), SEA)
    t[5, 30] = LAND
    assert kind_ok(t, SEA, Rect(0, 2, 20, 10))             # top and bottom edge: ring clipped
    assert not kind_ok(t, SEA, Rect(6, 20, 5, 10))          # ring touches the land pixel
    assert not kind_ok(t, SEA, Rect(0, 0, 5, 5)) and not kind_ok(t, SEA, Rect(0, 35, 5, 5))  # wrap seam


def test_ell_is_two_rectangles_with_the_named_box():
    s = ell(100, 40, 6, 60, 30, 8, True)
    assert len(s) == 2 and not overlaps(s) and bounding(s) == (40, 69, 40, 99)
    r = ell(100, 40, 6, 60, 30, 8, False)
    assert bounding(r) == (16, 45, 40, 99)
    assert overlaps([Rect(0, 0, 5, 5), Rect(4, 4, 5, 5)]) and as_shape(Rect(1, 2, 3, 4)) == (Rect(1, 2, 3, 4),)


def column_sea(H=100, W=120, cw=20, ch=25):
    """Sea of cw x ch cells in columns, every other column shifted by 12 rows (no X-crossings), plus a
    4 x 4 host cell at rows 60-63, cols 35-38 (last ID)."""
    pid = np.zeros((H, W), dtype=np.int32)
    n = 0
    for k in range(W // cw):
        for r in range(-(k % 2) * 12, H, ch):
            n += 1
            pid[max(0, r):r + ch, k * cw:(k + 1) * cw] = n
    pid[60:64, 35:39] = n + 1
    return pid, np.array([-1] + [SEA] * (n + 1))


def test_find_ells_on_an_open_sea():
    pid, types = column_sea()
    assert len(x_crossings(pid)[0]) == 0
    found = find_ells(pid, types, SEA, 6, 52, 30, 8, set(), limit=3)
    assert found and all(g["host"] == len(types) - 1 for _, g in found)
    from experiments.exp02c import donor_problems
    for shape, got in found:
        out = fill(pid, shape, got["host"])
        assert corner_crossings(out, shape) == 0 and len(x_crossings(out)[0]) == 0
        bb = bboxes(out, len(types))
        h = got["host"]
        assert (bb[0][h], bb[1][h], bb[2][h], bb[3][h]) == bounding(shape)
        assert bounding(shape)[3] == 99 and bounding(shape)[1] - bounding(shape)[0] + 1 == 30
        assert donor_problems(pid, out, got["donors"]) == []
    arm_on_border = ell(100, 34, 6, 50, 30, 8, True)       # top corner on a cell corner: an X-crossing
    assert corner_crossings(fill(pid, arm_on_border, len(types) - 1), arm_on_border) == 1
    assert all(s != arm_on_border for s, _ in found)


# ---------------------------------------------------------------- naval regions (negative tests)
def _two_band_map():
    """Rows 0-7: sea 1 [0,15), sea 2 [15,40), sea 5 [40,60); rows 8-19: sea 3 [0,60)."""
    pid = np.zeros((20, 60), dtype=np.int32)
    pid[:8, :15], pid[:8, 15:40], pid[:8, 40:] = 1, 2, 5
    pid[8:] = 3
    return pid


def test_fractioned_naval_region_is_caught():
    pid = _two_band_map()
    types = np.array([-1, SEA, SEA, SEA, LAND, SEA])
    pr = {1: (7, "a"), 2: (7, "a"), 3: (8, "b"), 5: (8, "b")}
    assert fractioned_naval(pid, pr, types) == set()
    got = pid.copy()
    got[:8, 14:16] = 3                                        # host 3 cuts the only contact of 1 and 2
    assert fractioned_naval(got, pr, types) == {7}
    assert fractioned_parts(got, pr, types) == {7: [2]}
    from experiments.exp02c import whole_map_problems
    v = FakeV(types, {7: [1, 2], 8: [3, 5]})
    assert whole_map_problems(v, pid, pid) == []
    probs = whole_map_problems(v, pid, got)
    assert any("fractioned" in p and "[7]" in p for p in probs), probs


def test_naval_contiguity_counts_contacts_across_the_wrap_and_ignores_land_members():
    pid = _two_band_map()
    types = np.array([-1, SEA, SEA, SEA, LAND, SEA])
    assert fractioned_naval(pid, {1: (7, "a"), 5: (7, "a")}, types) == set()        # 5 | 1 touch across the seam
    pid2 = pid.copy()
    pid2[:, 59] = 3                                                                 # now they do not
    assert fractioned_naval(pid2, {1: (7, "a"), 5: (7, "a")}, types) == {7}
    isl = pid.copy()
    isl[2:4, 30:32] = 4                                                             # a land island inside sea 2
    pr = {1: (7, "a"), 2: (7, "a"), 4: (7, "a"), 3: (8, "b")}
    assert naval_regions(pr, types) == {7: [1, 2], 8: [3]}  # only the sea members count
    isl[2:4, 5:7] = 4                                       # a second island piece, inside sea 1
    assert fractioned_naval(isl, pr, types) == set()        # land members apart from each other: no naval split


def test_whole_map_problems_catch_split_regions_states_and_the_centre_guard():
    from experiments.exp02c import whole_map_problems
    from experiments.regioncentre import guard_failures, region_centres
    pid = np.zeros((20, 60), dtype=np.int32)
    pid[:, :10], pid[:, 10:25], pid[:, 25:30] = 1, 2, 3
    pid[:, 30:40], pid[:, 40:50], pid[:, 50:] = 4, 5, 6
    types = np.array([-1] + [LAND] * 6)
    regions = {1: [1, 2], 2: [3, 4, 5, 6]}
    v = FakeV(types, regions, {10: [1, 2], 11: [3, 4, 5, 6]})
    assert guard_failures(region_centres(pid, regions), {}) == []
    got = pid.copy()
    got[:, 20:25] = 3                                       # 2 shrinks to 10 px like 1: region 1's mean on the edge
    assert 1 in guard_failures(region_centres(got, regions), {})
    probs = whole_map_problems(v, pid, got)
    assert any("region-centre guard" in p for p in probs), probs
    split = pid.copy()
    split[:, 41:50] = 1                                     # province 1 (region 1, state 10) cuts 5 off from 6
    probs = whole_map_problems(v, pid, split)
    assert any("strategic-region contiguity changed" in p for p in probs), probs
    assert any("state contiguity changed" in p for p in probs), probs


# ---------------------------------------------------------------- disconnected donors (negative tests)
def test_donor_problems_catch_a_cut_donor_a_lost_part_and_a_small_remnant():
    from experiments.exp02c import donor_problems
    van = np.full((20, 40), 1, dtype=np.int32)
    van[:, 30:] = 2
    got = van.copy()
    got[:, 14:16] = 3                                       # a full-height band cuts donor 1 in two
    assert any("is disconnected" in p for p in donor_problems(van, got, [1]))
    two = van.copy()
    two[:, 10] = 2                                          # donor 1 already in two parts (0-9 and 11-29)
    lost = two.copy()
    lost[:, :10] = 3                                        # one part vanishes: also a disconnect
    assert any("is disconnected" in p for p in donor_problems(two, lost, [1]))
    small = van.copy()
    small[:, :] = 3
    small[0, :5] = 1
    assert any(f"below the {REMNANT}-px remnant" in p for p in donor_problems(van, small, [1]))
    ok = van.copy()
    ok[:5, :5] = 3                                          # a corner notch keeps donor 1 in one piece
    assert donor_problems(van, ok, [1]) == []


def test_make_definition_types_for_the_fake_maps():
    d = make_definition(["", "sea", "land"])
    assert d.types().tolist() == [-1, SEA, LAND]
    with pytest.raises(AssertionError):
        FakeV(d.types(), {}).text("map/railways.txt")
