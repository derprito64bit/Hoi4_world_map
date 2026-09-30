"""Natural Earth 1:50m land polygons for the P00d previews (preview-only; P02 does the real acquisition).

The download is pinned by URL + SHA-256 (recorded in data/manifest.csv, id ``ne_50m_land``) and
stored under ``data/raw/naturalearth/`` (gitignored). The shapefile is read straight from the zip
with a minimal reader (polygon shapes only), so no GIS dependency is needed.
"""
from __future__ import annotations

import hashlib
import io
import struct
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "naturalearth"
LAND_URL = "https://naciscdn.org/naturalearth/50m/physical/ne_50m_land.zip"
LAND_ZIP = "ne_50m_land.zip"
LAND_SHA256 = "0b8e670cf80dce9cbebe2a193bc44ba5602758c22e1fa603980553646d7ff162"
LAND_VERSION = "4.1.0"


class DataError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def land_zip(download=True, raw_dir: Path = RAW_DIR) -> Path:
    """Path of the verified zip; downloads it when missing (and allowed)."""
    path = Path(raw_dir) / LAND_ZIP
    if not path.is_file():
        if not download:
            raise DataError(f"{path} missing (run `python tools/projection/hybrid.py preview` with network)")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        with urllib.request.urlopen(LAND_URL, timeout=120) as resp, open(tmp, "wb") as fh:
            fh.write(resp.read())
        tmp.replace(path)
    got = sha256_file(path)
    if got != LAND_SHA256:
        raise DataError(f"{path}: sha256 {got} != pinned {LAND_SHA256} (data/manifest.csv); refusing to use it")
    return path


def read_polygons_shp(data: bytes):
    """Minimal ESRI .shp reader for Polygon (5) records.

    Returns a list of records; each record is a list of rings, each ring an (n, 2) float array
    of (lon, lat). Ring orientation follows the spec: outer rings clockwise, holes counter-clockwise.
    """
    if len(data) < 100 or struct.unpack(">i", data[:4])[0] != 9994:
        raise DataError("not a shapefile")
    shape_type = struct.unpack("<i", data[32:36])[0]
    if shape_type not in (5, 15, 25):
        raise DataError(f"shape type {shape_type} is not a polygon type")
    off = 100
    records = []
    while off + 8 <= len(data):
        _, clen = struct.unpack(">ii", data[off:off + 8])
        body = data[off + 8: off + 8 + 2 * clen]
        off += 8 + 2 * clen
        st = struct.unpack("<i", body[:4])[0]
        if st == 0:
            records.append([])
            continue
        nparts, npts = struct.unpack("<ii", body[36:44])
        parts = np.frombuffer(body, "<i4", nparts, 44).astype(np.int64)
        pts = np.frombuffer(body, "<f8", 2 * npts, 44 + 4 * nparts).reshape(npts, 2)
        bounds = list(parts) + [npts]
        records.append([pts[bounds[i]:bounds[i + 1]].copy() for i in range(nparts)])
    return records


def ring_is_hole(ring) -> bool:
    """Counter-clockwise ring (positive shoelace area with y up) = hole in the shapefile convention."""
    x, y = ring[:, 0], ring[:, 1]
    return float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)) > 0


def load_land(download=True, raw_dir: Path = RAW_DIR):
    """Land records from the pinned ne_50m_land.zip."""
    with zipfile.ZipFile(land_zip(download, raw_dir)) as z:
        return read_polygons_shp(z.read("ne_50m_land.shp"))
