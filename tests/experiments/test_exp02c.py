"""EXP-02c: TOO LARGE BOX probes against the game install (skipped without it)."""
import numpy as np
import pytest

from experiments.mapdata import SEA

ALL = ["EXP-02c-land-440x150", "EXP-02c-sea-70x440", "EXP-02c-land-150x300", "EXP-02c-sea-L-330x480"]


@pytest.fixture(scope="module")
def built(ctx, tmp_path_factory):
    from experiments.build import build_into
    from experiments.registry import resolve
    root = tmp_path_factory.mktemp("e2c")
    outs = {}
    for bid in ALL:
        (exp, b), = resolve(ctx, bid)
        out = root / b
        out.mkdir()
        info = build_into(ctx, exp, b, out)
        outs[b] = (exp, out, info)
    return outs


def test_selector_picks_the_four_probes_in_run_order(ctx):
    from experiments.registry import resolve
    assert [b for _, b in resolve(ctx, "EXP-02c")] == ALL
    assert not set(ALL) & {b for _, b in resolve(ctx, "EXP-02b")}


@pytest.mark.parametrize("bid", ALL)
def test_fresh_build_passes_check(ctx, built, bid):
    exp, out, info = built[bid]
    assert exp.check(ctx, bid, out) == []
    from experiments.exp02c import patterns
    assert info["predictions"] == {c: p[bid] for c, (_, p) in patterns().items()}


@pytest.mark.parametrize("bid", ["EXP-02c-sea-70x440", "EXP-02c-sea-L-330x480"])
def test_rebuild_is_byte_identical(ctx, built, tmp_path, bid):
    from experiments.build import build_into
    from experiments.common import sha256_tree
    exp, out, _ = built[bid]
    again = tmp_path / bid
    again.mkdir()
    build_into(ctx, exp, bid, again)
    assert sha256_tree(again) == sha256_tree(out)


@pytest.mark.parametrize("bid", ALL)
def test_readme_asks_for_debug_and_explains_every_outcome(ctx, built, bid):
    from experiments.exp02c import PROBES
    exp, out, info = built[bid]
    r = (out / "README.txt").read_text(encoding="utf-8")
    p = PROBES[bid]
    for part in ("-debug is REQUIRED", "TOO LARGE BOX", "fractioned", f"'{p.host}'", "C1:", "C2:", "C3:", "C4:",
                 "Any other pattern", f"{p.w} x {p.h}", "no enclaves", "BBOX_MAX", "touches"):
        assert part in r, part
    assert "WITHOUT -debug" not in r


def _edit_pid(ctx, out, fn):
    from experiments.bmpio import read_bmp, write_bmp
    from experiments.mapdata import pid_from_rgb, rgb_from_pid
    p = out / "map" / "provinces.bmp"
    orig = p.read_bytes()
    bmp = read_bmp(orig)
    colors = ctx.vanilla.definition.colors()
    pid = pid_from_rgb(bmp.pixels, colors)
    fn(pid)
    p.write_bytes(write_bmp(bmp, rgb_from_pid(pid, colors), keep_tail=True))
    return p, orig


def _neg(ctx, built, bid, fn, *needles):
    exp, out, _ = built[bid]
    p, orig = _edit_pid(ctx, out, fn)
    try:
        probs = exp.check(ctx, bid, out)
        for needle in needles:
            assert any(needle in x for x in probs), (needle, probs)
    finally:
        p.write_bytes(orig)
    assert exp.check(ctx, bid, out) == []


def test_check_catches_an_enclave(ctx, built):
    from experiments.exp02c import PROBES
    bid = "EXP-02c-land-440x150"
    r = PROBES[bid].shape[0]
    van = np.asarray(ctx.vanilla.pid)

    def fn(pid):                           # one inner donor pixel of the rectangle goes back to its donor
        sub = van[r.r0 + 1:r.r0 + r.h - 1, r.c0 + 1:r.c0 + r.w - 1]
        ys, xs = np.nonzero(sub != PROBES[bid].host)
        k = len(ys) // 2
        y, x = r.r0 + 1 + int(ys[k]), r.c0 + 1 + int(xs[k])
        pid[y, x] = van[y, x]
    _neg(ctx, built, bid, fn, "is not filled by host")


def test_check_catches_a_disconnected_donor(ctx, built):
    from experiments.exp02c import PROBES, donor_problems
    bid = "EXP-02c-sea-70x440"
    probe = PROBES[bid]
    exp, out, info = built[bid]
    van = np.asarray(ctx.vanilla.pid)

    def cut(pid):                          # the host takes a full column through a donor's outside part
        for d in info["donors"]:
            ys, xs = np.nonzero(pid == d)
            col = int(np.median(xs))
            trial = pid.copy()
            trial[(trial == d) & (np.arange(pid.shape[1])[None, :] == col)] = probe.host
            if any("is disconnected" in x for x in donor_problems(van, trial, [d])):
                pid[:] = trial
                return
        raise AssertionError("no donor could be cut")
    _neg(ctx, built, bid, cut, "is disconnected", "outside the shape")


@pytest.fixture(scope="module")
def pid400(ctx):
    from experiments.exp02b import Exp02b
    from experiments.mapdata import LAND
    return Exp02b().make_blocks(ctx.vanilla, 400, (LAND, SEA))[0]


def test_check_catches_a_fractioned_naval_region(ctx, built, pid400):
    """The real negative: EXP-02b-block-400's map, which the game refused for exactly these two regions."""
    from experiments.exp02c import whole_map_problems
    v = ctx.vanilla
    probs = whole_map_problems(v, np.asarray(v.pid), pid400)
    assert any("fractioned" in x and "[115, 176]" in x for x in probs), probs

    def fn(pid):                           # put block-400's map into a probe build: --check must refuse it
        pid[:] = pid400
    _neg(ctx, built, "EXP-02c-sea-L-330x480", fn, "fractioned", "outside the shape")


def test_block400_fractioned_parts_match_the_game_log(ctx, pid400):
    """error.log 2026-09-29 23:02 (-debug) listed these separated provinces for the two regions."""
    from experiments.boxfill import fractioned_parts
    v = ctx.vanilla
    assert fractioned_parts(pid400, v.province_region, v.types) == {
        115: [2378, 2404, 2452, 2503, 2551, 2627, 2650, 2676, 2701, 2779],
        176: [263, 460, 644, 2144, 2252, 2278, 2305, 8583, 9029, 9086]}


def test_vanilla_has_no_fractioned_naval_region(ctx):
    from experiments.boxfill import fractioned_naval, naval_regions
    v = ctx.vanilla
    assert len(naval_regions(v.province_region, v.types)) == 98
    assert fractioned_naval(np.asarray(v.pid), v.province_region, v.types) == set()


def test_pinned_vanilla_boxes_match_the_game(ctx):
    from experiments.boxrules import OBSERVED
    from experiments.diag02 import measure, vanilla_maxima
    v = ctx.vanilla
    pid = np.asarray(v.pid)
    pins = [b for b in OBSERVED if b.label == "vanilla"]
    got = measure(pid, v.definition, [b.pid for b in pins], "vanilla", False)
    assert [(g.x0, g.x1, g.y0, g.y1, g.pixels, g.kind) for g in got] == \
        [(b.x0, b.x1, b.y0, b.y1, b.pixels, b.kind) for b in pins]
    holders = {i for _, (_, i) in vanilla_maxima(pid, v.definition).items()}
    assert holders <= {b.pid for b in pins}              # every metric's vanilla maximum is pinned


def test_probe_sites_are_the_first_valid_ones(ctx):
    """PROBES were found with find_site; re-running the search reproduces them (the cheap ones)."""
    from experiments.exp02c import PROBES, find_site
    from experiments.mapdata import LAND
    for bid, kind, w, h in (("EXP-02c-land-440x150", LAND, 440, 150), ("EXP-02c-sea-70x440", SEA, 70, 440)):
        assert find_site(ctx.vanilla, kind, w, h, step=2) == (PROBES[bid].shape, PROBES[bid].host)
