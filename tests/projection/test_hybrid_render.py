"""Preview pipeline pieces on synthetic geometry (no Natural Earth download needed)."""
import struct
import zipfile

import numpy as np
import pytest

from projection import hybrid, metrics, naturalearth, places, render, reports


def _shp(records):
    """Build a tiny Polygon shapefile in memory: records = [[ring(n,2), ...], ...]."""
    body = b""
    for i, rec in enumerate(records, 1):
        pts = np.vstack(rec)
        parts = np.cumsum([0] + [len(r) for r in rec[:-1]])
        content = struct.pack("<i4d", 5, *pts[:, 0].min(0).ravel()[:1], pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max())
        content += struct.pack("<ii", len(rec), len(pts)) + parts.astype("<i4").tobytes() + pts.astype("<f8").tobytes()
        body += struct.pack(">ii", i, len(content) // 2) + content
    header = struct.pack(">i5ii", 9994, 0, 0, 0, 0, 0, (100 + len(body)) // 2) + struct.pack("<ii", 1000, 5)
    header += struct.pack("<8d", -180, -90, 180, 90, 0, 0, 0, 0)
    return header + body


def _square(lon0, lat0, size, clockwise=True):
    r = np.array([[lon0, lat0], [lon0, lat0 + size], [lon0 + size, lat0 + size], [lon0 + size, lat0], [lon0, lat0]], float)
    return r if clockwise else r[::-1].copy()


def test_shapefile_reader_and_holes():
    outer = _square(0, 0, 10)
    hole = _square(3, 3, 2, clockwise=False)
    data = _shp([[outer, hole], [_square(20, 20, 1)]])
    recs = naturalearth.read_polygons_shp(data)
    assert len(recs) == 2 and len(recs[0]) == 2
    assert np.array_equal(recs[0][0], outer)
    assert not naturalearth.ring_is_hole(recs[0][0]) and naturalearth.ring_is_hole(recs[0][1])
    with pytest.raises(naturalearth.DataError):
        naturalearth.read_polygons_shp(b"x" * 120)


def test_pinned_download_refuses_bad_hash(tmp_path):
    bad = tmp_path / naturalearth.LAND_ZIP
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("ne_50m_land.shp", b"")
    with pytest.raises(naturalearth.DataError):
        naturalearth.land_zip(download=False, raw_dir=tmp_path)
    with pytest.raises(naturalearth.DataError):
        naturalearth.land_zip(download=False, raw_dir=tmp_path / "missing")


def test_densify_max_step():
    p = render.densify(np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 3.0]]))
    assert np.max(np.abs(np.diff(p, axis=0))) <= render.DENSIFY_DEG + 1e-12
    assert np.array_equal(p[0], [0, 0]) and np.array_equal(p[-1], [10, 3])


def test_seam_split_island():
    """An island straddling the seam (like St Lawrence Island) is drawn on both edges."""
    seam = float(hybrid.ee.wrap_lon(hybrid.LON0 + 180.0, 0.0))
    island = _square(seam - 2.0, 63.0, 1.0)
    island[:, 0] = np.where(island[:, 0] > seam - 1.5, seam + 1.0, island[:, 0])
    shapes = render.land_shapes([[island]], hybrid.LON0)
    assert len(shapes) == 2
    c = hybrid.HybridCanvas(512, 256, lambda_b=90.0)
    m = render.land_mask(c, shapes)
    cols = np.nonzero(m)[1]
    assert cols.min() == 0 and cols.max() == c.W - 1
    assert len(render.seam_crossings([[island]], hybrid.LON0)) == 1


def test_render_deterministic():
    recs = [[_square(-10, 40, 20)], [_square(150, -40, 25)], [_square(-175, 60, 10)]]
    shapes = render.land_shapes(recs, hybrid.LON0)
    outs = []
    for _ in range(2):
        c = hybrid.HybridCanvas(512, 256, lambda_b=90.0)
        m = render.land_mask(c, shapes)
        outs.append(render.png_bytes(render.downscale(render.render_land(c, m))))
    assert outs[0] == outs[1]


def test_area_factor_equals_stretch_and_ee_is_equal_area():
    rng = np.random.default_rng(5)
    dl = rng.uniform(-179.5, 179.5, 5000)
    lat = rng.uniform(-80, 80, 5000)
    te = metrics.tissot(dl, lat, 180.0, 0.5)
    assert np.allclose(te["area"], 1.0, atol=1e-6)
    th = metrics.tissot(dl, lat, 90.0, 0.5)
    s = hybrid.stretch(dl + hybrid.LON0, lat, hybrid.LON0, 90.0, 0.5)
    assert np.allclose(th["area"], s, atol=1e-5)


def test_places_table_and_csv_deterministic(tmp_path):
    t = places.table()
    assert len(t) == 3 * len(places.KEY_PLACES)
    by = {(r["place"], r["lambda_b"]): r for r in t}
    assert by[("Beijing", "120")]["zone"] == "interior" and by[("Anadyr", "60")]["zone"] == "band"
    assert all(float(r["stretch_ew"]) == 1.0 for r in t if r["zone"] == "interior")
    assert all(abs(float(r["area_factor"]) - float(r["stretch_ew"])) < 2e-3 for r in t)
    a = places.write_csv(t, tmp_path / "a.csv").read_bytes()
    b = places.write_csv(places.table(), tmp_path / "b.csv").read_bytes()
    assert a == b


def test_top_edge_numbers():
    c = hybrid.HybridCanvas()
    opts = reports.top_edge_options()
    cur = opts[0]
    assert cur["lat_min"] == -60.0 and abs(cur["top_margin"] - c.margin) < 1e-9
    assert abs(cur["kaffeklubben_row"] - float(c.row_of_lat(83.66))) < 1e-9
    for o in opts:  # the canvas height is fixed: rows are conserved
        gh = (c.y_top - float(hybrid.ee.forward(0.0, o["lat_min"])[1])) * c.scale
        assert abs(o["top_margin"] + gh + o["bottom_margin"] - c.H) < 1e-9
