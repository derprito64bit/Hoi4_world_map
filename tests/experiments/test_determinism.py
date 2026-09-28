"""Same input -> identical bytes."""
import numpy as np

from experiments.common import sha256_tree


def test_subdivide_is_deterministic():
    from test_changes import big_world
    from experiments.exp03 import subdivide
    pid, d = big_world()
    a = subdivide(pid, d.types(), 9, np.arange(d.n), {}, {2, 3}, min_px=40)
    b = subdivide(pid, d.types(), 9, np.arange(d.n), {}, {2, 3}, min_px=40)
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])


def test_widen_is_deterministic():
    from test_changes import strip_world
    from experiments.exp02 import widen
    from experiments.mapdata import LAND
    pid, d = strip_world()
    f = np.zeros(pid.shape, bool)
    a = widen(pid, d.types(), f, LAND, 200)
    b = widen(pid, d.types(), f, LAND, 200)
    assert np.array_equal(a[0], b[0]) and a[1] == b[1]


def test_layout_is_deterministic():
    from test_changes import small_layout
    _, a = small_layout()
    _, b = small_layout()
    assert np.array_equal(a.pid, b.pid) and a.off_ids == b.off_ids and a.sea_new == b.sea_new


def test_dds_mips_are_deterministic():
    from experiments.dds import dxt5_encode, dxt5_mip_chain, full_mip_count
    img = np.random.default_rng(5).integers(0, 256, (32, 48, 4), dtype=np.uint8)
    l0 = dxt5_encode(img)
    assert dxt5_mip_chain(img, l0, full_mip_count(48, 32)) == dxt5_mip_chain(img, l0, full_mip_count(48, 32))


def test_small_builds_are_byte_identical(ctx, tmp_path):
    """Build a few cheap experiments twice from the game install: identical SHA-256 per file."""
    from experiments.build import build_into
    from experiments.registry import resolve
    for sel in ("EXP-01-SEAM-A", "EXP-05-3to1", "EXP-06"):
        (exp, bid), = resolve(ctx, sel)
        outs = []
        for k in range(2):
            out = tmp_path / f"{bid}-{k}"
            out.mkdir()
            build_into(ctx, exp, bid, out)
            outs.append(sha256_tree(out))
        assert outs[0] == outs[1], bid
