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


@pytest.mark.parametrize("sel", ["EXP-01A", "EXP-01B", "EXP-02-300", "EXP-05-2to1", "EXP-06", "EXP-07"])
def test_fresh_build_passes_check(ctx, tmp_path, sel):
    exp, bid, out = build(ctx, tmp_path, sel)
    assert exp.check(ctx, bid, out) == []


def test_check_catches_an_extra_line(ctx, tmp_path):
    exp, bid, out = build(ctx, tmp_path, "EXP-01B")
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
