"""P00b-f7: naval-region contiguity as a kit-wide --check rule, and EXP-09 regions that stay one piece."""
import re
import shutil

import numpy as np
import pytest

from experiments import naval
from experiments.boxfill import fractioned_parts
from experiments.common import KitError, decode, encode
from experiments.mapdata import SEA
from experiments.regiongroup import Boxes, connected, grow_regions, neighbours

# error.log of the owner's EXP-09a run (2026-09-30 15:45, -debug), gamestate.cpp:2703, verbatim:
# "MAP_ERROR: Naval strategic region <name> is fractioned! The following provinces are separated from the rest:"
EXP09A_GAME_LOG = {
    "EXP-09 extra sea 37 (south)": [*range(14531, 14544), 14566, 14649, 14650, 14651, 14652],
    "EXP-09 extra sea 58 (south)": [15258, 15259],
    "EXP-09 extra sea 70 (south)": [15620, 15621],
    "EXP-09 extra sea 71 (south)": [*range(15696, 15706)],
    "EXP-09 extra sea 89 (south)": [16130],
    "EXP-09 extra sea 105 (south)": [16390],
}


def voronoi(seed, H=40, W=60, k=25):
    """Deterministic irregular tiling (convex cells: every province is one piece)."""
    rng = np.random.default_rng(seed)
    pts = np.stack([rng.integers(0, H, k), rng.integers(0, W, k)], 1)
    yy, xx = np.mgrid[:H, :W]
    d = (yy[..., None] - pts[:, 0]) ** 2 + (xx[..., None] - pts[:, 1]) ** 2
    return (d.argmin(-1) + 1).astype(np.int32)


# ---------------------------------------------------------------- grow_regions keeps every region one piece
def test_grow_regions_keeps_regions_connected_where_the_old_grouping_cut_them():
    cut = fixed = 0
    for seed in range(200):
        pid = voronoi(seed)
        ids = sorted(np.unique(pid).tolist())
        nb = neighbours(pid, ids)
        try:
            old = grow_regions(pid, ids, max_members=8, keep_connected=False)
        except KitError:
            old = None
        try:
            new = grow_regions(pid, ids, max_members=8)
        except KitError:
            continue
        bx = Boxes(pid)
        assert sorted(i for g in new for i in g) == ids
        assert all(connected(g, nb) and bx.ok(g) for g in new), seed
        assert new == grow_regions(pid, ids, max_members=8)                     # deterministic
        if old is not None and any(not connected(g, nb) for g in old):
            cut += 1                                                            # the old grouping cut one here
            fixed += 1
    assert cut >= 3 and fixed == cut    # the pre-f7 grouping (drop the farthest member) cuts regions on such maps


def test_connected_helper():
    nb = {1: [2], 2: [1, 3], 3: [2], 4: []}
    assert connected([1, 2, 3], nb) and connected([4], nb) and connected([], nb)
    assert not connected([1, 3], nb) and not connected([1, 4], nb)


# ---------------------------------------------------------------- the rule and its verdicts (no game)
def test_separated_are_the_pieces_without_the_lowest_id():
    """The engine keeps the piece of the lowest ID even when it is the smaller one (EXP-09a region 37)."""
    pid = np.zeros((4, 30), dtype=np.int32)
    pid[:, :10], pid[:, 10:12], pid[:, 12:] = 1, 9, 2          # 1 | land 9 | 2 (the bigger piece)
    pid[:, 29] = 9                                             # and no contact across the wrap
    types = np.array([-1, SEA, SEA, 0, 0, 0, 0, 0, 0, 0])
    pr = {1: (7, "7-a.txt"), 2: (7, "7-a.txt")}
    assert fractioned_parts(pid, pr, types) == {7: [2]}
    assert naval.findings(pid, types, pr) == {"a": [2]}
    assert naval.findings(pid, types, pr, {7: "Sea A"}) == {"Sea A": [2]}


def test_judge_fails_new_findings_and_notes_documented_ones():
    found = {"Sea A": [2, 3]}
    assert naval.judge("EXP-XX", {}, {}) == ([], [])
    probs, notes = naval.judge("EXP-XX", found, {})
    assert notes == [] and len(probs) == 1 and "'Sea A' is fractioned" in probs[0] and "[2, 3]" in probs[0]
    known = {"why": "concluded", "regions": {"Sea A": [2, 3]}}
    probs, notes = naval.judge("EXP-XX", found, known)
    assert probs == [] and len(notes) == 1 and "expected finding (concluded)" in notes[0]
    probs, _ = naval.judge("EXP-XX", {"Sea A": [2]}, known)                  # a different finding fails
    assert any("does not match" in p for p in probs)
    probs, _ = naval.judge("EXP-XX", {}, known)                              # and so does none at all
    assert any("does not match" in p for p in probs)


def test_registry_documents_only_concluded_builds():
    from experiments.registry import CONCLUDED, KNOWN_FRACTIONED, RETIRED
    assert set(KNOWN_FRACTIONED) <= set(CONCLUDED)
    assert not set(CONCLUDED) & set(RETIRED)
    assert {"EXP-02b-block-400", "EXP-08-5632x2560", "EXP-08-6144x2560"} <= set(CONCLUDED)
    assert not [b for b in CONCLUDED if b.startswith("EXP-09")]
    for k in KNOWN_FRACTIONED.values():
        assert k["why"] and all(ids == sorted(ids) and ids for ids in k["regions"].values())


def test_region_name_and_loc_lines():
    assert naval.region_name("88-Bering Sea.txt") == "Bering Sea"
    assert naval.region_name("305-EXP-09 extra sea 1 (north).txt") == "EXP-09 extra sea 1 (north)"
    t = '﻿l_english:\n STRATEGICREGION_95: "West Emperor Chain"\n STRATEGICREGION_305:0 "EXP-09 x"\n'
    assert {int(k): v for k, v in naval.LOC_LINE.findall(t)} == {95: "West Emperor Chain", 305: "EXP-09 x"}


# ---------------------------------------------------------------- with the game install
def test_vanilla_is_clean_and_named_as_in_game(ctx):
    v = ctx.vanilla
    assert naval.build_findings(None, ctx.game) == {}
    loc = naval.loc_names(None, ctx.game)
    assert loc[88] == "Bering Sea" and loc[95] == "West Emperor Chain" and loc[96] == "North Emperor Chain"
    assert naval.build_findings(None, ctx.game, v) == {}


@pytest.fixture(scope="module")
def old_exp09(ctx):
    """The pre-f7 EXP-09 layout (the regions of the owner's EXP-09a run): same pixels, old grouping."""
    from experiments.exp09 import REGION_CHUNK, Exp09
    from experiments.synth import Params
    return Exp09().make_layout(ctx.vanilla, Params(region_max=REGION_CHUNK, connected_regions=False))


def _new_sea_regions(v, lay):
    rid = max(r for r, _ in v.province_region.values()) + 1
    pr = dict(v.province_region)
    for k, (side, ids) in enumerate(lay.sea_regions, 1):
        for i in ids:
            pr[i] = (rid, f"{rid}-EXP-09 extra sea {k} ({side}).txt")
        rid += 1
    return pr


def test_rule_reproduces_the_six_exp09a_game_failures(ctx, old_exp09):
    """EXP-09a (2026-09-30): exactly these 6 regions, exactly these separated provinces."""
    lay, types = old_exp09
    assert naval.findings(lay.pid, types, _new_sea_regions(ctx.vanilla, lay)) == EXP09A_GAME_LOG


def test_fixed_exp09_has_no_fractioned_region_and_the_same_pixels(ctx, old_exp09):
    from experiments.exp09 import Exp09, naval_findings
    exp = Exp09()
    files = exp.shared_files(ctx)
    lay, types = exp.make_layout(ctx.vanilla)
    assert np.array_equal(lay.pid, old_exp09[0].pid)          # only the grouping changed: landmarks, filler kept
    assert naval_findings(ctx.vanilla, lay.pid, types, {k: decode(d) for k, d in files.items()
                                                        if k.startswith("map/strategicregions/")}) == {}
    assert naval.findings(lay.pid, types, _new_sea_regions(ctx.vanilla, lay)) == {}
    nb = neighbours(lay.pid, lay.off_ids)
    assert all(connected(g, nb) for _, g in lay.off_regions)  # the filler regions are one piece too


def test_block400_and_exp08_findings_match_the_documented_record(ctx, tmp_path):
    """The concluded builds' findings, by engine name, equal registry.KNOWN_FRACTIONED; EXP-08-5632 is clean."""
    from experiments.build import build_into
    from experiments.registry import KNOWN_FRACTIONED, resolve
    for bid in ("EXP-02b-block-400", "EXP-08-6144x2560", "EXP-08-5632x2560"):
        (exp, _), = resolve(ctx, bid)
        out = tmp_path / bid
        out.mkdir()
        build_into(ctx, exp, bid, out)
        found = naval.build_findings(out, ctx.game, ctx.vanilla)
        want = KNOWN_FRACTIONED.get(bid, {"regions": {}})["regions"]
        assert found == want, bid
        probs, notes = naval.check_build(ctx, exp, bid, out)
        assert probs == [] and len(notes) == (1 if want else 0)
        shutil.rmtree(out)
    # the names the game logged for EXP-08-6144 (2026-09-30 15:41: "Bering Sea, West Emperor Chain, North
    # Emperor Chain, ...") are the first three by region id
    assert {"Bering Sea", "West Emperor Chain", "North Emperor Chain"} <= set(KNOWN_FRACTIONED["EXP-08-6144x2560"]
                                                                              ["regions"])
    assert KNOWN_FRACTIONED["EXP-02b-block-400"]["regions"] == {
        "North East Pacific": [2378, 2404, 2452, 2503, 2551, 2627, 2650, 2676, 2701, 2779],
        "Central North Pacific": [263, 460, 644, 2144, 2252, 2278, 2305, 8583, 9029, 9086]}


def _cut_region_build(ctx, out):
    """A build folder with two vanilla region files changed: one sea province of 'A' moved to a far region 'B'."""
    v = ctx.vanilla
    fa = next(f for f in sorted(v.region_files) if f.startswith("88-"))          # Bering Sea
    fb = next(f for f in sorted(v.region_files) if f.startswith("32-"))          # Southern Ocean
    sea_b = sorted(p for p, (_, f) in v.province_region.items() if f == fb and v.types[p] == SEA)
    pid = np.asarray(v.pid)
    for moved in reversed(sea_b):                 # one whose removal leaves the Southern Ocean in one piece
        pr = dict(v.province_region)
        pr[moved] = v.province_region[next(p for p, (_, f) in v.province_region.items() if f == fa)]
        if set(fractioned_parts(pid, pr, v.types)) == {88}:
            break
    ta = v.region_files[fa].replace("provinces={", f"provinces={{ {moved}", 1)
    tb = re.sub(rf"(?<!\d){moved}(?!\d)", "", v.region_files[fb], count=1)
    d = out / "map" / "strategicregions"
    d.mkdir(parents=True)
    (d / fa).write_bytes(encode(ta))
    (d / fb).write_bytes(encode(tb))
    return moved


def test_every_build_check_runs_the_rule(ctx, tmp_path, capsys):
    """build.py --check applies the rule to any build, whatever its experiment's own check says."""
    from experiments import build as bld
    from experiments.registry import resolve
    (exp, bid), = resolve(ctx, "EXP-01-UK-A")
    out = tmp_path / bid
    out.mkdir()
    bld.build_into(ctx, exp, bid, out)
    assert bld.kit_rules(ctx, exp, bid, out) == ([], [])
    moved = _cut_region_build(ctx, out)
    probs, notes = bld.kit_rules(ctx, exp, bid, out)
    assert notes == [] and len(probs) == 1
    assert "'Bering Sea' is fractioned" in probs[0] and f"[{moved}]" in probs[0]
    assert bld.check_one(ctx, exp, bid, tmp_path) is False
    assert "'Bering Sea' is fractioned" in capsys.readouterr().out
