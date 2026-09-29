"""P00b-f3: conservative strategic-region centre model (the EXP-03-24k divide-by-zero) and the EXP-03 guard / trap."""
import numpy as np
import pytest

from experiments.common import KitError
from experiments.mapdata import Definition
from experiments.regioncentre import (guard_failures, pixel_boxes, province_boxes, region_centre, region_centres,
                                      unknown_regions, unsafe_regions)


def ring_world(right_width=15, bottom_rows=15):
    """Region 2 is a ring of four land bars around an inner sea (6); region 3 is one big block (7).

    Defaults: region 2 takes the fallback with dx -1 and dy 1 (safe). ``right_width=10``
    makes dx 0; ``bottom_rows=10`` makes dy 0 (both unsafe).
    """
    H, W = 120, 200
    pid = np.full((H, W), 1, dtype=np.int32)
    pid[20:30, 40:140] = 2
    pid[90:90 + bottom_rows, 40:140] = 3
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


def test_pixel_boxes_count_rows_from_the_bottom():
    pid = np.zeros((10, 20), dtype=np.int32)
    pid[2:5, 3:9] = 1                       # rows 2..4, cols 3..8
    x0, x1, y0, y1 = pixel_boxes(pid, 3)
    assert (x0[1], x1[1], y0[1], y1[1]) == (3, 8, 10 - 1 - 4, 10 - 1 - 2)
    assert x1[2] == -1                      # no pixels
    bx, by, bw, bh = province_boxes(pid, 2)
    assert (bx[1], by[1], bw[1], bh[1]) == (3, 5, 6, 3)


def test_region_rect_is_span_plus_two():
    """The dump: region 191 has xmax - xmin = 300 (301 columns) and an engine rect 302 wide; same rule here."""
    pid, _, _ = ring_world()
    c = region_centres(pid, REGIONS)[2]
    assert c.rect == (40, 120 - 1 - 104, 101, 86)        # columns 40..139 -> 99 + 2; rows 20..104 -> 84 + 2
    assert c.fallback and c.fallback_all and (c.dx, c.dy) == (-1, 1) and not c.unsafe


def test_dx_zero_divides_by_zero():
    pid, _, _ = ring_world(right_width=10)
    c = region_centres(pid, REGIONS)[2]
    assert c.fallback and c.dx == 0 and c.unsafe


def test_dy_zero_is_flagged_conservatively():
    pid, _, _ = ring_world(bottom_rows=10)
    c = region_centres(pid, REGIONS)[2]
    assert c.fallback and c.dx != 0 and c.dy == 0 and c.unsafe
    assert unsafe_regions(pid, REGIONS) == [2]


def test_mean_inside_a_member_box_skips_the_fallback():
    pid, _, _ = ring_world()
    c = region_centres(pid, REGIONS)[3]
    assert not c.fallback and c.divisor is None and not c.unsafe and c.gap == 0


def test_mean_is_truncated_integer_mean_of_box_centres():
    boxes = tuple(np.array(a, dtype=np.int64) for a in ([0, 0, 10], [-1, 2, 12], [0, 0, 0], [-1, 2, 2]))
    c = region_centre(9, [1, 2], boxes, 100)                 # centres x 1 and 11 -> mean 6
    assert c.mean == (6, 1) and c.rect == (0, 0, 14, 4) and c.fallback and c.dx == 6 - 7 and c.gap == 4


@pytest.mark.parametrize("s", [1, 2, 3])
def test_box_edge_ambiguity_counts_as_fallback(s):
    """Mean at xmax + s of box 1: inside under the widest convention for s <= 2, yet ``fallback`` is True."""
    # box 1 x 0..10 (centre 5), box 2 x (14+2s)..(16+2s) (centre 15+2s) -> mean x 10 + s; both y 0..9
    boxes = tuple(np.array(a, dtype=np.int64) for a in ([0, 0, 14 + 2 * s], [-1, 10, 16 + 2 * s], [0, 0, 0],
                                                         [-1, 9, 9]))
    c = region_centre(9, [1, 2], boxes, 100)
    assert c.mean == (10 + s, 5)
    assert c.fallback and c.fallback_all == (s > 2) and c.gap == s


@pytest.mark.parametrize("edge", ["left", "bottom"])
def test_mean_on_a_lower_box_edge_counts_as_fallback_for_dx(edge):
    """Strip layouts: the mean sits on the shared edge of two boxes; a strict lower bound misses both."""
    # box 1 x 0..9, box 2 x 10..19 (centres 5 and 15 -> mean x 10 = box 2's xmin); both y 0..9 (mean y 5)
    boxes = [np.array(a, dtype=np.int64) for a in ([0, 0, 10], [-1, 9, 19], [0, 0, 0], [-1, 9, 9])]
    if edge == "bottom":            # the same, rotated: boxes stacked in y, mean y on box 2's ymin
        boxes = [boxes[2], boxes[3], boxes[0], boxes[1]]
    c = region_centre(9, [1, 2], tuple(boxes), 100)
    assert c.fallback_strict and not c.fallback            # inside only with an inclusive lower bound
    assert c.divisor == c.dx
    assert c.unsafe == (c.dx == 0)


def test_member_without_pixels_is_an_error():
    pid, _, _ = ring_world()
    with pytest.raises(KitError):
        region_centres(pid, {2: [2, 3, 4, 5, 99]})
    with pytest.raises(KitError):
        region_centres(pid, {2: [2, 3, 8]})                 # ID 8 is below max but has no pixels


def wrap_world():
    """Region 5 wraps the seam: members 2 (at column 0) and 3 (at column W-1) on either side of sea 1."""
    H, W = 60, 100
    pid = np.full((H, W), 1, dtype=np.int32)
    pid[10:20, 0:10] = 2
    pid[40:50, 90:100] = 3
    return pid


def test_wrapping_region_with_fallback_is_unknown_not_unsafe():
    pid = wrap_world()
    c = region_centres(pid, {5: [2, 3]})[5]
    assert c.seam and c.fallback and c.unknown and not c.unsafe
    assert unknown_regions(pid, {5: [2, 3]}) == [5] and unsafe_regions(pid, {5: [2, 3]}) == []


def test_guard_accepts_unknown_only_with_an_identical_observed_twin():
    pid = wrap_world()
    cs = region_centres(pid, {5: [2, 3]})
    assert guard_failures(cs) == [5]                        # nothing observed: unknown counts as unsafe
    assert guard_failures(cs, cs) == []                     # identical geometry seen loading
    moved = pid.copy()
    moved[20, 0] = 2                                        # one pixel more: different engine input
    assert guard_failures(region_centres(moved, {5: [2, 3]}), cs) == [5]


def test_trap_split_makes_exactly_that_region_unsafe():
    from experiments.exp03 import trap_split, guard_failures_of
    pid, d, region_of = ring_world()
    types = d.types()
    assert guard_failures_of(pid, np.arange(d.n), region_of) == []
    out, root, (rid, p, k) = trap_split(pid, types, region_of, {}, set(), set())
    assert rid == 2 and region_of[p] == 2 and len(root) == d.n + k - 1
    assert set(root[d.n:].tolist()) == {p}
    assert guard_failures_of(out, root, region_of) == [2]
    c = region_centres(out, {2: [i for i in range(len(root)) if region_of[root[i]] == 2]})[2]
    assert c.dx == 0 and c.fallback_all


def test_trap_respects_frozen_provinces():
    from experiments.exp03 import trap_candidates
    pid, d, region_of = ring_world()
    assert list(trap_candidates(pid, d.types(), region_of, {2, 3, 4, 5})) == []


def _first_unsafe_extra(pid, types, region_of):
    from experiments.exp03 import subdivide, guard_failures_of
    n0 = len(types)
    for extra in range(1, 40):
        p2, r2 = subdivide(pid, types, extra, np.arange(n0), {}, set(), frozen=set())
        if guard_failures_of(p2, r2, region_of):
            return extra, p2, r2
    raise AssertionError("no unguarded plan hits the division in the ring world")


def test_guarded_subdivide_avoids_the_division_and_keeps_the_count():
    from experiments.exp03 import guarded_subdivide, guard_failures_of
    pid, d, region_of = ring_world()
    types = d.types()
    n0 = d.n
    extra, plain_pid, plain_root = _first_unsafe_extra(pid, types, region_of)
    bad = guard_failures_of(plain_pid, plain_root, region_of)
    assert bad                                                             # the unguarded plan hits it
    out, root, guard, moved = guarded_subdivide(pid, types, extra, {}, set(), set(), region_of)
    assert len(root) == n0 + extra
    assert guard_failures_of(out, root, region_of) == []
    assert guard and guard[0][0] in bad and all(region_of[p] == r for r, p in guard)
    assert not (root[n0:] == guard[0][1]).any()                           # the frozen parent stays whole
    kids, plain = np.bincount(root[n0:], minlength=n0), np.bincount(plain_root[n0:], minlength=n0)
    assert moved and moved == [int(p) for p in np.nonzero(kids > plain)[0]]


def test_guard_refuses_a_region_that_is_unsafe_without_splits():
    from experiments.exp03 import guarded_subdivide
    pid, d, region_of = ring_world(right_width=10)
    with pytest.raises(KitError):
        guarded_subdivide(pid, d.types(), 3, {}, set(), set(), region_of)


# ---------------------------------------------------------------- against the game install
VANILLA_DX0_INSIDE = [2, 20, 52, 62, 147, 187, 188, 197, 207, 232, 237, 276, 302]
VANILLA_UNKNOWN = [88, 95, 96, 97, 178, 180]


@pytest.fixture(scope="module")
def vanilla_centres_(ctx):
    from experiments.exp03 import region_lookup, region_members, vanilla_centres
    v = ctx.vanilla
    n0 = v.definition.n
    ro = region_lookup(v, n0)
    return np.asarray(v.pid), vanilla_centres(np.asarray(v.pid), ro), region_members(np.arange(n0), ro)


def test_vanilla_is_clean_and_its_wrapping_fallbacks_are_known(vanilla_centres_):
    _, cs, _ = vanilla_centres_
    assert [r for r, c in cs.items() if c.unsafe] == []
    assert [r for r, c in cs.items() if c.unknown] == VANILLA_UNKNOWN
    assert sum(c.fallback for c in cs.values()) == 14
    assert guard_failures(cs, cs) == []


def test_vanilla_dx_zero_regions_with_the_mean_inside_a_box_load(vanilla_centres_):
    """13 vanilla regions have dx == 0 but the mean inside a member box, and vanilla loads: the gate is real."""
    _, cs, _ = vanilla_centres_
    assert sorted(r for r, c in cs.items() if c.dx == 0 and not c.fallback) == VANILLA_DX0_INSIDE
    assert not any(cs[r].unsafe for r in VANILLA_DX0_INSIDE)


def test_pixel_membership_gate_would_wrongly_crash_vanilla_region_207(vanilla_centres_):
    """If the gate were 'the mean pixel belongs to a member', region 207 (dx 0) would crash; vanilla loads."""
    pid, cs, members = vanilla_centres_
    H = pid.shape[0]
    wrong = [r for r in VANILLA_DX0_INSIDE
             if int(pid[H - 1 - cs[r].mean[1], cs[r].mean[0]]) not in set(members[r])]
    assert wrong == [207]


def test_vanilla_region_1_rules_out_strict_lower_bound_plus_dy_division(vanilla_centres_):
    """Region 1: dx 10, dy 0, mean on a box's lower edge. Vanilla loads, so the dy test keeps the inclusive bound."""
    _, cs, _ = vanilla_centres_
    c = cs[1]
    assert (c.dx, c.dy) == (10, 0) and c.fallback_strict and not c.fallback and not c.unsafe


def test_observed_loading_pins_exact_bytes(tmp_path):
    from experiments.exp03 import OBSERVED_LOADING, mod_tree_sha256
    (tmp_path / "map").mkdir()
    (tmp_path / "map" / "a.txt").write_bytes(b"1")
    (tmp_path / "README.txt").write_text("user dir A")
    h = mod_tree_sha256(tmp_path)
    (tmp_path / "README.txt").write_text("user dir B")          # README holds machine paths: ignored
    assert mod_tree_sha256(tmp_path) == h
    (tmp_path / "map" / "a.txt").write_bytes(b"2")
    assert mod_tree_sha256(tmp_path) != h
    assert set(OBSERVED_LOADING) == {"16k", "20k", "30k"} and all(len(v) == 64 for v in OBSERVED_LOADING.values())


# ---------------------------------------------------------------- diag03 (report / main)
def test_diag03_report_vanilla_is_clean_and_tags_its_seam_regions(ctx, capsys):
    from experiments import diag03
    fails, cs = diag03.report("vanilla", None, ctx.game)
    out = capsys.readouterr().out
    assert fails == [] and len(cs) == 304
    assert "unsafe 0," in out and "unknown (wrapping + fallback) 6;" in out
    tagged = [ln for ln in out.splitlines() if "identical in vanilla, observed loading" in ln]
    assert [int(ln.split()[2]) for ln in tagged] == VANILLA_UNKNOWN
    assert "NEW" not in out and "UNSAFE" not in out


def test_diag03_main_exit_codes_and_build_root(ctx, tmp_path, capsys):
    """Exit 0 for vanilla alone; exit 1 and region 191 for EXP-03-24k found under --build-root."""
    from experiments import diag03
    from experiments.build import build_into
    from experiments.registry import resolve
    empty = tmp_path / "empty"
    empty.mkdir()
    assert diag03.main(["--build-root", str(empty)]) == 0
    capsys.readouterr()
    (exp, bid), = resolve(ctx, "EXP-03-24k")
    out = tmp_path / "builds" / bid
    out.mkdir(parents=True)
    build_into(ctx, exp, bid, out)
    assert diag03.main(["--build-root", str(tmp_path / "builds"), bid]) == 1
    text = capsys.readouterr().out
    assert "UNSAFE region 191 191-Northern Norway.txt: dx = 0" in text
    assert text.count("identical in vanilla, observed loading") == 2 * len(VANILLA_UNKNOWN)   # vanilla + 24k
    assert "NEW" not in text
    fails, _ = diag03.report(bid, out, ctx.game, diag03.report("vanilla", None, ctx.game)[1])
    assert fails == [191]


def test_diag03_tags_a_changed_seam_region_as_new(ctx, vanilla_centres_, tmp_path, capsys):
    """A wrapping region with one member dropped is still unknown but no longer matches vanilla: NEW, exit 1."""
    from experiments import diag03
    from experiments.mapdata import block_ids, find_block
    pid, _, members = vanilla_centres_
    v = ctx.vanilla
    fname = next(f for f in sorted(v.region_files) if f.startswith("88-"))
    ids = members[88]
    drop = next(m for m in ids if region_centres(pid, {88: [i for i in ids if i != m]})[88].unknown)
    text = v.region_files[fname]
    o, c = find_block(text, "provinces", 1)
    kept = [i for i in block_ids(text, "provinces", 1) if i != drop]
    new = text[:o + 1] + " " + " ".join(str(i) for i in kept) + " " + text[c:]
    d = tmp_path / "X" / "map" / "strategicregions"
    d.mkdir(parents=True)
    (d / fname).write_text(new, encoding="utf-8")
    assert diag03.main(["--build-root", str(tmp_path), "X"]) == 1
    out = capsys.readouterr().out
    assert "unknown region 88 88-Bering Sea.txt: wraps the seam" in out and "-> NEW" in out


def test_model_reproduces_the_crash_dump_numbers(ctx):
    """EXP-03-24k region 191 (Northern Norway): the values read from both crash dumps' registers."""
    from experiments.exp03 import Exp03, centres_of, region_lookup
    v = ctx.vanilla
    pid, root, _, _ = Exp03().make(v, "EXP-03-24k")
    c = centres_of(pid, root, region_lookup(v, v.definition.n))[191]
    assert c.n == 54
    assert c.mean == (3141, 1961)
    assert c.rect == (2990, 1854, 302, 170)
    assert c.dx == 0 and c.fallback_all and c.unsafe
