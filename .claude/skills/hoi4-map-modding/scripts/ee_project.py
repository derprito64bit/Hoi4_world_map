#!/usr/bin/env python3
"""Equal Earth projection <-> HOI4 pixel canvas.

Formulas: Šavrič, Patterson & Jenny (2018), "The Equal Earth map projection",
IJGIS 33(3). Verified to 1e-6 against PROJ `+proj=eqearth` (see references/equal-earth.md).

Canvas convention (matches how the game reads BMPs after decoding):
  * pixel (col, row) with row 0 = TOP (north) of the image, as numpy/PIL see it;
  * the game's own z coordinate in buildings.txt / unitstacks.txt counts from the
    BOTTOM, so  z = H - row  (see to_game_xz()).
  * Latitudes outside [lat_min, lat_max] are cropped (project default: 60°S, like vanilla).
  * The canvas is fitted so the projected equator spans the full width exactly:
    the left and right image edges are both the cut meridian (lon_0 +/- 180),
    which lets the game's horizontal wrap join them at the equator.

CLI:
  python3 ee_project.py info                      # project defaults: 4608x2048, lon0 10.9, 60°S..90°N
  python3 ee_project.py info  --width 5120 --height 2560 --lat-min -90   # full globe variant
  python3 ee_project.py mask  --out globe_mask.png
  python3 ee_project.py point --lon 13.4 --lat 52.5
  python3 ee_project.py selftest
"""
import argparse
import sys

import numpy as np

A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
M = np.sqrt(3.0) / 2.0
X_MAX = 2.7066299836960748   # x at (lon=180, lat=0), R = 1
Y_MAX = 1.3173627591574133   # y at lat = 90, R = 1
EARTH_AREA_KM2 = 510_065_622.0


def wrap_lon(lon, lon0):
    """Longitude relative to lon0, in [-180, 180)."""
    return (np.asarray(lon, dtype=float) - lon0 + 180.0) % 360.0 - 180.0


def forward(lon, lat, lon0=0.0):
    """Degrees -> unit-sphere Equal Earth (x, y). x in [-X_MAX, X_MAX), y in [-Y_MAX, Y_MAX]."""
    lam = np.radians(wrap_lon(lon, lon0))
    th = np.arcsin(M * np.sin(np.radians(lat)))
    t2 = th * th
    t6 = t2 * t2 * t2
    x = lam * np.cos(th) / (M * (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2)))
    y = th * (A1 + A2 * t2 + t6 * (A3 + A4 * t2))
    return x, y


def inverse(x, y, lon0=0.0, iters=12):
    """Unit-sphere (x, y) -> degrees (lon, lat). Points outside the outline return NaN."""
    x = np.asarray(x, dtype=float)
    y = np.clip(np.asarray(y, dtype=float), -Y_MAX, Y_MAX)
    th = y.copy()
    for _ in range(iters):  # Newton on y(theta) - y = 0
        t2 = th * th
        t6 = t2 * t2 * t2
        fy = th * (A1 + A2 * t2 + t6 * (A3 + A4 * t2)) - y
        fpy = A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2)
        th = th - fy / fpy
    t2 = th * th
    t6 = t2 * t2 * t2
    lam = M * x * (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2)) / np.cos(th)
    lat = np.degrees(np.arcsin(np.clip(np.sin(th) / M, -1, 1)))
    lon = np.degrees(lam)
    outside = np.abs(lon) > 180.0 + 1e-9
    lon = np.where(outside, np.nan, wrap_lon(lon + lon0, 0.0))
    lat = np.where(outside, np.nan, lat)
    return lon, lat


class Canvas:
    """Fits the Equal Earth outline into a W x H pixel canvas.

    scale (px per unit-sphere radian) is chosen so 2*X_MAX*scale == W: the
    equator touches both vertical edges. The outline is centred vertically; the
    remaining rows (top and bottom) are off-globe margin.
    """

    def __init__(self, width, height, lon0=0.0, lat_min=-90.0, lat_max=90.0):
        self.W, self.H, self.lon0 = int(width), int(height), float(lon0)
        self.lat_min, self.lat_max = float(lat_min), float(lat_max)
        self.scale = self.W / (2 * X_MAX)
        self.y_top = float(forward(0.0, self.lat_max)[1])
        self.y_bot = float(forward(0.0, self.lat_min)[1])
        self.globe_h = (self.y_top - self.y_bot) * self.scale
        if self.globe_h > self.H + 1e-6:
            raise ValueError(f"height {self.H} too small: latitudes {self.lat_min}..{self.lat_max} need {self.globe_h:.1f} rows at width {self.W}")
        self.margin = (self.H - self.globe_h) / 2

    # --- lon/lat <-> pixel (float, pixel centres at .5)
    def to_pixel(self, lon, lat):
        x, y = forward(lon, lat, self.lon0)
        col = (x + X_MAX) * self.scale
        row = self.margin + (self.y_top - y) * self.scale
        return col, row

    def to_lonlat(self, col, row):
        x = np.asarray(col, dtype=float) / self.scale - X_MAX
        y = self.y_top - (np.asarray(row, dtype=float) - self.margin) / self.scale
        return inverse(x, y, self.lon0)

    def to_game_xz(self, lon, lat):
        """Coordinates as written in buildings.txt/unitstacks.txt (z counted from the bottom)."""
        col, row = self.to_pixel(lon, lat)
        return col, self.H - row

    def globe_mask(self):
        """bool[H, W]: True where the pixel centre lies on the globe inside the latitude window."""
        rows, cols = np.mgrid[0:self.H, 0:self.W] + 0.5
        lon, _ = self.to_lonlat(cols, rows)
        y = self.y_top - (rows - self.margin) / self.scale
        return ~np.isnan(lon) & (y <= self.y_top) & (y >= self.y_bot)

    def km2_per_px(self):
        return EARTH_AREA_KM2 / (4 * np.pi * self.scale ** 2)


def selftest():
    # reference values from PROJ 9 (+proj=eqearth +R=1 +lon_0=0)
    ref = [((45, 45), (0.579927, 0.860231)), ((-120, -30), (-1.687801, -0.592935)),
           ((179.9, 60), (2.037927, 1.088301)), ((0, 90), (0.0, 1.317363))]
    for (lon, lat), (ex, ey) in ref:
        x, y = forward(lon, lat)
        assert abs(x - ex) < 1e-6 and abs(y - ey) < 1e-6, (lon, lat, x, y)
    rng = np.random.default_rng(0)
    lon = rng.uniform(-179.99, 179.99, 20000)
    lat = rng.uniform(-89.9, 89.9, 20000)
    for lon0 in (0.0, 11.0, -150.0):
        x, y = forward(lon, lat, lon0)
        lo, la = inverse(x, y, lon0)
        dlon = np.abs(wrap_lon(lo - lon, 0.0))
        assert np.nanmax(dlon) < 1e-6 and np.nanmax(np.abs(la - lat)) < 1e-6, lon0
    c = Canvas(5120, 2560, 10.9)
    m = c.globe_mask()
    area_px = m.sum()
    expect = 4 * np.pi * c.scale ** 2
    assert abs(area_px - expect) / expect < 1e-3, (area_px, expect)
    # cropped canvas (project default): 60°S crop fits 4608 x 2048 exactly
    c = Canvas(4608, 2048, 10.9, lat_min=-60.0)
    col, row = c.to_pixel(10.9, -60.0)
    assert abs(row - (c.margin + c.globe_h)) < 1e-6
    lo, la = c.to_lonlat(*c.to_pixel(13.4, 52.5))
    assert abs(lo - 13.4) < 1e-6 and abs(la - 52.5) < 1e-6
    print(f"selftest ok: forward matches PROJ, inverse round-trips, mask area {area_px} px ~ {expect:.0f}, crop ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["info", "mask", "point", "selftest"])
    ap.add_argument("--width", type=int, default=4608)
    ap.add_argument("--height", type=int, default=2048)
    ap.add_argument("--lat-min", type=float, default=-60.0)
    ap.add_argument("--lat-max", type=float, default=90.0)
    ap.add_argument("--lon0", type=float, default=10.9)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--lat", type=float)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.cmd == "selftest":
        selftest(); return 0
    c = Canvas(a.width, a.height, a.lon0, a.lat_min, a.lat_max)
    if a.cmd == "info":
        print(f"canvas {c.W}x{c.H} area {c.W*c.H}  lon0={c.lon0}  cut meridian={wrap_lon(c.lon0 + 180, 0):.3f}")
        print(f"latitudes {c.lat_min}..{c.lat_max}  scale {c.scale:.3f} px/rad  globe height {c.globe_h:.1f} rows  margin {c.margin:.1f} rows top & bottom")
        print(f"{c.km2_per_px():.2f} km2 per pixel  (~{np.sqrt(c.km2_per_px()):.2f} km per pixel side)")
        print(f"equator: {c.W / 360:.3f} px per degree of longitude")
    elif a.cmd == "point":
        col, row = c.to_pixel(a.lon, a.lat)
        gx, gz = c.to_game_xz(a.lon, a.lat)
        print(f"col {float(col):.2f} row {float(row):.2f}  game x {float(gx):.2f} z {float(gz):.2f}")
    elif a.cmd == "mask":
        from PIL import Image
        Image.fromarray((c.globe_mask() * 255).astype(np.uint8)).save(a.out)
        print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
