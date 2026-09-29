"""P00b-f3: strategic-region centre model (the EXP-03-24k divide-by-zero) and the EXP-03 guard / trap."""
import numpy as np
import pytest

from experiments.common import KitError
from experiments.mapdata import Definition
from experiments.regioncentre import province_boxes, region_centre, region_centres


def ring_world(right_width=15):
    """Region 2 is a ring of four land bars around an inner sea (6); region 3 is one big block (7).

    With ``right_width=15`` region 2 takes the engine's fallback path with divisor -1;
    with 10 the ring is symmetric and the divisor is 0 already.
    """
    H, W = 120, 200
    pid = np.full((H, W), 1, dtype=np.int32)
    pid[20:30, 40:140] = 2
    pid[90:100, 40:140] = 3
    pid[30:90, 40:50] = 4
    pid[30:90, 140 - right_width:140] = 5
    pid[30:90, 50:140 - right_width] = 6
    pid[20:100, 150:196] = 7
    types = ["", "sea", "land", "land", "land", "land", "sea", "land"]
    rows = [["0", "0", "0", "0", "land", "false", "unknown", "0"]]
    for i in range(1, len(types)):
        rows.append([str(i), str(i * 30), "0", "0", types[i], "false", "plains", "1"])
    region_of = np.array([-1, 1, 2, 2, 2, 2, 1, 3])
    return pid, Definition(rows=rows, trailing_newline=False), region_of


REGIONS = {1: [1, 6], 2: [2, 3, 4, 5], 3: [7]}


def test_province_boxes_use_bottom_up_rows_and_inclusive_size():
    pid = np.zeros((10, 20), dtype=np.int32)
    pid[2:5, 3:9] = 1                       # rows 2..4, cols 3..8
    x0, y0, w, h = province_boxes(pid, 2)
    assert (x0[1], y0[1], w[1], h[1]) == (3, 10 - 1 - 4, 6, 3)


def test_region_rect_is_span_plus_two_like_the_dump():
    """Dump: Northern Norway spans 300 columns and the engine rect is 302 wide; same rule here."""
    pid, _, _ = ring_world()
    c = region_centres(pid, REGIONS)[2]
    assert c.rect == (40, 120 - 1 - 99, 101, 81)        # columns 40..139 -> span 99 -> 101
    assert c.fallback and c.divisor == -1 and not c.unsafe


def test_symmetric_ring_divides_by_zero():
    pid, _, _ = ring_world(right_width=10)
    c = region_centres(pid, REGIONS)[2]
    assert c.fallback and c.divisor == 0 and c.unsafe


def test_mean_inside_a_member_box_skips_the_fallback():
    pid, _, _ = ring_world()
    c = region_centres(pid, REGIONS)[3]
    assert not c.fallback and c.divisor is None and not c.unsafe


def test_mean_is_truncated_integer_mean_of_box_centres():
    boxes = tuple(np.array(a, dtype=np.int64) for a in ([0, 0, 10], [0, 0, 0], [0, 3, 3], [0, 3, 3]))
    c = region_centre(9, [1, 2], boxes, 100)                 # centres x 1 and 11 -> mean 6
    assert c.mean == (6, 1) and c.rect == (0, 0, 14, 4) and c.fallback and c.divisor == 6 - 7


def test_trap_split_makes_exactly_that_region_unsafe():
    from experiments.exp03 import trap_split, unsafe_of
    pid, d, region_of = ring_world()
    types = d.types()
    assert unsafe_of(pid, np.arange(d.n), region_of) == []
    out, root, (rid, p, k) = trap_split(pid, types, region_of, {}, set(), set())
    assert rid == 2 and region_of[p] == 2 and len(root) == d.n + k - 1
    assert set(root[d.n:].tolist()) == {p}
    assert unsafe_of(out, root, region_of) == [2]


def test_trap_respects_frozen_provinces():
    from experiments.exp03 import trap_candidates
    pid, d, region_of = ring_world()
    cands = list(trap_candidates(pid, d.types(), region_of, {2, 3, 4, 5}))
    assert cands == []


def test_guarded_subdivide_avoids_the_division_and_keeps_the_count():
    from experiments.exp03 import guarded_subdivide, subdivide, unsafe_of
    pid, d, region_of = ring_world()
    types = d.types()
    n0 = d.n
    plain_pid, plain_root = subdivide(pid, types, 22, np.arange(n0), {}, set(), frozen=set())
    assert unsafe_of(plain_pid, plain_root, region_of) == [2]            # the unguarded plan hits it
    out, root, guard, moved = guarded_subdivide(pid, types, 22, {}, set(), set(), region_of)
    assert len(root) == n0 + 22
    assert unsafe_of(out, root, region_of) == []
    assert guard and all(r == 2 and region_of[p] == 2 for r, p in guard)
    assert not (root[n0:] == guard[0][1]).any()                           # the frozen parent stays whole
    kids, plain = np.bincount(root[n0:], minlength=n0), np.bincount(plain_root[n0:], minlength=n0)
    assert moved and moved == [int(p) for p in np.nonzero(kids > plain)[0]]


def test_guard_refuses_a_region_that_is_unsafe_without_splits():
    from experiments.exp03 import guarded_subdivide
    pid, d, region_of = ring_world(right_width=10)
    with pytest.raises(KitError):
        guarded_subdivide(pid, d.types(), 3, {}, set(), set(), region_of)


def test_vanilla_has_no_unsafe_region(ctx):
    from experiments.exp03 import region_lookup, unsafe_of
    v = ctx.vanilla
    n0 = v.definition.n
    assert unsafe_of(np.asarray(v.pid), np.arange(n0), region_lookup(v, n0)) == []


def test_diag03_reports_vanilla_clean(ctx, capsys):
    from experiments import diag03
    assert diag03.report("vanilla", None, ctx.game) == 0
    assert "divide-by-zero 0" in capsys.readouterr().out
