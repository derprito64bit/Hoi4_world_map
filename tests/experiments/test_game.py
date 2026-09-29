"""Builds against the real game install (skipped without it): --check passes on a fresh build and
fails when anything beyond the intended property is touched."""
import re

import pytest

from experiments.build import build_into
from experiments.registry import resolve


def build(ctx, tmp_path, sel):
    (exp, bid), = resolve(ctx, sel)
    out = tmp_path / bid
    out.mkdir()
    build_into(ctx, exp, bid, out)
    return exp, bid, out


@pytest.mark.parametrize("sel", ["EXP-01-UK-A", "EXP-01-UK-B", "EXP-01-SEAM-A", "EXP-01-SEAM-B", "EXP-02-300",
                                 "EXP-05-2to1", "EXP-06", "EXP-07"])
def test_fresh_build_passes_check(ctx, tmp_path, sel):
    exp, bid, out = build(ctx, tmp_path, sel)
    assert exp.check(ctx, bid, out) == []


def test_check_catches_an_extra_line(ctx, tmp_path):
    exp, bid, out = build(ctx, tmp_path, "EXP-01-UK-B")
    p = out / "map" / "adjacencies.csv"
    p.write_bytes(p.read_bytes().replace(b"\n-1;-1;", b"\n1;2;;-1;-1;-1;-1;-1;;extra\n-1;-1;", 1))
    assert exp.check(ctx, bid, out)


def test_check_catches_an_extra_file(ctx, tmp_path):
    exp, bid, out = build(ctx, tmp_path, "EXP-05-3to1")
    (out / "map" / "rivers.bmp").write_bytes(b"x")
    assert any("unexpected files" in p for p in exp.check(ctx, bid, out))


def test_check_catches_a_changed_pixel(ctx, tmp_path):
    exp, bid, out = build(ctx, tmp_path, "EXP-05-2to1")
    p = out / "map" / "trees.bmp"
    b = bytearray(p.read_bytes())
    b[-10] = (b[-10] + 1) % 256
    p.write_bytes(bytes(b))
    assert exp.check(ctx, bid, out)


def test_check_catches_a_touched_state(ctx, tmp_path):
    exp, bid, out = build(ctx, tmp_path, "EXP-07")
    p = next((out / "history" / "states").glob("1-*.txt"))
    p.write_bytes(p.read_bytes() + b"\n")
    assert any("changed" in x for x in exp.check(ctx, bid, out))


def test_exp01_pair_is_valid_in_this_game(ctx):
    from experiments.exp01 import Exp01
    assert Exp01().verify_pair(ctx.vanilla) >= 5


def test_exp07_finds_all_script_references(ctx):
    from experiments.exp07 import NEW, OLD, Exp07, renumber_state_refs
    edits = Exp07().script_edits(ctx.vanilla)
    assert edits
    for rel, text in edits.items():
        _, n, left = renumber_state_refs(text, OLD, NEW)
        assert n == 0 and left == 0, rel                 # no reference to state 1081 left behind


def test_exp09_real_manifest_patches_apply(ctx):
    from experiments.exp09 import Exp09
    e = Exp09()
    for bid in e.build_ids(ctx):
        files = e.variant_files(ctx, bid)
        for rel in files:
            assert rel.startswith(("common/defines/zz_", "gfx/FX/"))


def test_exp01_seam_pair_straddles_the_wrap_seam(ctx):
    from experiments.exp01 import Exp01
    assert Exp01().verify_pair(ctx.vanilla, "SEAM") >= 5


@pytest.fixture(scope="module")
def exp08_build(ctx, tmp_path_factory):
    exp, bid, out = build(ctx, tmp_path_factory.mktemp("e8"), "EXP-08-5632x2560")
    assert exp.check(ctx, bid, out) == []
    return exp, bid, out


@pytest.mark.parametrize("rel,extra", [
    ("map/buildings.txt", "1;naval_base_spawn;2946.50;9.50;1364.50;0.00;13500"),     # extra coastal line
    ("map/unitstacks.txt", "13500;0;10.50;9.50;2500.50;0.00;0.20"),                   # duplicate stack type
    ("map/weatherpositions.txt", "305;10.50;9.50;2500.50;big"),                       # second line, same region
])
def test_exp08_check_catches_extra_appended_lines(ctx, exp08_build, rel, extra):
    exp, bid, out = exp08_build
    p = out / rel
    orig = p.read_bytes()
    try:
        p.write_bytes(orig + extra.encode() + b"\n")
        assert exp.check(ctx, bid, out)
    finally:
        p.write_bytes(orig)
    assert exp.check(ctx, bid, out) == []


@pytest.fixture(scope="module")
def exp09_builds(ctx, tmp_path_factory):
    from experiments.exp09 import Exp09
    e = Exp09()
    root = tmp_path_factory.mktemp("e9")
    outs = {}
    for bid in (e.build_ids(ctx)[0], e.build_ids(ctx)[-1]):
        out = root / bid
        out.mkdir()
        build_into(ctx, e, bid, out)
        outs[bid] = out
    return e, outs


# landmark state -> (cols, rows) of its bars in the pre-f4 EXP-09 builds (2026-09-28): the doubled middle bar
# of P00b-f4 must never move a landmark
LANDMARK_BOXES = {822: ((4323, 4346), (148, 167)), 463: ((764, 853), (153, 172)),
                  101: ((2162, 2191), (19, 38)), 953: ((1680, 1697), (2226, 2245))}


def test_exp09_landmarks_keep_their_pre_f4_pixels(ctx, exp09_builds):
    import numpy as np
    from experiments.exp09 import ANCHORS
    e, outs = exp09_builds
    pid, _ = _pid_of(list(outs.values())[0])
    states = {}
    for p, (sid, _) in ctx.vanilla.province_state.items():
        states.setdefault(sid, []).append(p)
    assert set(LANDMARK_BOXES) == {a[0] for a in ANCHORS}
    for sid, ((c0, c1), (r0, r1)) in LANDMARK_BOXES.items():
        ys, xs = np.nonzero(np.isin(pid, states[sid]))
        assert (xs.min(), xs.max(), ys.min(), ys.max()) == (c0, c1, r0, r1), sid
        assert len(xs) == (c1 - c0 + 1) * (r1 - r0 + 1), sid        # one solid run, no gap, no doubled bar outside


def test_exp09_readme_names_the_region_count_as_a_rival_cause(ctx, exp09_builds):
    e, outs = exp09_builds
    info = e.layout_info
    text = (list(outs.values())[0] / "README.txt").read_text(encoding="utf-8")
    cannot = text.split("WHAT THIS TEST CANNOT PROVE", 1)[1]
    assert f"{info['regions']} strategic regions (the normal game: {info['regions_vanilla']})" in cannot
    assert f"{info['regions_single']} of them hold a single province" in cannot and "rival causes" in cannot


def test_exp09_fresh_builds_pass_and_share_the_base(ctx, exp09_builds):
    e, outs = exp09_builds
    for bid, out in outs.items():
        assert e.check(ctx, bid, out) == [], bid
    a, z = list(outs.values())
    extra = set(e.variant_files(ctx, list(outs)[-1]))
    for p in sorted(a.rglob("*")):
        rel = p.relative_to(a).as_posix()
        if p.is_file() and rel not in ("README.txt", "descriptor.mod") and rel not in extra:
            assert (z / rel).read_bytes() == p.read_bytes(), rel


def test_exp09_check_catches_a_different_base_file(ctx, exp09_builds):
    e, outs = exp09_builds
    bid, out = list(outs.items())[-1]
    p = out / "map" / "heightmap.bmp"
    orig = p.read_bytes()
    b = bytearray(orig)
    b[-100] = (b[-100] + 1) % 256
    try:
        p.write_bytes(bytes(b))
        assert any("shared by all variants" in x for x in e.check(ctx, bid, out))
    finally:
        p.write_bytes(orig)


def _warm(b):
    return b.replace(b"arctic_water=1.000", b"arctic_water=0.000").replace(b"temperature={ -20.0", b"temperature={ 5.0")


def _no_snow(b):
    return re.sub(rb"(?<![\w])snow=[\d.]+", b"snow=0.000", b)


def _no_arctic(b):
    return b.replace(b"arctic_water=1.000", b"arctic_water=0.000")


@pytest.mark.parametrize("spoil", [_warm, _no_snow, _no_arctic], ids=["warm", "no-snow", "no-arctic-water"])
def test_exp09_check_catches_filler_without_snow_and_arctic_water(ctx, exp09_builds, spoil):
    """The northern filler must have winter snow AND arctic water; losing either one fails --check."""
    e, outs = exp09_builds
    bid, out = list(outs.items())[0]
    # P00b-f4: the filler is split into several compact regions per quadrant; spoil every northern one
    # (Chukotka is in the NE, Alaska in the NW quadrant)
    ps = sorted((out / "map" / "strategicregions").glob("*off-globe N*.txt"))
    origs = {p: p.read_bytes() for p in ps}
    assert any("off-globe NE" in p.name for p in ps) and any("off-globe NW" in p.name for p in ps)
    for orig in origs.values():
        assert re.search(rb"(?<![\w])snow=0\.[1-9]", orig) and b"arctic_water=1.000" in orig
    try:
        for p, orig in origs.items():
            p.write_bytes(spoil(orig))
        assert any("icy winter weather" in x for x in e.check(ctx, bid, out))
    finally:
        for p, orig in origs.items():
            p.write_bytes(orig)


# ---------------------------------------------------------------- P00b-f4 region-centre guard
def _pid_of(out):
    from experiments.bmpio import read_bmp
    from experiments.common import decode
    from experiments.mapdata import Definition, pid_from_rgb
    d = Definition.parse(decode((out / "map/definition.csv").read_bytes()))
    return pid_from_rgb(read_bmp((out / "map/provinces.bmp").read_bytes()).pixels, d.colors()), d


def _split_off_a_strip(out, pid):
    """Split a new region into a strip pair (two 4-neighbours whose mean sits on a box edge) and the rest (a new
    region file), so every province stays in exactly one region. Returns a restore function."""
    from experiments.common import decode
    from experiments.exp08 import region_file
    from experiments.mapdata import block_ids
    from experiments.regiongroup import Boxes, neighbours
    bx = Boxes(pid)
    files = sorted((out / "map" / "strategicregions").glob("*.txt"))
    rid_of = {f: int(re.search(rb"\bid=(\d+)", f.read_bytes()).group(1)) for f in files}
    weather = "\tweather={\n\t}"
    for f in files:
        orig = f.read_bytes()
        ids = block_ids(decode(orig), "provinces")
        nb = neighbours(pid, ids)
        pair = next(([a, b] for a in sorted(nb) for b in nb[a] if a < b and bx.margin([a, b]) <= 0), None)
        if pair is None or len(ids) < 3:
            continue
        new_id = max(rid_of.values()) + 1
        extra = f.parent / f"{new_id}-test rest.txt"
        f.write_bytes(region_file(rid_of[f], "test strip", pair, weather, "water_deep_ocean").encode())
        extra.write_bytes(region_file(new_id, "test rest", [i for i in ids if i not in pair], weather,
                                      "water_deep_ocean").encode())

        def restore():
            f.write_bytes(orig)
            extra.unlink()
        return restore
    raise AssertionError("no new region holds a strip pair")


def test_exp08_check_catches_a_vanilla_province_gaining_padding_pixels(ctx, exp08_build):
    from experiments.bmpio import read_bmp, write_bmp
    exp, bid, out = exp08_build
    p = out / "map" / "provinces.bmp"
    orig = p.read_bytes()
    b = read_bmp(orig)
    px = b.pixels.copy()
    px[511, 100] = px[512, 100]                    # the padding pixel above the old top edge takes the ID below
    try:
        p.write_bytes(write_bmp(b, px))
        probs = exp.check(ctx, bid, out)
        assert any("may gain pixels" in x for x in probs)
        assert any("changed their centre calculation" in x for x in probs)
    finally:
        p.write_bytes(orig)
    assert exp.check(ctx, bid, out) == []


def test_exp08_check_catches_a_new_region_on_the_fallback_path(ctx, exp08_build):
    exp, bid, out = exp08_build
    pid, _ = _pid_of(out)
    restore = _split_off_a_strip(out, pid)
    try:
        assert any("region-centre guard" in x and "take the fallback" in x for x in exp.check(ctx, bid, out))
    finally:
        restore()
    assert exp.check(ctx, bid, out) == []


def test_exp09_check_catches_a_region_on_the_fallback_path(ctx, exp09_builds):
    e, outs = exp09_builds
    bid, out = list(outs.items())[0]
    pid, _ = _pid_of(out)
    restore = _split_off_a_strip(out, pid)
    try:
        assert any("region-centre guard" in x and "take the fallback" in x for x in e.check(ctx, bid, out))
    finally:
        restore()
    assert e.check(ctx, bid, out) == []


def test_exp08_known_risk_signature_is_vanilla_region_178(ctx):
    """The allowance matches vanilla's own member boxes of region 178 (unchanged in the 6144 build)."""
    from experiments.exp08 import KNOWN_RISK, vanilla_centres
    assert vanilla_centres(ctx.vanilla)[178].signature == KNOWN_RISK["EXP-08-6144x2560"][178][0]
