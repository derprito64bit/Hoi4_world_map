"""Inverse hybrid: lon/lat and pixel round trips, the wrap-adjacency property, determinism."""
import numpy as np

from projection import hybrid

ee = hybrid.ee


def test_lonlat_round_trip(lambda_b, ramp):
    rng = np.random.default_rng(3)
    lon = rng.uniform(-180, 180, 200000)
    lat = rng.uniform(-90, 90, 200000)
    x, y = hybrid.forward(lon, lat, hybrid.LON0, lambda_b, ramp)
    lo, la = hybrid.inverse(x, y, hybrid.LON0, lambda_b, ramp)
    assert not np.isnan(lo).any()
    assert np.max(np.abs(ee.wrap_lon(lo - lon, 0.0))) < 1e-9
    assert np.max(np.abs(la - lat)) < 1e-9


def test_pixel_round_trip_whole_canvas(lambda_b):
    """Every row, every 5th column plus both edge column pairs (the full canvas runs in `selftest`)."""
    c = hybrid.HybridCanvas(lambda_b=lambda_b)
    wc, wr, bad_rows = hybrid.roundtrip_error(c, col_step=5)
    assert wc < 0.01 and wr < 0.01
    # only the rows north of the North Pole (the top margin) have no geographic coordinate
    assert bad_rows == list(range(int(np.ceil(c.margin - 0.5))))


def test_outside_is_nan():
    lo, la = hybrid.inverse(np.array([hybrid.X_MAX * 1.01, 0.0]), np.array([0.0, hybrid.Y_MAX * 1.01]))
    assert np.isnan(lo).all() and np.isnan(la).all()
    # plain EE: beyond the curved outline at 70 N is off the globe; the hybrid covers it
    x = hybrid.X_MAX * 0.95
    y = float(ee.forward(0.0, 70.0)[1])
    assert np.isnan(hybrid.inverse(x, y, lambda_b=180.0)[0])
    assert not np.isnan(hybrid.inverse(x, y, lambda_b=90.0)[0])


def test_wrap_adjacency_every_row(lambda_b, ramp):
    """Columns 0 and W-1 are neighbouring longitudes (either side of lon0 ± 180) on every row."""
    c = hybrid.HybridCanvas(lambda_b=lambda_b, ramp=ramp)
    ratio = hybrid.wrap_adjacency(c)
    top = int(np.ceil(c.margin - 0.5))
    assert np.isnan(ratio[:top]).all()
    assert np.all(np.abs(ratio[top:] - 1.0) < 1e-3)
    rows = np.arange(top, c.H) + 0.5
    l0, _ = c.to_lonlat(np.full_like(rows, 0.5), rows)
    lw, _ = c.to_lonlat(np.full_like(rows, c.W - 0.5), rows)
    seam = ee.wrap_lon(hybrid.LON0 + 180.0, 0.0)
    # left edge pixel is just east of the seam meridian, right edge pixel just west of it
    assert np.all(ee.wrap_lon(l0 - seam, 0.0) > 0) and np.all(ee.wrap_lon(lw - seam, 0.0) < 0)
    assert np.all(np.abs(ee.wrap_lon(l0 - seam, 0.0)) < 0.2) and np.all(np.abs(ee.wrap_lon(lw - seam, 0.0)) < 0.2)


def test_plain_ee_does_not_wrap():
    """Control: pure Equal Earth fails the same property away from the equator."""
    ratio = hybrid.wrap_adjacency(hybrid.HybridCanvas(lambda_b=180.0))
    assert np.isnan(ratio).sum() > 1500


def test_globe_mask_full_rectangle(lambda_b):
    c = hybrid.HybridCanvas(512, 256, lambda_b=lambda_b)
    on = c.on_globe()
    assert on[int(np.ceil(c.margin)):].all() and not on[0].any()
    e = hybrid.HybridCanvas(512, 256, lambda_b=180.0)
    em = ee.Canvas(512, 256, hybrid.LON0, hybrid.LAT_MIN, hybrid.LAT_MAX).globe_mask()
    assert (e.globe_mask() != em).sum() <= 4  # same outline up to boundary-centre rounding


def test_deterministic():
    for lb in hybrid.LAMBDA_B_CANDIDATES:
        assert hybrid.forward_digest(lb, hybrid.DEFAULT_RAMP) == hybrid.forward_digest(lb, hybrid.DEFAULT_RAMP)
    a = hybrid.HybridCanvas(lambda_b=90.0).to_lonlat(np.arange(5120) + 0.5, np.full(5120, 700.5))
    b = hybrid.HybridCanvas(lambda_b=90.0).to_lonlat(np.arange(5120) + 0.5, np.full(5120, 700.5))
    assert all(np.array_equal(p, q) for p, q in zip(a, b))
