"""Minimal, header-preserving BMP I/O for HOI4 map layers.

Pillow rewrites headers (40-byte DIB, 256-entry palettes). HOI4 1.19.3 ships
BITMAPV5 (124-byte) headers on terrain.bmp/trees.bmp and 255-entry palettes on
terrain/cities, so this module keeps the original header and palette bytes and
only updates the size fields. Supported: uncompressed 8-bit indexed and 24-bit.

Pixels are handled top-down in memory (row 0 = north), as numpy/PIL see them.
(``tools/common.py`` does not exist yet and is outside the P00b scope, so the
kit carries its own BMP helper; P01 can absorb it.)
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

from .common import KitError


@dataclass
class Bmp:
    header: bytes            # everything before the pixel array (file header, DIB header, palette, gap)
    width: int
    height: int              # absolute value
    bpp: int
    top_down: bool           # True if the file stores rows top-down (negative height)
    pixels: np.ndarray       # (H, W) uint8 for 8-bit, (H, W, 3) RGB uint8 for 24-bit
    tail: bytes = field(default=b"")

    @property
    def dib_size(self) -> int:
        return struct.unpack_from("<I", self.header, 14)[0]

    @property
    def palette(self) -> bytes:
        """Raw BGRA palette quads (empty for 24-bit)."""
        if self.bpp > 8:
            return b""
        n = struct.unpack_from("<I", self.header, 46)[0] or (1 << self.bpp)
        start = 14 + self.dib_size
        return self.header[start:start + 4 * n]


def _stride(width: int, bpp: int) -> int:
    return ((width * bpp + 31) // 32) * 4


def read_bmp(data: bytes) -> Bmp:
    if data[:2] != b"BM":
        raise KitError("not a BMP file")
    off = struct.unpack_from("<I", data, 10)[0]
    dib = struct.unpack_from("<I", data, 14)[0]
    if dib not in (40, 108, 124):
        raise KitError(f"unsupported DIB header size {dib}")
    w, h = struct.unpack_from("<ii", data, 18)
    bpp, comp = struct.unpack_from("<HI", data, 28)
    if comp != 0:
        raise KitError("compressed BMPs are not supported (HOI4 needs BI_RGB)")
    if bpp not in (8, 24):
        raise KitError(f"unsupported bit depth {bpp}")
    H, top_down = abs(h), h < 0
    stride = _stride(w, bpp)
    end = off + stride * H
    if len(data) < end:
        raise KitError("truncated BMP pixel array")
    raw = np.frombuffer(data, dtype=np.uint8, count=stride * H, offset=off).reshape(H, stride)
    if bpp == 8:
        px = raw[:, :w].copy()
    else:
        px = raw[:, :w * 3].reshape(H, w, 3)[:, :, ::-1].copy()   # BGR -> RGB
    if not top_down:
        px = px[::-1].copy()
    return Bmp(header=bytes(data[:off]), width=w, height=H, bpp=bpp, top_down=top_down,
               pixels=px, tail=bytes(data[end:]))


def write_bmp(template: Bmp, pixels: np.ndarray, palette: bytes | None = None, keep_tail: bool = False) -> bytes:
    """Serialise pixels with the template's header (DIB type, palette, resolution fields kept).

    Size fields (bfSize, width, height, biSizeImage) are recomputed. ``palette``
    optionally replaces the palette bytes (same length). ``keep_tail`` re-appends
    the template's trailing bytes (vanilla heightmap/rivers carry 2 of them).
    """
    px = np.ascontiguousarray(pixels)
    if template.bpp == 8:
        if px.ndim != 2 or px.dtype != np.uint8:
            raise KitError("8-bit BMP needs a 2-D uint8 array")
        H, W = px.shape
    else:
        if px.ndim != 3 or px.shape[2] != 3 or px.dtype != np.uint8:
            raise KitError("24-bit BMP needs an (H, W, 3) uint8 array")
        H, W = px.shape[:2]
    stride = _stride(W, template.bpp)
    rows = px if template.top_down else px[::-1]
    buf = np.zeros((H, stride), dtype=np.uint8)
    if template.bpp == 8:
        buf[:, :W] = rows
    else:
        buf[:, :W * 3] = rows[:, :, ::-1].reshape(H, W * 3)
    hdr = bytearray(template.header)
    if palette is not None:
        old = template.palette
        if len(palette) != len(old):
            raise KitError("replacement palette must have the template's length")
        start = 14 + template.dib_size
        hdr[start:start + len(old)] = palette
    tail = template.tail if keep_tail else b""
    struct.pack_into("<ii", hdr, 18, W, -H if template.top_down else H)
    struct.pack_into("<I", hdr, 34, stride * H + len(tail))
    struct.pack_into("<I", hdr, 2, len(hdr) + stride * H + len(tail))
    struct.pack_into("<I", hdr, 10, len(hdr))
    return bytes(hdr) + buf.tobytes() + tail


def rgb_to_key(px: np.ndarray) -> np.ndarray:
    """(H, W, 3) uint8 RGB -> (H, W) int32 key r<<16 | g<<8 | b."""
    p = px.astype(np.int32)
    return (p[..., 0] << 16) | (p[..., 1] << 8) | p[..., 2]
