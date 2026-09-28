"""Builds against the real game install (skipped without it): --check passes on a fresh build and
fails when anything beyond the intended property is touched."""
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


def test_exp09_check_catches_warm_weather_at_the_ice_landmarks(ctx, exp09_builds):
    e, outs = exp09_builds
    bid, out = list(outs.items())[0]
    p = next((out / "map" / "strategicregions").glob("*off-globe NE.txt"))
    orig = p.read_bytes()
    try:
        p.write_bytes(orig.replace(b"arctic_water=1.000", b"arctic_water=0.000").replace(b"temperature={ -20.0",
                                                                                       b"temperature={ 5.0"))
        assert any("icy winter weather" in x for x in e.check(ctx, bid, out))
    finally:
        p.write_bytes(orig)
