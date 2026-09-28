"""BMP (header-preserving) and DDS/DXT5 helpers."""
import struct

import numpy as np
import pytest

from experiments.bmpio import read_bmp, write_bmp
from experiments.common import KitError
from experiments.dds import (Dds, box_downsample, dxt5_decode, dxt5_encode, dxt5_mip_chain, dxt5_pad_blocks,
                             dxt5_uniform_block, full_mip_count, level_dims, read_dds, write_dds)


def make_bmp8(w, h, dib=124, ncolors=255, top_down=False):
    stride = ((w * 8 + 31) // 32) * 4
    pal = bytes(b for i in range(ncolors) for b in (i, 255 - i, i // 2, 0))
    dibh = struct.pack("<IiiHHIIiiII", dib, w, -h if top_down else h, 1, 8, 0, stride * h + 2, 2834, 2834, ncolors, ncolors)
    dibh += b"\x00" * (dib - 40)
    off = 14 + dib + len(pal)
    px = (np.arange(h * w).reshape(h, w) % ncolors).astype(np.uint8)
    rows = px if top_down else px[::-1]
    buf = np.zeros((h, stride), np.uint8)
    buf[:, :w] = rows
    data = b"BM" + struct.pack("<IHHI", off + stride * h + 2, 0, 0, off) + dibh + pal + buf.tobytes() + b"\x00\x00"
    return data, px


@pytest.mark.parametrize("dib,top_down,w", [(124, False, 10), (40, False, 16), (40, True, 7)])
def test_bmp8_roundtrip_keeps_header_palette_and_tail(dib, top_down, w):
    data, px = make_bmp8(w, 6, dib=dib, top_down=top_down)
    b = read_bmp(data)
    assert b.dib_size == dib and b.bpp == 8 and len(b.palette) == 255 * 4
    assert np.array_equal(b.pixels, px)
    assert write_bmp(b, b.pixels, keep_tail=True) == data


def test_bmp8_resize_updates_only_size_fields():
    data, px = make_bmp8(10, 6)
    b = read_bmp(data)
    new = np.zeros((4, 13), np.uint8)
    out = write_bmp(b, new)
    r = read_bmp(out)
    assert (r.width, r.height) == (13, 4) and r.palette == b.palette and r.dib_size == 124
    a, c = bytearray(data[:b.header.__len__()]), bytearray(out[:len(r.header)])
    for off in (2, 18, 22, 34):
        a[off:off + 4] = c[off:off + 4] = b"\0\0\0\0"
    assert a == c


def test_bmp24_roundtrip():
    w, h = 5, 3
    rgb = np.arange(w * h * 3, dtype=np.uint8).reshape(h, w, 3)
    stride = ((w * 24 + 31) // 32) * 4
    buf = np.zeros((h, stride), np.uint8)
    buf[:, :w * 3] = rgb[::-1, :, ::-1].reshape(h, w * 3)
    dib = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, stride * h, 3780, 3780, 0, 0)
    data = b"BM" + struct.pack("<IHHI", 54 + stride * h, 0, 0, 54) + dib + buf.tobytes()
    b = read_bmp(data)
    assert np.array_equal(b.pixels, rgb)
    assert write_bmp(b, b.pixels) == data


def test_bmp_rejects_compressed_and_32bit():
    data, _ = make_bmp8(4, 4)
    bad = bytearray(data)
    struct.pack_into("<I", bad, 30, 1)
    with pytest.raises(KitError):
        read_bmp(bytes(bad))
    bad = bytearray(data)
    struct.pack_into("<H", bad, 28, 32)
    with pytest.raises(KitError):
        read_bmp(bytes(bad))


def test_dxt5_uniform_block_decodes_exactly():
    blk = dxt5_uniform_block((16, 64, 200, 77))
    px = dxt5_decode(blk, 4, 4)
    assert (px[..., 3] == 77).all()
    assert len(np.unique(px.reshape(-1, 4), axis=0)) == 1


def test_dxt5_encode_decode_is_close_and_deterministic():
    rng = np.random.default_rng(1)
    img = np.clip(rng.normal(120, 30, (12, 20, 4)), 0, 255).astype(np.uint8)
    img[..., :3] = np.linspace(0, 255, 20)[None, :, None].astype(np.uint8)
    a = dxt5_encode(img)
    assert a == dxt5_encode(img)
    back = dxt5_decode(a, 20, 12)
    assert np.abs(back.astype(int) - img.astype(int)).max() <= 40
    flat = np.full((8, 8, 4), (10, 20, 30, 40), np.uint8)
    assert np.abs(dxt5_decode(dxt5_encode(flat), 8, 8).astype(int) - flat).max() <= 4


def test_dxt5_pad_blocks_is_lossless_for_the_old_area():
    rng = np.random.default_rng(2)
    lvl = rng.integers(0, 256, 16 * 4 * 3, dtype=np.uint8).tobytes()      # 16x12 px = 4x3 blocks
    fill = dxt5_uniform_block((1, 2, 3, 4))
    out = dxt5_pad_blocks(lvl, 16, 12, top=8, right=4, block=fill)
    arr = np.frombuffer(out, np.uint8).reshape(5, 5, 16)
    assert np.array_equal(arr[2:, :4].tobytes(), np.frombuffer(lvl, np.uint8).reshape(3, 4, 16).tobytes())
    assert all(arr[r, c].tobytes() == fill for r in range(5) for c in range(5) if r < 2 or c == 4)
    with pytest.raises(KitError):
        dxt5_pad_blocks(lvl, 16, 12, top=3, right=0, block=fill)


def _dds_header(w, h, mips, compressed):
    hdr = bytearray(128)
    hdr[:4] = b"DDS "
    flags = 0x1007 | (0x80000 if compressed else 0x8) | (0x20000 if mips > 1 else 0)
    struct.pack_into("<7I", hdr, 4, 124, flags, h, w, w * h if compressed else w * 4, 0, mips)
    struct.pack_into("<I", hdr, 76, 32)
    if compressed:
        struct.pack_into("<I", hdr, 80, 4)
        hdr[84:88] = b"DXT5"
    else:
        struct.pack_into("<I5I", hdr, 80, 0x41, 32, 0xFF0000, 0xFF00, 0xFF, 0xFF000000)
    return bytes(hdr)


def test_dds_roundtrip_with_mip_chain():
    w, h = 16, 8
    img = np.zeros((h, w, 4), np.uint8)
    img[..., 0] = 200
    l0 = dxt5_encode(img)
    levels = dxt5_mip_chain(img, l0, full_mip_count(w, h))
    assert [d for d in level_dims(w, h, len(levels))] == [(16, 8), (8, 4), (4, 2), (2, 1), (1, 1)]
    data = write_dds(Dds(_dds_header(w, h, 5, True), w, h, b"DXT5", levels), w, h, levels)
    d = read_dds(data)
    assert d.levels == levels and (d.width, d.height) == (w, h) and d.compressed


def test_box_downsample_odd_sizes():
    a = np.arange(5 * 3 * 4, dtype=np.uint8).reshape(3, 5, 4)
    assert box_downsample(a).shape == (1, 2, 4)
    assert box_downsample(np.zeros((1, 3, 4), np.uint8)).shape == (1, 1, 4)


def test_vanilla_bitmaps_roundtrip(game):
    from experiments.vanilla import Vanilla
    v = Vanilla(game)
    for rel in ("map/trees.bmp", "map/terrain.bmp", "map/cities.bmp", "map/world_normal.bmp"):
        data = v.bytes(rel)
        assert write_bmp(read_bmp(data), read_bmp(data).pixels, keep_tail=True) == data, rel


def test_vanilla_dds_parse(game):
    from experiments.vanilla import Vanilla
    v = Vanilla(game)
    d = read_dds(v.bytes("map/terrain/fow_rgb_waterspec_a.dds"))
    assert d.compressed and len(d.levels) == 12 and (d.width, d.height) == (2816, 1024)
    assert write_dds(d, d.width, d.height, d.levels) == v.bytes("map/terrain/fow_rgb_waterspec_a.dds")
