#!/usr/bin/env python3
"""Hybrid Equal Earth projection (DEC-035): Equal Earth interior, straight wrap edges.

Definition
----------
Let d = lon - lon0 wrapped to [-180, 180) (Δλ), phi the latitude, and let
``x_EE(d, phi) = c(phi) * d`` be the Equal Earth abscissa (unit sphere, d in
radians; EE is linear in d on every parallel).  Each parallel of EE ends at the
half-width ``w(phi) = pi * c(phi)``; only the equator reaches the canvas edge
``X_MAX = w(0)``.  The hybrid keeps y(phi) of EE unchanged and sets

    x_H(d, phi) = x_EE(d, phi)                                     |d| <= lb
    x_H(d, phi) = x_EE(d, phi) + sgn(d) * (X_MAX - w(phi)) * g(u)  lb < |d| <= pi
    u = (|d| - lb) / (pi - lb)                                     (0 at lb, 1 at the seam)

with a blend g: [0, 1] -> [0, 1], g(0) = g'(0) = g''(0) = 0, g(1) = 1, g' >= 0:

    k = 1 / (1 - r/2),  t = u / r
    g(u) = k r (t^3 - t^4/2)       u <  r   (g' = k (3t^2 - 2t^3), a smoothstep ramp)
    g(u) = k (r/2 + u - r)         u >= r   (g' = k, constant stretch)

``r`` (``ramp``, 0 < r <= 1) is the fraction of the band over which the extra
E-W stretch ramps up; r = 1 gives g = 2u^3 - u^4.

Derivation of the properties
  * |d| = lb: g = g' = g'' = 0, so x, dx/dλ and d²x/dλ² all match EE  -> C² at λb
    (g''' jumps: not C³).  At u = r, g' and g'' are continuous (smoothstep ends flat).
  * |d| = pi: g(1) = k (1 - r/2) = 1, so x = ±(w + X_MAX - w) = ±X_MAX: every row
    reaches the canvas edge.  x_H is odd in d, so dx/dλ is equal on both sides of
    the seam, and g''(1) = 0 makes d²x/dλ² vanish there: the periodic continuation
    across the wrap is C² too.
  * dx/dλ = c + (X_MAX - w) g'(u) / (pi - lb) >= c > 0: strictly monotone
    (w <= X_MAX on every parallel, EE is widest at the equator).
  * Equator: w = X_MAX, so the correction vanishes: identity where EE already
    touches the edge.
  * y depends on phi only, so the Jacobian is triangular and the area factor
    relative to EE equals the E-W stretch  s = 1 + (X_MAX/w - 1) * pi/(pi - lb) * g'(u).
    Peak stretch (at the seam) is 1 + (X_MAX/w - 1) * k * pi/(pi - lb); r trades a
    lower peak (small r) against a faster ramp (large curvature just outside λb).

Default ramp r = 0.5: the peak E-W stretch at the seam (Alaska/Chukotka) is 1.33x
the mean band stretch instead of 2x for r = 1, while the ramp still spans half
the band, so meridian spacing changes gradually (C²) with no visible kink.

Inverse: y -> phi exactly as ee_project; in the band the per-row equation
x_H(u) = x is strictly increasing in u on [0, 1] and is solved by a bracketed
(safeguarded) Newton iteration to ~1e-15.

CLI
  python tools/projection/hybrid.py selftest [--lambda-b N] [--ramp R]
  python tools/projection/hybrid.py info     [--lambda-b N] [--ramp R]
  python tools/projection/hybrid.py preview  [--lambda-b N] [--ramp R] [--check] [--out DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
EE_SCRIPTS = REPO_ROOT / ".claude" / "skills" / "hoi4-map-modding" / "scripts"
BUILD_DIR = REPO_ROOT / "build" / "projection"


def _ee():
    """The skill's Equal Earth module (imported, never copied)."""
    if str(EE_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(EE_SCRIPTS))
    return importlib.import_module("ee_project")


ee = _ee()
X_MAX = ee.X_MAX
Y_MAX = ee.Y_MAX

# Project canvas (docs/PROJECT_SPEC.md §2: CANVAS, LAT_RANGE, LON0). tools/params.py does not
# exist yet; these mirror the spec and ee_project's CLI defaults and move there when it does.
WIDTH, HEIGHT = 5120, 2304
LON0 = 10.9
LAT_MIN, LAT_MAX = -60.0, 90.0
LAMBDA_B_CANDIDATES = (60.0, 90.0, 120.0)
DEFAULT_LAMBDA_B = 90.0
DEFAULT_RAMP = 0.5
RAMP_MIN = 0.05


# ------------------------------------------------------------------ blend function
def _check_params(lambda_b, ramp):
    lambda_b, ramp = float(lambda_b), float(ramp)
    if not 0.0 < lambda_b <= 180.0:
        raise ValueError(f"lambda_b must be in (0, 180], got {lambda_b}")
    if not RAMP_MIN <= ramp <= 1.0:
        raise ValueError(f"ramp must be in [{RAMP_MIN}, 1], got {ramp}")
    return lambda_b, ramp


def blend(u, ramp=DEFAULT_RAMP):
    """g(u), g'(u), g''(u) for u in [0, 1] (see module docstring)."""
    u = np.clip(np.asarray(u, dtype=float), 0.0, 1.0)
    r = float(ramp)
    k = 1.0 / (1.0 - 0.5 * r)
    t = np.minimum(u / r, 1.0)
    t2 = t * t
    inner = u < r
    g = np.where(inner, k * r * (t2 * t - 0.5 * t2 * t2), k * (0.5 * r + u - r))
    g1 = np.where(inner, k * (3.0 * t2 - 2.0 * t2 * t), k)
    g2 = np.where(inner, k * 6.0 * t * (1.0 - t) / r, 0.0)
    return g, g1, g2


def half_width(lat):
    """w(phi): Equal Earth x at Δλ = 180° on each parallel (unit sphere); w(0) = X_MAX."""
    lat = np.asarray(lat, dtype=float)
    return -ee.forward(np.full_like(lat, -180.0), lat, 0.0)[0]


# ------------------------------------------------------------------ forward
def _band_terms(d, lat, lambda_b, ramp):
    """band mask, sign, (X_MAX - w), w, g, g' for Δλ d (degrees)."""
    ad = np.abs(d)
    band = ad > lambda_b
    lb = np.radians(lambda_b)
    span = np.pi - lb
    u = (np.radians(ad) - lb) / span if span > 0 else np.zeros_like(ad)
    g, g1, _ = blend(u, ramp)
    w = half_width(lat)
    return band, np.sign(d), X_MAX - w, w, g, g1, u


def forward(lon, lat, lon0=0.0, lambda_b=DEFAULT_LAMBDA_B, ramp=DEFAULT_RAMP):
    """Degrees -> unit-sphere hybrid (x, y). x in [-X_MAX, X_MAX), y exactly Equal Earth.

    Where |Δλ| <= lambda_b the result is bit-identical to ``ee_project.forward``.
    lambda_b = 180 is plain Equal Earth.
    """
    lambda_b, ramp = _check_params(lambda_b, ramp)
    lon, lat = np.broadcast_arrays(np.asarray(lon, dtype=float), np.asarray(lat, dtype=float))
    x_ee, y = ee.forward(lon, lat, lon0)
    if lambda_b >= 180.0:
        return x_ee, y
    d = ee.wrap_lon(lon, lon0)
    band, sgn, gap, _, g, _, u = _band_terms(d, lat, lambda_b, ramp)
    x = np.where(band, x_ee + sgn * gap * g, x_ee)
    x = np.where(band & (u >= 1.0), sgn * X_MAX, x)  # Δλ = -180 exactly: the left edge
    return x, y


def forward_dl(dl, lat, lambda_b=DEFAULT_LAMBDA_B, ramp=DEFAULT_RAMP):
    """Like forward() but takes Δλ (degrees) unwrapped in [-180, 180] inclusive.

    Δλ = +180 gives x = +X_MAX (right edge), -180 gives -X_MAX. Used for edge tests and
    for drawing geometry that touches the seam from either side.
    """
    lambda_b, ramp = _check_params(lambda_b, ramp)
    dl, lat = np.broadcast_arrays(np.asarray(dl, dtype=float), np.asarray(lat, dtype=float))
    if np.any(np.abs(dl) > 180.0 + 1e-9):
        raise ValueError("forward_dl: |Δλ| must be <= 180")
    sgn = np.sign(dl)
    x_abs, y = ee.forward(-np.abs(dl), lat, 0.0)
    x_ee = -sgn * x_abs
    if lambda_b >= 180.0:
        return x_ee, y
    band, _, gap, _, g, _, u = _band_terms(dl, lat, lambda_b, ramp)
    x = np.where(band, x_ee + sgn * gap * g, x_ee)
    x = np.where(band & (u >= 1.0), sgn * X_MAX, x)
    return x, y


def stretch(lon, lat, lon0=0.0, lambda_b=DEFAULT_LAMBDA_B, ramp=DEFAULT_RAMP):
    """E-W scale ratio hybrid/EE (dx/dλ over EE's dx/dλ). Equals the area factor. 1 in the interior."""
    lambda_b, ramp = _check_params(lambda_b, ramp)
    lon, lat = np.broadcast_arrays(np.asarray(lon, dtype=float), np.asarray(lat, dtype=float))
    if lambda_b >= 180.0:
        return np.ones_like(lon)
    d = ee.wrap_lon(lon, lon0)
    band, _, _, w, _, g1, _ = _band_terms(d, lat, lambda_b, ramp)
    span = np.pi - np.radians(lambda_b)
    return np.where(band, 1.0 + (X_MAX / w - 1.0) * (np.pi / span) * g1, 1.0)


def dx_dlambda(dl, lat, lambda_b=DEFAULT_LAMBDA_B, ramp=DEFAULT_RAMP):
    """Analytic dx/dλ (per radian) at Δλ = dl degrees."""
    lambda_b, ramp = _check_params(lambda_b, ramp)
    dl, lat = np.broadcast_arrays(np.asarray(dl, dtype=float), np.asarray(lat, dtype=float))
    w = half_width(lat)
    c = w / np.pi
    if lambda_b >= 180.0:
        return c
    band, _, gap, _, _, g1, _ = _band_terms(dl, lat, lambda_b, ramp)
    span = np.pi - np.radians(lambda_b)
    return np.where(band, c + gap * g1 / span, c)


# ------------------------------------------------------------------ inverse
def _lat_from_y(y):
    y = np.asarray(y, dtype=float)
    lat = ee.inverse(np.zeros_like(y), y, 0.0)[1]
    return np.where(np.abs(y) > Y_MAX * (1 + 1e-12), np.nan, lat)


def inverse(x, y, lon0=0.0, lambda_b=DEFAULT_LAMBDA_B, ramp=DEFAULT_RAMP, iters=60):
    """Unit-sphere hybrid (x, y) -> degrees (lon, lat). Outside |x| <= X_MAX, |y| <= Y_MAX: NaN.

    lambda_b = 180 is plain Equal Earth (NaN outside the curved outline).
    """
    lambda_b, ramp = _check_params(lambda_b, ramp)
    x, y = np.broadcast_arrays(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
    shape = x.shape
    x, y = x.reshape(-1), y.reshape(-1)
    lon, lat = _inverse_flat(x, y, lon0, lambda_b, ramp, iters)
    return lon.reshape(shape), lat.reshape(shape)


def _inverse_flat(x, y, lon0, lambda_b, ramp, iters):
    lat = _lat_from_y(y)
    ok = ~np.isnan(lat)
    latz = np.where(ok, lat, 0.0)
    xb = np.abs(ee.forward(np.full_like(latz, lambda_b if lambda_b < 180 else -180.0), latz, 0.0)[0])
    ax = np.abs(x)
    interior = ok & (ax <= xb)
    lon_ee = ee.inverse(np.where(interior, x, 0.0), y, lon0)[0]
    lon = np.where(interior, lon_ee, np.nan)
    if lambda_b >= 180.0:
        return lon, np.where(interior, lat, np.nan)
    band = ok & ~interior & (ax <= X_MAX * (1 + 1e-12))
    if np.any(band):
        idx = np.nonzero(band)
        axb = np.minimum(ax[idx], X_MAX)
        w = half_width(latz[idx])
        c = w / np.pi
        gap = X_MAX - w
        lb = np.radians(lambda_b)
        span = np.pi - lb
        xbb = xb[idx]
        denom = X_MAX - xbb
        u = np.clip(np.where(denom > 0, (axb - xbb) / np.where(denom > 0, denom, 1.0), 0.0), 0.0, 1.0)
        lo = np.zeros_like(u)
        hi = np.ones_like(u)
        for _ in range(iters):
            g, g1, _ = blend(u, ramp)
            f = c * (lb + u * span) + gap * g - axb
            fp = c * span + gap * g1
            lo = np.where(f < 0, u, lo)
            hi = np.where(f > 0, u, hi)
            un = u - f / fp
            un = np.where((un < lo) | (un > hi), 0.5 * (lo + hi), un)
            un = np.where(f == 0, u, un)
            done = np.all(np.abs(un - u) <= 1e-14)
            u = un
            if done:
                break
        d = np.sign(x[idx]) * np.degrees(lb + u * span)
        lon[idx] = ee.wrap_lon(d + lon0, 0.0)
    lat = np.where(np.isnan(lon), np.nan, lat)
    return lon, lat


# ------------------------------------------------------------------ canvas
class HybridCanvas:
    """The hybrid on a W x H pixel canvas; same scale, rows and margins as ``ee_project.Canvas``.

    Pixel convention as ee_project: (col, row) floats, row 0 = top (north), centres at .5.
    Rows y(phi) are identical to ``ee_project.Canvas``; columns are identical in the interior.
    """

    def __init__(self, width=WIDTH, height=HEIGHT, lon0=LON0, lat_min=LAT_MIN, lat_max=LAT_MAX,
                 lambda_b=DEFAULT_LAMBDA_B, ramp=DEFAULT_RAMP):
        self.lambda_b, self.ramp = _check_params(lambda_b, ramp)
        self.ee = ee.Canvas(width, height, lon0, lat_min, lat_max)
        self.W, self.H, self.lon0 = self.ee.W, self.ee.H, self.ee.lon0
        self.lat_min, self.lat_max = self.ee.lat_min, self.ee.lat_max
        self.scale, self.margin = self.ee.scale, self.ee.margin
        self.y_top, self.y_bot, self.globe_h = self.ee.y_top, self.ee.y_bot, self.ee.globe_h

    @property
    def is_plain_ee(self):
        return self.lambda_b >= 180.0

    def label(self):
        if self.is_plain_ee:
            return "Equal Earth"
        return f"Hybrid lambda_b={self.lambda_b:g} ramp={self.ramp:g}"

    def tag(self):
        return "ee" if self.is_plain_ee else f"lb{int(round(self.lambda_b)):03d}"

    # --- lon/lat <-> pixel
    def to_pixel(self, lon, lat):
        col_ee, row = self.ee.to_pixel(lon, lat)
        if self.is_plain_ee:
            return col_ee, row
        x, _ = forward(lon, lat, self.lon0, self.lambda_b, self.ramp)
        d = ee.wrap_lon(lon, self.lon0)
        col = np.where(np.abs(d) > self.lambda_b, (x + X_MAX) * self.scale, col_ee)
        return col, row

    def to_pixel_dl(self, dl, lat):
        """Pixel from unwrapped Δλ in [-180, 180] (so +180 lands on col W, -180 on col 0)."""
        x, y = forward_dl(dl, lat, self.lambda_b, self.ramp)
        col = (x + X_MAX) * self.scale
        row = self.margin + (self.y_top - y) * self.scale
        return col, row

    def xy_of_pixel(self, col, row):
        x = np.asarray(col, dtype=float) / self.scale - X_MAX
        y = self.y_top - (np.asarray(row, dtype=float) - self.margin) / self.scale
        return x, y

    def to_lonlat(self, col, row):
        x, y = self.xy_of_pixel(col, row)
        return inverse(x, y, self.lon0, self.lambda_b, self.ramp)

    def to_game_xz(self, lon, lat):
        col, row = self.to_pixel(lon, lat)
        return col, self.H - row

    def row_of_lat(self, lat):
        return self.ee.to_pixel(self.lon0, lat)[1]

    def stretch(self, lon, lat):
        return stretch(lon, lat, self.lon0, self.lambda_b, self.ramp)

    def on_globe(self):
        """bool[H, W]: pixel centre maps to a geographic point (any latitude)."""
        rows = np.arange(self.H) + 0.5
        cols = np.arange(self.W) + 0.5
        _, y = self.xy_of_pixel(0.0, rows)
        lat = _lat_from_y(y)
        ok_row = ~np.isnan(lat)
        if not self.is_plain_ee:
            return np.repeat(ok_row[:, None], self.W, axis=1)
        hw = half_width(np.where(ok_row, lat, 0.0)) * self.scale
        xc = np.abs(cols - self.W / 2.0)
        return ok_row[:, None] & (xc[None, :] <= hw[:, None])

    def globe_mask(self):
        """bool[H, W]: on the globe and inside the latitude window (cf. ee_project.Canvas.globe_mask)."""
        rows = np.arange(self.H) + 0.5
        _, y = self.xy_of_pixel(0.0, rows)
        in_window = (y <= self.y_top) & (y >= self.y_bot)
        return self.on_globe() & in_window[:, None]

    def km2_per_px(self):
        """Interior (Equal Earth) pixel area; band pixels cover km2_per_px / stretch."""
        return self.ee.km2_per_px()


# ------------------------------------------------------------------ checks (selftest + tests)
def roundtrip_error(canvas, row_chunk=128, col_step=1):
    """Max |px -> lonlat -> px| error (cols, rows) over the canvas; also returns #invalid rows."""
    cols = np.arange(0, canvas.W, col_step, dtype=float) + 0.5
    if col_step > 1:
        cols = np.unique(np.concatenate([cols, [0.5, 1.5, canvas.W - 1.5, canvas.W - 0.5]]))
    worst_c = worst_r = 0.0
    invalid_rows = []
    for r0 in range(0, canvas.H, row_chunk):
        rows = np.arange(r0, min(canvas.H, r0 + row_chunk), dtype=float) + 0.5
        cc, rr = np.meshgrid(cols, rows)
        lon, lat = canvas.to_lonlat(cc, rr)
        bad = np.isnan(lon)
        if bad.any():
            invalid_rows.extend(sorted(set(np.nonzero(bad.any(axis=1))[0] + r0)))
        c2, r2 = canvas.to_pixel(np.where(bad, 0.0, lon), np.where(bad, 0.0, lat))
        dc = np.abs(c2 - cc)
        dc = np.minimum(dc, canvas.W - dc)  # a centre within 1e-9 of the seam may come back at the other edge
        worst_c = max(worst_c, float(np.max(np.where(bad, 0.0, dc))))
        worst_r = max(worst_r, float(np.max(np.where(bad, 0.0, np.abs(r2 - rr)))))
    return worst_c, worst_r, invalid_rows


def wrap_adjacency(canvas):
    """Per row: (lon step across the seam between col 0 and col W-1) / (step between cols 0 and 1).

    ~1 means columns 0 and W-1 are neighbouring longitudes (±180) on that row. NaN rows are
    beyond the pole (top margin) or, for plain EE, rows where the edge is off the globe.
    """
    rows = np.arange(canvas.H) + 0.5
    c0, c1, cw = np.full_like(rows, 0.5), np.full_like(rows, 1.5), np.full_like(rows, canvas.W - 0.5)
    l0, _ = canvas.to_lonlat(c0, rows)
    l1, _ = canvas.to_lonlat(c1, rows)
    lw, _ = canvas.to_lonlat(cw, rows)
    seam = ee.wrap_lon(l0 - lw, 0.0)
    step = ee.wrap_lon(l1 - l0, 0.0)
    return seam / step


def forward_digest(lambda_b, ramp, n=20000, seed=0):
    rng = np.random.default_rng(seed)
    lon = rng.uniform(-180, 180, n)
    lat = rng.uniform(-90, 90, n)
    x, y = forward(lon, lat, LON0, lambda_b, ramp)
    lo, la = inverse(x, y, LON0, lambda_b, ramp)
    h = hashlib.sha256()
    for a in (x, y, lo, la):
        h.update(np.ascontiguousarray(a, dtype="<f8").tobytes())
    return h.hexdigest()


def selftest(lambdas=LAMBDA_B_CANDIDATES, ramp=DEFAULT_RAMP, full=True):
    out = []
    rng = np.random.default_rng(1)
    lon = rng.uniform(-180, 180, 200000)
    lat = rng.uniform(-90, 90, 200000)
    x_ee, y_ee = ee.forward(lon, lat, LON0)
    lats = np.linspace(-90, 90, 361)
    for lb in lambdas:
        x, y = forward(lon, lat, LON0, lb, ramp)
        d = ee.wrap_lon(lon, LON0)
        inn = np.abs(d) <= lb
        assert np.array_equal(x[inn], x_ee[inn]) and np.array_equal(y, y_ee), "interior/rows not bit-identical"
        # C0/C1/C2 at lambda_b (finite differences, both sides)
        h = 1e-4
        for s in (1.0, -1.0):
            xm = forward_dl(s * (lb - np.degrees(h)), lats, lb, ramp)[0]
            x0 = forward_dl(s * lb, lats, lb, ramp)[0]
            xp = forward_dl(s * (lb + np.degrees(h)), lats, lb, ramp)[0]
            assert np.array_equal(x0, ee.forward(np.full_like(lats, s * lb), lats, 0.0)[0])
            sl, sr = (x0 - xm) / h, (xp - x0) / h
            assert np.max(np.abs(sl - sr)) < 1e-6, "slope jump at lambda_b"
            h2 = 2e-5  # EE is linear inside, so the curvature just outside must vanish (C2)
            q = [forward_dl(s * (lb + i * np.degrees(h2)), lats, lb, ramp)[0] for i in (0, 1, 2)]
            assert np.max(np.abs((q[2] - 2 * q[1] + q[0]) / h2 ** 2)) < 5e-3, "curvature jump at lambda_b"
        # monotone
        dl = np.linspace(-180, 180, 36001)
        xx = forward_dl(dl[None, :], lats[:, None], lb, ramp)[0]
        assert np.all(np.diff(xx, axis=1) > 0), "not strictly monotone"
        assert np.all(dx_dlambda(dl[None, :], lats[:, None], lb, ramp) > 0)
        # edges
        assert np.max(np.abs(forward_dl(np.full_like(lats, 180.0), lats, lb, ramp)[0] - X_MAX)) == 0
        assert np.max(np.abs(forward_dl(np.full_like(lats, -180.0), lats, lb, ramp)[0] + X_MAX)) == 0
        # inverse round trip (lon/lat)
        lo, la = inverse(x, y, LON0, lb, ramp)
        dlon = np.abs(ee.wrap_lon(lo - lon, 0.0))
        assert np.nanmax(dlon) < 1e-9 and np.nanmax(np.abs(la - lat)) < 1e-9, "lon/lat round trip"
        c = HybridCanvas(lambda_b=lb, ramp=ramp)
        wc, wr, bad_rows = roundtrip_error(c, col_step=1 if full else 7)
        assert wc < 0.01 and wr < 0.01, (wc, wr)
        top_rows = int(np.ceil(c.margin - 0.5))
        assert bad_rows == list(range(top_rows)), "only the rows north of the pole may be invalid"
        ratio = wrap_adjacency(c)
        valid = ~np.isnan(ratio)
        assert valid.sum() == c.H - top_rows and np.all(np.abs(ratio[valid] - 1.0) < 1e-3), "wrap"
        assert forward_digest(lb, ramp) == forward_digest(lb, ramp)
        out.append(f"lambda_b={lb:g}: interior bit-identical, C2 at lambda_b, monotone, edges exact, "
                   f"round trip {wc:.2e}/{wr:.2e} px ({'full canvas' if full else 'every 7th column'}), "
                   f"wrap ratio {np.nanmin(ratio[valid]):.6f}..{np.nanmax(ratio[valid]):.6f} on {valid.sum()} rows")
    # lambda_b = 180 is plain EE, pixel-identical to ee_project.Canvas
    c = HybridCanvas(lambda_b=180.0)
    col, row = c.to_pixel(lon, lat)
    col_e, row_e = ee.Canvas(WIDTH, HEIGHT, LON0, LAT_MIN, LAT_MAX).to_pixel(lon, lat)
    assert np.array_equal(col, col_e) and np.array_equal(row, row_e)
    out.append("lambda_b=180 reproduces ee_project.Canvas exactly")
    return out


# ------------------------------------------------------------------ CLI
def _lambdas(a):
    return (float(a.lambda_b),) if a.lambda_b is not None else LAMBDA_B_CANDIDATES


def main(argv=None):
    ap = argparse.ArgumentParser(description="Hybrid Equal Earth projection (DEC-035)")
    ap.add_argument("cmd", choices=["selftest", "info", "preview"])
    ap.add_argument("--lambda-b", type=float, default=None, help="interior half-width in degrees (default: 60, 90 and 120)")
    ap.add_argument("--ramp", type=float, default=DEFAULT_RAMP, help="blend ramp fraction r in (0, 1] (default 0.5)")
    ap.add_argument("--quick", action="store_true", help="selftest: round trip on every 7th column only")
    ap.add_argument("--check", action="store_true", help="preview: compute and validate everything, write nothing")
    ap.add_argument("--out", type=Path, default=BUILD_DIR, help="preview/info output folder (default build/projection)")
    ap.add_argument("--no-download", action="store_true", help="preview: fail instead of downloading Natural Earth")
    a = ap.parse_args(argv)
    lambdas = _lambdas(a)
    if a.cmd == "selftest":
        for line in selftest(lambdas, a.ramp, full=not a.quick):
            print(line)
        print("selftest ok")
        return 0
    from projection import places, reports
    if a.cmd == "info":
        c = HybridCanvas(lambda_b=lambdas[0], ramp=a.ramp)
        print(f"canvas {c.W}x{c.H}  lon0={c.lon0}  seam at {float(ee.wrap_lon(c.lon0 + 180, 0)):.3f}  "
              f"latitudes {c.lat_min:g}..{c.lat_max:g}  scale {c.scale:.4f} px/rad  margin {c.margin:.2f} rows top & bottom")
        print(f"interior {c.km2_per_px():.2f} km2/px; rows identical to ee_project.Canvas; ramp r={a.ramp:g}")
        print(reports.band_summary(lambdas, a.ramp))
        table = places.table(lambdas, a.ramp)
        print(places.format_table(table))
        if not a.check:
            p = places.write_csv(table, a.out / "places.csv")
            print("wrote", p)
        return 0
    from projection import render
    return render.run_preview(lambdas, a.ramp, a.out, check=a.check, download=not a.no_download)


if __name__ == "__main__":
    _tools = str(Path(__file__).resolve().parents[1])
    if _tools not in sys.path:
        sys.path.insert(0, _tools)
    from projection.hybrid import main as _main  # the package copy, so every module shares one instance
    sys.exit(_main())
