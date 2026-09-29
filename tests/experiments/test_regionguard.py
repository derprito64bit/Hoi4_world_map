"""P00b-f4: region-centre guard for EXP-08 / EXP-09 (synthetic maps, no game needed)."""
from types import SimpleNamespace

import numpy as np
import pytest

from experiments.common import KitError
from experiments.mapdata import x_crossings
from experiments.regioncentre import (guard_failures, guard_problems, inner_margin, mean_point, pixel_boxes,
                                      region_centres)
from experiments.regiongroup import Boxes, grow_regions


def tiles(H, W, tw, th):
    """pid of equal tw x th tiles (IDs from 1, row-major): the regular layout that puts means on box edges."""
    r, c = np.divmod(np.arange(H * W).reshape(H, W), W)
    return ((r // th) * ((W + tw - 1) // tw) + c // tw + 1).astype(np.int32)


# ---------------------------------------------------------------- the margin rule
def test_margin_matches_region_centre_and_rejects_shared_edges():
    pid = tiles(20, 60, 10, 20)                        # one row of six 10x20 tiles
    cs = region_centres(pid, {1: [1, 2], 2: [1, 2, 3], 3: [4]})
    assert cs[1].margin <= 0 and not cs[1].clear       # two equal boxes: the mean is on their shared edge
    assert cs[2].clear and cs[2].margin >= 1 and not cs[2].fallback_strict
    assert cs[3].clear                                  # a single box >= 3 px each way holds its own centre
    x0, x1, y0, y1 = (a[[1, 2, 3]] for a in pixel_boxes(pid, 7))
    mx, my = mean_point(x0, x1, y0, y1)
    assert (mx, my) == cs[2].mean and inner_margin(mx, my, x0, x1, y0, y1) == cs[2].margin


def test_guard_problems_names_failures_and_fallback_regions():
    pid = tiles(20, 60, 10, 20)
    cs = region_centres(pid, {1: [1, 2], 2: [3, 4, 5]})
    probs = guard_problems(cs, {})
    assert len(probs) == 2 and "1 regions fail" in probs[0] and "1 regions take the fallback" in probs[1]
    assert guard_failures(cs, {}) == [1]
    assert guard_problems(cs, {}, clear_ids=[2]) == [probs[0]]
    assert guard_problems(region_centres(pid, {2: [3, 4, 5]}), {}) == []


# ---------------------------------------------------------------- grouping new filler provinces
@pytest.mark.parametrize("tw,th", [(10, 10), (6, 8), (12, 5)])
def test_grow_regions_on_a_regular_grid_never_takes_the_fallback(tw, th):
    pid = tiles(90, 240, tw, th)
    ids = sorted(np.unique(pid).tolist())
    cls = {i: ("north" if (np.nonzero(pid == i)[0].mean() < 45) else "south") for i in ids}
    groups = grow_regions(pid, ids, cls, max_members=12)
    assert sorted(i for g in groups for i in g) == ids
    bx = Boxes(pid)
    cs = region_centres(pid, {k: g for k, g in enumerate(groups, 1)})
    for k, g in enumerate(groups, 1):
        assert len(g) <= 12 + 3 and len({cls[i] for i in g}) == 1
        assert bx.ok(g) and cs[k].clear and not cs[k].seam
    assert guard_failures(cs, {}) == []
    assert sum(len(g) > 1 for g in groups) >= len(groups) // 2      # real regions, not a pile of singletons
    assert groups == grow_regions(pid, ids, cls, max_members=12)    # deterministic


def test_grow_regions_never_joins_both_image_edges():
    pid = tiles(30, 30, 10, 10)                        # 3 x 3 tiles: a 9-tile region would reach col 0 and col 29
    groups = grow_regions(pid, range(1, 10), max_members=9)
    bx = Boxes(pid)
    assert all(not bx.wraps(g) for g in groups) and sorted(i for g in groups for i in g) == list(range(1, 10))


def test_grow_regions_merges_a_thin_member_that_cannot_stand_alone():
    pid = tiles(20, 40, 10, 10)                        # 8 tiles of 10x10
    pid[0, :10] = 9                                    # a 1-px-high tile: its own box cannot hold a mean
    groups = grow_regions(pid, range(1, 10), max_members=4)
    g9 = next(g for g in groups if 9 in g)
    assert len(g9) > 1 and Boxes(pid).ok(g9)
    assert all(Boxes(pid).ok(g) for g in groups)


def test_grow_regions_raises_when_nothing_can_hold_the_mean():
    pid = np.zeros((1, 40), dtype=np.int32)
    pid[0, :20], pid[0, 20:] = 1, 2                    # 1-px-high provinces only
    with pytest.raises(KitError):
        grow_regions(pid, [1, 2], max_members=4)


def test_merge_small_min_side_removes_slivers():
    from experiments.tiling import merge_small
    lab = np.full((10, 20), 0, dtype=np.int64)
    lab[:, 10:] = 1
    lab[9, :10] = 2                                    # 10 px but 1 row high
    out, n = merge_small(lab, 5)
    assert n == 3                                      # area rule alone keeps it
    out, n = merge_small(lab, 5, min_side=3)
    assert n == 2 and set(np.unique(out).tolist()) == {0, 1}


# ---------------------------------------------------------------- EXP-08 padding
def seam_world():
    """64 x 400 vanilla stand-in whose top row has different sea provinces at column 0 and W-1 (like 2287 / 5834).

    Top padding of 32 rows is then one band of padding tiles 4 (columns 0..175), 5 (176..351), 6 (352..399)."""
    H, W = 64, 400
    pid = np.zeros((H, W), dtype=np.int32)
    pid[:16, :200], pid[:16, 200:] = 1, 2
    pid[16:, :] = 3
    types = np.array([-1, 1, 1, 0], dtype=np.int8)          # sea, sea, land
    return pid, types


def test_exp08_top_padding_never_gives_vanilla_ids_and_patches_the_seam():
    from experiments.exp08 import pad_provinces, seam_straddlers, vanilla_pixel_problems, wrapped_width
    pid, types = seam_world()
    out, k = pad_provinces(pid, types, 32, 0, 4)
    assert np.array_equal(out[32:], pid) and (out[:32] >= 4).all()
    assert vanilla_pixel_problems(out, pid, 32, 4) == []
    assert len(x_crossings(out)[0]) == 0
    patch = seam_straddlers(out, range(4, 4 + k))
    assert patch == [4 + k - 1] and wrapped_width(out, patch[0]) <= 8
    assert Boxes(out).margin([patch[0]]) >= 1                  # its own region never falls back
    # with right padding the vanilla top row no longer meets the seam: no patch
    out2, k2 = pad_provinces(pid, types, 32, 32, 4)
    assert seam_straddlers(out2, range(4, 4 + k2)) == [] and len(x_crossings(out2)[0]) == 0


def test_exp08_vanilla_pixel_rule_catches_gains_and_losses():
    from experiments.exp08 import pad_provinces, vanilla_pixel_problems
    pid, types = seam_world()
    out, _ = pad_provinces(pid, types, 32, 0, 4)
    gained = out.copy()
    gained[31, 399] = 2                                 # the P00b-f3 seam rule: a padding pixel takes the ID below
    assert any("may gain pixels" in p for p in vanilla_pixel_problems(gained, pid, 32, 4))
    lost = out.copy()
    lost[40, 5] = int(out[0, 5])
    assert any("vanilla part" in p for p in vanilla_pixel_problems(lost, pid, 32, 4))


def region_text(rid, ids):
    from experiments.exp08 import region_file
    return region_file(rid, f"r{rid}", ids, "\tweather={\n\t}", "water_deep_ocean")


def stub_vanilla(pid, regions):
    return SimpleNamespace(pid=pid, province_region={p: (r, f"{r}-x.txt") for r, ids in regions.items() for p in ids})


def padded_world():
    """Vanilla stand-in: region 1 = sea 1, 2 (top), region 2 = land 3; padded by 32 rows (new seas 4..)."""
    from experiments.exp08 import pad_provinces
    pid, types = seam_world()
    out, k = pad_provinces(pid, types, 32, 0, 4)
    v = stub_vanilla(pid, {1: [1, 2], 2: [3]})
    return v, out, list(range(4, 4 + k))


def test_exp08_centre_problems_pass_for_safe_new_regions():
    from experiments.exp08 import centre_problems
    v, out, new = padded_world()
    groups = grow_regions(out, [i for i in new if i != new[-1]], max_members=3) + [[new[-1]]]
    texts = {f"{10 + k}.txt": region_text(10 + k, g) for k, g in enumerate(groups)}
    assert centre_problems(v, out, texts) == []


def test_exp08_centre_problems_catch_fallback_regions_and_moved_vanilla_centres():
    from experiments.exp08 import centre_problems
    v, out, new = padded_world()
    strip = [4, 5]                                     # two 176-px tiles side by side: mean on their shared edge
    texts = {"10.txt": region_text(10, strip), "11.txt": region_text(11, [i for i in new if i not in strip])}
    assert region_centres(out, {10: strip})[10].margin <= 0
    assert any("take the fallback" in p for p in centre_problems(v, out, texts))
    # a vanilla province gaining one padding pixel moves its region's centre calculation
    groups = grow_regions(out, [i for i in new if i != new[-1]], max_members=3) + [[new[-1]]]
    ok = {f"{10 + k}.txt": region_text(10 + k, g) for k, g in enumerate(groups)}
    gained = out.copy()
    gained[31, 399] = 2
    assert any("changed their centre calculation" in p for p in centre_problems(v, gained, ok))


def test_exp08_wider_canvas_turns_a_wrapping_dy0_region_into_a_guard_failure():
    """The EXP-08-6144 region-178 case: a vanilla region that wraps (fallback, dy 0) stops touching the new
    right edge; its members and boxes are unchanged, yet it is no longer a wrapping region -> guard failure."""
    from experiments.exp08 import centre_problems
    H, W = 60, 100
    pid = np.full((H, W), 1, dtype=np.int32)
    pid[20:30, 0:10] = 2                               # region 5: one member at column 0 ...
    pid[20:30, 90:100] = 3                             # ... one at column W-1, same rows -> dy 0, fallback
    v = stub_vanilla(pid, {4: [1], 5: [2, 3]})
    vc = region_centres(pid, {5: [2, 3]})[5]
    assert vc.seam and vc.fallback and vc.dy == 0 and guard_failures({5: vc}, {5: vc}) == []
    wide = np.full((H, W + 20), 6, dtype=np.int32)     # 20 columns of new sea at the right
    wide[:, :W] = pid
    probs = centre_problems(v, wide, {"7.txt": region_text(7, [6])})
    assert any("1 regions fail" in p and "5 (" in p for p in probs)


# ---------------------------------------------------------------- EXP-09
def test_exp09_centre_problems_reject_strips_and_accept_runs():
    from experiments.exp09 import centre_problems
    from experiments.synth import run_widths
    H, W = 40, 200
    strip = np.full((H, W), 9, dtype=np.int32)
    for k in range(4):                                 # region 1: four equal 6 x 20 bars (the old EXP-09 layout)
        strip[10:30, 20 + 6 * k:26 + 6 * k] = 1 + k
    v = stub_vanilla(strip, {1: [1, 2, 3, 4]})
    assert any("take the fallback" in p for p in centre_problems(v, strip, {"2.txt": region_text(2, [9])}))
    good = np.full((H, W), 9, dtype=np.int32)
    c = 20
    for k, w in enumerate(run_widths(4, 6)):           # the P00b-f4 run: the middle bar doubled
        good[10:30, c:c + w] = 1 + k
        c += w
    assert centre_problems(v, good, {"2.txt": region_text(2, [9])}) == []
    # a wrapping new region that takes the fallback fails even though the model cannot judge it
    wrap = good.copy()
    wrap[0:5, 0:5], wrap[35:40, W - 5:] = 7, 8
    probs = centre_problems(v, wrap, {"2.txt": region_text(2, [9]), "3.txt": region_text(3, [7, 8])})
    assert any("1 regions fail" in p and "wraps" in p for p in probs)


# ---------------------------------------------------------------- r2: documented known risk (EXP-08-6144 region 178)
def wrap_loss_world():
    """Vanilla region 5 wraps (fallback, dy 0); padded by 20 columns at the right it no longer does."""
    H, W = 60, 100
    pid = np.full((H, W), 1, dtype=np.int32)
    pid[20:30, 0:10] = 2
    pid[20:30, 90:100] = 3
    v = stub_vanilla(pid, {4: [1], 5: [2, 3]})
    wide = np.full((H, W + 20), 6, dtype=np.int32)
    wide[:, :W] = pid
    return v, wide, region_centres(pid, {5: [2, 3]})[5].signature


def test_known_risk_with_the_exact_signature_is_allowed_and_noted():
    from experiments.exp08 import centre_problems
    v, wide, sig = wrap_loss_world()
    notes = []
    probs = centre_problems(v, wide, {"7.txt": region_text(7, [6])}, known={5: (sig, "test reason")}, notes=notes)
    assert probs == []
    assert len(notes) == 1 and notes[0].startswith("KNOWN RISK (allowed): region 5 ") and "test reason" in notes[0]


def test_known_risk_never_hides_a_changed_signature_or_another_failure():
    from experiments.exp08 import centre_problems
    v, wide, sig = wrap_loss_world()
    notes = []
    probs = centre_problems(v, wide, {"7.txt": region_text(7, [6])}, known={5: ("0" * 16, "stale")}, notes=notes)
    assert notes == [] and any("1 regions fail" in p and "5 (" in p for p in probs)
    # the member boxes change (a vanilla pixel moves): signature and centre path differ -> fails
    moved = wide.copy()
    moved[30, 0:10] = 2
    probs = centre_problems(v, moved, {"7.txt": region_text(7, [6])}, known={5: (sig, "r")}, notes=notes)
    assert notes == [] and any("changed their centre calculation" in p for p in probs)
    assert any("1 regions fail" in p for p in probs)
    # an allowance for another region does not cover region 5
    probs = centre_problems(v, wide, {"7.txt": region_text(7, [6])}, known={4: (sig, "wrong region")}, notes=notes)
    assert notes == [] and any("1 regions fail" in p for p in probs)


def test_split_known_matches_region_and_signature():
    from experiments.regioncentre import split_known
    pid = tiles(20, 60, 10, 20)
    cs = region_centres(pid, {1: [1, 2], 2: [3, 4]})
    assert guard_failures(cs, {}) == [1, 2]
    rest, notes = split_known([1, 2], cs, {1: (cs[1].signature, "why"), 2: (cs[1].signature, "wrong sig")})
    assert rest == [2] and len(notes) == 1 and "region 1 " in notes[0]


def test_exp08_known_risk_is_only_region_178_in_6144():
    from experiments.exp08 import KNOWN_RISK
    assert set(KNOWN_RISK) == {"EXP-08-6144x2560"} and set(KNOWN_RISK["EXP-08-6144x2560"]) == {178}


def test_exp08_readmes_ask_for_the_crash_lines():
    """r3: both EXP-08 READMEs ask for the crash lines; 5632 names its second property (seam province 13511)."""
    from experiments.exp08 import Exp08
    info = {"top": 512, "right": 512, "new": 148, "newly_coastal": [], "seam_patch": [],
            "wrap_lost": [88, 95, 96, 97, 178, 180]}
    ctx = SimpleNamespace(user=None)
    r = Exp08().readme(ctx, "EXP-08-6144x2560", info)
    r2 = Exp08().readme(ctx, "EXP-08-5632x2560", dict(info, right=0, seam_patch=[13511], wrap_lost=[]))
    for text in (r, r2):
        assert "Unhandled Exception" in text and "exception.txt" in text and "crashes/" in text
        assert "Loaded N provinces" in text
    assert "+0x15A4CDC" in r and "NOT the map size" in r and "88, 95, 96, 97, 178, 180" in r
    assert "THE ONE THING" in r and "13511" not in r
    assert "THE TWO THINGS" in r2 and "1. The map canvas" in r2 and "2. Sea province 13511" in r2
    assert "TOO LARGE BOX" in r2 and "'BOX' or '13511'" in r2
    assert "may come from province 13511 rather than from the map size" in r2
