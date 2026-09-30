"""Forward hybrid: interior exactness, C0/C1/C2 at lambda_b, monotonicity, edges, equator identity."""
import numpy as np
import pytest

from projection import hybrid

ee = hybrid.ee
LATS = np.linspace(-90, 90, 361)
H_RAD = 1e-4


def test_interior_bit_identical(lambda_b, ramp):
    rng = np.random.default_rng(7)
    lon = rng.uniform(-180, 180, 100000)
    lat = rng.uniform(-90, 90, 100000)
    x, y = hybrid.forward(lon, lat, hybrid.LON0, lambda_b, ramp)
    xe, ye = ee.forward(lon, lat, hybrid.LON0)
    inner = np.abs(ee.wrap_lon(lon, hybrid.LON0)) <= lambda_b
    assert inner.sum() > 1000 and (~inner).sum() > 1000
    assert np.array_equal(x[inner], xe[inner])
    assert np.array_equal(y, ye)  # rows identical everywhere
    assert np.all(np.abs(x[~inner]) >= np.abs(xe[~inner]))


def test_canvas_interior_and_rows_identical(lambda_b):
    rng = np.random.default_rng(8)
    lon = rng.uniform(-180, 180, 50000)
    lat = rng.uniform(-60, 90, 50000)
    c = hybrid.HybridCanvas(lambda_b=lambda_b)
    e = ee.Canvas(hybrid.WIDTH, hybrid.HEIGHT, hybrid.LON0, hybrid.LAT_MIN, hybrid.LAT_MAX)
    col, row = c.to_pixel(lon, lat)
    ce, re_ = e.to_pixel(lon, lat)
    inner = np.abs(ee.wrap_lon(lon, hybrid.LON0)) <= lambda_b
    assert np.array_equal(col[inner], ce[inner])
    assert np.array_equal(row, re_)
    assert (c.scale, c.margin, c.y_top) == (e.scale, e.margin, e.y_top)


def test_plain_ee_passthrough():
    c = hybrid.HybridCanvas(lambda_b=180.0)
    e = ee.Canvas(hybrid.WIDTH, hybrid.HEIGHT, hybrid.LON0, hybrid.LAT_MIN, hybrid.LAT_MAX)
    lon = np.linspace(-180, 180, 1001)
    lat = np.linspace(-60, 90, 1001)
    assert all(np.array_equal(a, b) for a, b in zip(c.to_pixel(lon, lat), e.to_pixel(lon, lat)))


@pytest.mark.parametrize("side", [1.0, -1.0])
def test_continuity_c1_c2_at_lambda_b(lambda_b, ramp, side):
    hd = np.degrees(H_RAD)
    f = lambda dl: hybrid.forward_dl(np.full_like(LATS, side * dl), LATS, lambda_b, ramp)[0]  # noqa: E731
    xm, x0, xp = f(lambda_b - hd), f(lambda_b), f(lambda_b + hd)
    # C0: the boundary value is exactly Equal Earth
    assert np.array_equal(x0, ee.forward(np.full_like(LATS, side * lambda_b), LATS, 0.0)[0])
    # C1: one-sided slopes agree (a C0-only kink would differ by O(1))
    sl, sr = (x0 - xm) / H_RAD, (xp - x0) / H_RAD
    assert np.max(np.abs(sr - sl)) < 1e-6
    # C2: one-sided second differences agree and the gap shrinks with h (a C1-only u^2 blend
    # leaves a constant gap of ~0.5..2 here); step 2e-5 rad keeps rounding noise ~1e-5
    def curv_gap(h):
        hdd = np.degrees(h)
        g = [f(lambda_b + i * hdd) for i in (-2, -1, 0, 1, 2)]
        cl = (g[2] - 2 * g[1] + g[0]) / h ** 2
        cr = (g[4] - 2 * g[3] + g[2]) / h ** 2
        return np.max(np.abs(cr - cl))
    assert curv_gap(2e-5) < 5e-3
    assert curv_gap(2e-5) < 0.5 * curv_gap(1e-4)


def test_c1_detector_is_sensitive():
    """Negative control: the same slope check flags a kinked (C0-only, linear g) blend."""
    lb = 90.0
    hd = np.degrees(H_RAD)
    w = hybrid.half_width(LATS)

    def kinked(dl):
        u = np.clip((np.radians(dl) - np.radians(lb)) / (np.pi - np.radians(lb)), 0, 1)
        return hybrid.forward_dl(np.full_like(LATS, dl), LATS, 180.0)[0] + (hybrid.X_MAX - w) * u

    sl = (kinked(lb) - kinked(lb - hd)) / H_RAD
    sr = (kinked(lb + hd) - kinked(lb)) / H_RAD
    assert np.max(np.abs(sr - sl)) > 0.1


def test_analytic_derivative_matches_fd(lambda_b, ramp):
    dl = np.linspace(-179.9, 179.9, 3599)
    lat = np.full_like(dl, 64.0)
    hd = 1e-6
    fd = (hybrid.forward_dl(dl + hd, lat, lambda_b, ramp)[0]
          - hybrid.forward_dl(dl - hd, lat, lambda_b, ramp)[0]) / np.radians(2 * hd)
    an = hybrid.dx_dlambda(dl, lat, lambda_b, ramp)
    assert np.max(np.abs(fd - an)) < 1e-6
    st = hybrid.stretch(dl + hybrid.LON0, lat, hybrid.LON0, lambda_b, ramp)
    assert np.allclose(st, an / (hybrid.half_width(lat) / np.pi), rtol=0, atol=1e-9)


def test_c2_at_ramp_junction_and_seam(ramp):
    g, g1, g2 = hybrid.blend(np.array([0.0, ramp, 1.0]), ramp)
    assert g[0] == 0 and g1[0] == 0 and g2[0] == 0
    assert g[2] == pytest.approx(1.0, abs=1e-15)
    assert g2[2] == 0.0  # seam: second derivative 0 -> the wrap is C2 as well
    eps = 1e-7
    gl = hybrid.blend(np.array([ramp - eps]), ramp)
    gr = hybrid.blend(np.array([min(ramp + eps, 1.0)]), ramp)
    assert abs(gl[1][0] - gr[1][0]) < 1e-5 and abs(gl[2][0] - gr[2][0]) < 1e-4


def test_strictly_monotone(lambda_b, ramp):
    dl = np.linspace(-180, 180, 36001)
    x = hybrid.forward_dl(dl[None, :], LATS[:, None], lambda_b, ramp)[0]
    assert np.all(np.diff(x, axis=1) > 0)
    assert np.all(hybrid.dx_dlambda(dl[None, :], LATS[:, None], lambda_b, ramp) > 0)


def test_edges_reached_on_every_row(lambda_b, ramp):
    lat = np.linspace(-90, 90, 3601)
    assert np.all(hybrid.forward_dl(np.full_like(lat, 180.0), lat, lambda_b, ramp)[0] == hybrid.X_MAX)
    assert np.all(hybrid.forward_dl(np.full_like(lat, -180.0), lat, lambda_b, ramp)[0] == -hybrid.X_MAX)
    # the wrapped forward: lon0 + 180 is Δλ = -180 -> the left edge
    x, _ = hybrid.forward(np.full_like(lat, hybrid.LON0 + 180.0), lat, hybrid.LON0, lambda_b, ramp)
    assert np.all(x == -hybrid.X_MAX)
    c = hybrid.HybridCanvas(lambda_b=lambda_b, ramp=ramp)
    col_r, _ = c.to_pixel_dl(np.full_like(lat, 180.0), lat)
    col_l, _ = c.to_pixel_dl(np.full_like(lat, -180.0), lat)
    assert np.allclose(col_r, c.W, atol=1e-9) and np.allclose(col_l, 0.0, atol=1e-9)


def test_identity_at_equator(lambda_b, ramp):
    dl = np.linspace(-180, 180, 7201)
    x = hybrid.forward_dl(dl, np.zeros_like(dl), lambda_b, ramp)[0]
    xe = hybrid.forward_dl(dl, np.zeros_like(dl), 180.0)[0]
    assert np.max(np.abs(x - xe)) < 1e-12
    assert np.all(hybrid.half_width(LATS) <= hybrid.X_MAX + 1e-15)


def test_parameter_validation():
    with pytest.raises(ValueError):
        hybrid.forward(0, 0, lambda_b=0)
    with pytest.raises(ValueError):
        hybrid.forward(0, 0, lambda_b=200)
    with pytest.raises(ValueError):
        hybrid.forward(0, 0, ramp=0.0)
    with pytest.raises(ValueError):
        hybrid.forward_dl(181.0, 0.0)
