"""DDS container + DXT5 (BC3) codec in numpy, enough for HOI4's map-sized textures.

Vanilla 1.19.3 (P00 log section 4):
  colormap_rgb_cityemissivemask_a.dds  uncompressed 32-bit BGRA, 1 level
  colormap_water_0/1/2.dds             DXT5, no mip chain
  fow_rgb_waterspec_a.dds              DXT5, 12 levels
The writer reuses the vanilla header (flags, caps, pixel format) and only
updates width, height, pitch/linear size and mip count, so the file layout the
engine sees is the vanilla one. The encoder is a deterministic bounding-box
fit (no randomness, no platform-dependent maths).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

from .common import KitError

DDSD_MIPMAPCOUNT = 0x20000
DDSD_LINEARSIZE = 0x80000
DDSD_PITCH = 0x8


@dataclass
class Dds:
    header: bytes      # 128 bytes incl. magic
    width: int
    height: int
    fourcc: bytes      # b"DXT5" or b"\0\0\0\0" (uncompressed)
    levels: list       # list[bytes], level 0 first

    @property
    def compressed(self) -> bool:
        return self.fourcc == b"DXT5"


def level_dims(w: int, h: int, n: int) -> list:
    return [(max(1, w >> k), max(1, h >> k)) for k in range(n)]


def level_size(w: int, h: int, compressed: bool) -> int:
    if compressed:
        return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * 16
    return w * h * 4


def full_mip_count(w: int, h: int) -> int:
    return max(w, h).bit_length()


def read_dds(data: bytes) -> Dds:
    if data[:4] != b"DDS " or len(data) < 128:
        raise KitError("not a DDS file")
    h, w = struct.unpack_from("<II", data, 12)
    mips = struct.unpack_from("<I", data, 28)[0]
    pf_flags = struct.unpack_from("<I", data, 80)[0]
    fourcc = data[84:88]
    if pf_flags & 0x4:
        if fourcc != b"DXT5":
            raise KitError(f"unsupported fourcc {fourcc!r}")
        comp = True
    else:
        bits, rm, gm, bm, am = struct.unpack_from("<5I", data, 88)
        if (bits, rm, gm, bm, am) != (32, 0xFF0000, 0xFF00, 0xFF, 0xFF000000):
            raise KitError("only 32-bit BGRA uncompressed DDS is supported")
        comp = False
        fourcc = b"\0\0\0\0"
    n = max(1, mips)
    levels, off = [], 128
    for lw, lh in level_dims(w, h, n):
        size = level_size(lw, lh, comp)
        if off + size > len(data):
            raise KitError("truncated DDS")
        levels.append(bytes(data[off:off + size]))
        off += size
    return Dds(header=bytes(data[:128]), width=w, height=h, fourcc=fourcc, levels=levels)


def write_dds(template: Dds, width: int, height: int, levels: list) -> bytes:
    hdr = bytearray(template.header)
    struct.pack_into("<II", hdr, 12, height, width)
    flags = struct.unpack_from("<I", hdr, 8)[0]
    if template.compressed:
        struct.pack_into("<I", hdr, 20, level_size(width, height, True))
    else:
        struct.pack_into("<I", hdr, 20, width * 4)
    if flags & DDSD_MIPMAPCOUNT:
        struct.pack_into("<I", hdr, 28, len(levels))
    elif len(levels) != 1:
        raise KitError("template has no mip chain but several levels were given")
    for (lw, lh), lv in zip(level_dims(width, height, len(levels)), levels):
        if len(lv) != level_size(lw, lh, template.compressed):
            raise KitError("level size does not match its dimensions")
    return bytes(hdr) + b"".join(levels)


# ------------------------------------------------------------------ BGRA (uncompressed)
def bgra_to_rgba(level: bytes, w: int, h: int) -> np.ndarray:
    a = np.frombuffer(level, dtype=np.uint8).reshape(h, w, 4)
    return a[:, :, [2, 1, 0, 3]].copy()


def rgba_to_bgra(rgba: np.ndarray) -> bytes:
    return np.ascontiguousarray(rgba[:, :, [2, 1, 0, 3]]).tobytes()


# ------------------------------------------------------------------ DXT5 codec
def _565_to_rgb(c: np.ndarray) -> np.ndarray:
    c = c.astype(np.int32)
    r = (c >> 11) & 31
    g = (c >> 5) & 63
    b = c & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], -1)


def _rgb_to_565(rgb: np.ndarray) -> np.ndarray:
    rgb = rgb.astype(np.int32)
    r = (rgb[..., 0] * 31 + 127) // 255
    g = (rgb[..., 1] * 63 + 127) // 255
    b = (rgb[..., 2] * 31 + 127) // 255
    return ((r << 11) | (g << 5) | b).astype(np.uint16)


def dxt5_decode(level: bytes, w: int, h: int) -> np.ndarray:
    """DXT5 level -> (h, w, 4) RGBA uint8."""
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    blk = np.frombuffer(level, dtype=np.uint8).reshape(bh * bw, 16)
    a0 = blk[:, 0].astype(np.int32)
    a1 = blk[:, 1].astype(np.int32)
    abits = np.zeros(len(blk), dtype=np.uint64)
    for i in range(6):
        abits |= blk[:, 2 + i].astype(np.uint64) << np.uint64(8 * i)
    aidx = np.stack([((abits >> np.uint64(3 * k)) & np.uint64(7)).astype(np.int32) for k in range(16)], 1)
    apal = np.zeros((len(blk), 8), dtype=np.int32)
    apal[:, 0], apal[:, 1] = a0, a1
    eight = a0 > a1
    for k in range(1, 7):   # 8-value mode
        apal[:, k + 1] = np.where(eight, ((7 - k) * a0 + k * a1) // 7, apal[:, k + 1])
    for k in range(1, 5):   # 6-value mode
        apal[:, k + 1] = np.where(~eight, ((5 - k) * a0 + k * a1) // 5, apal[:, k + 1])
    apal[:, 6] = np.where(~eight, 0, apal[:, 6])
    apal[:, 7] = np.where(~eight, 255, apal[:, 7])
    alpha = np.take_along_axis(apal, aidx, 1)
    c0 = blk[:, 8].astype(np.uint16) | (blk[:, 9].astype(np.uint16) << 8)
    c1 = blk[:, 10].astype(np.uint16) | (blk[:, 11].astype(np.uint16) << 8)
    p0, p1 = _565_to_rgb(c0), _565_to_rgb(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3], 1)   # DXT5 is always 4-colour
    cbits = (blk[:, 12].astype(np.uint32) | (blk[:, 13].astype(np.uint32) << 8)
             | (blk[:, 14].astype(np.uint32) << 16) | (blk[:, 15].astype(np.uint32) << 24))
    cidx = np.stack([((cbits >> (2 * k)) & 3).astype(np.int64) for k in range(16)], 1)
    rgb = np.take_along_axis(pal, cidx[:, :, None].repeat(3, 2), 1)
    out = np.concatenate([rgb, alpha[:, :, None]], 2).astype(np.uint8)       # (nb, 16, 4)
    out = out.reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return out[:h, :w].copy()


def dxt5_encode(rgba: np.ndarray) -> bytes:
    """(h, w, 4) RGBA uint8 -> DXT5 level bytes (edge-replicated to whole blocks)."""
    h, w = rgba.shape[:2]
    bh, bw = max(1, (h + 3) // 4), max(1, (w + 3) // 4)
    pad = np.pad(rgba, ((0, bh * 4 - h), (0, bw * 4 - w), (0, 0)), mode="edge")
    blocks = pad.reshape(bh, 4, bw, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * bw, 16, 4).astype(np.int32)
    out = np.zeros((bh * bw, 16), dtype=np.uint8)
    # alpha
    a = blocks[:, :, 3]
    amax, amin = a.max(1), a.min(1)
    out[:, 0], out[:, 1] = amax, amin
    apal = np.stack([amax, amin] + [((7 - k) * amax + k * amin) // 7 for k in range(1, 7)], 1)
    aidx = np.abs(a[:, :, None] - apal[:, None, :]).argmin(2)
    aidx = np.where((amax == amin)[:, None], 0, aidx).astype(np.uint64)
    abits = np.zeros(len(blocks), dtype=np.uint64)
    for k in range(16):
        abits |= aidx[:, k] << np.uint64(3 * k)
    for i in range(6):
        out[:, 2 + i] = ((abits >> np.uint64(8 * i)) & np.uint64(255)).astype(np.uint8)
    # colour
    rgb = blocks[:, :, :3]
    c0 = _rgb_to_565(rgb.max(1))
    c1 = _rgb_to_565(rgb.min(1))
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    p0, p1 = _565_to_rgb(c0), _565_to_rgb(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3], 1)          # (nb, 4, 3)
    d = ((rgb[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(3)                     # (nb, 16, 4)
    cidx = d.argmin(2)
    cidx = np.where((c0 == c1)[:, None], 0, cidx).astype(np.uint32)
    cbits = np.zeros(len(blocks), dtype=np.uint32)
    for k in range(16):
        cbits |= cidx[:, k] << np.uint32(2 * k)
    out[:, 8], out[:, 9] = (c0 & 255).astype(np.uint8), (c0 >> 8).astype(np.uint8)
    out[:, 10], out[:, 11] = (c1 & 255).astype(np.uint8), (c1 >> 8).astype(np.uint8)
    for i in range(4):
        out[:, 12 + i] = ((cbits >> np.uint32(8 * i)) & np.uint32(255)).astype(np.uint8)
    return out.tobytes()


def dxt5_uniform_block(rgba) -> bytes:
    """One DXT5 block that decodes to a single colour (565-quantised RGB, exact alpha)."""
    r, g, b, a = (int(v) for v in rgba)
    c = int(_rgb_to_565(np.array([r, g, b])))
    return bytes([a, a, 0, 0, 0, 0, 0, 0, c & 255, c >> 8, c & 255, c >> 8, 0, 0, 0, 0])


def dxt5_pad_blocks(level: bytes, w: int, h: int, top: int, right: int, block: bytes) -> bytes:
    """Pad a DXT5 level by whole blocks: ``top`` rows above, ``right`` columns to the right.

    DDS rows run top-down, so padding at the top prepends block rows. Existing
    blocks are copied bit-for-bit (the vanilla area is lossless).
    """
    if w % 4 or h % 4 or top % 4 or right % 4:
        raise KitError("block padding needs dimensions and padding that are multiples of 4")
    bw, bh = w // 4, h // 4
    arr = np.frombuffer(level, dtype=np.uint8).reshape(bh, bw, 16)
    fill = np.frombuffer(block, dtype=np.uint8)
    out = np.empty((bh + top // 4, bw + right // 4, 16), dtype=np.uint8)
    out[:] = fill
    out[top // 4:, :bw] = arr
    return out.tobytes()


def box_downsample(rgba: np.ndarray) -> np.ndarray:
    """Next mip level: 2x2 box filter (odd trailing row/column ignored), integer rounding."""
    h, w = rgba.shape[:2]
    nh, nw = max(1, h // 2), max(1, w // 2)
    if h == 1 or w == 1:
        a = rgba.astype(np.int32)
        if h == 1 and w == 1:
            return rgba.copy()
        if h == 1:
            return ((a[:, 0:2 * nw:2] + a[:, 1:2 * nw:2] + 1) // 2).astype(np.uint8)
        return ((a[0:2 * nh:2] + a[1:2 * nh:2] + 1) // 2).astype(np.uint8)
    a = rgba[:2 * nh, :2 * nw].astype(np.int32)
    s = a[0::2, 0::2] + a[1::2, 0::2] + a[0::2, 1::2] + a[1::2, 1::2]
    return ((s + 2) // 4).astype(np.uint8)


def dxt5_mip_chain(level0_rgba: np.ndarray, level0_bytes: bytes, count: int) -> list:
    """Levels 0..count-1: level 0 as given (bytes), the rest box-filtered and re-encoded."""
    levels, cur = [level0_bytes], level0_rgba
    for _ in range(1, count):
        cur = box_downsample(cur)
        levels.append(dxt5_encode(cur))
    return levels
