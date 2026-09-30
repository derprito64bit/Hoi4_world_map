"""P00d previews: land + graticule per variant, distortion heat maps, contact sheets, CSV reports.

Everything is rendered from Natural Earth 1:50m land (preview only) on the full 5120 x 2304
canvas and box-downscaled 2x to 2560 x 1152; heat maps are computed per pixel on a 2560 x 1152
canvas with the same geography. Output goes to build/projection/ (gitignored); nothing is
committed. Deterministic: no randomness, sorted/fixed iteration, PNGs written from bytes.
"""
from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from shapely.affinity import translate
from shapely.geometry import Polygon, box

from projection import hybrid, metrics, naturalearth, places, reports

ee = hybrid.ee
PREVIEW_W, PREVIEW_H = 2560, 1152
SEAM_BAND_PX = 50
DENSIFY_DEG = 0.25

OCEAN = (62, 104, 160)
OCEAN_OUT = (44, 74, 116)      # on the globe but south of the 60° S frame
OFF_GLOBE = (38, 38, 42)
LAND = (206, 199, 182)
GRATICULE = (255, 255, 255, 90)
LB_COLOUR = (230, 40, 40, 255)
FRAME = (15, 15, 15, 255)

STRETCH_STOPS = ((1.0, (247, 247, 247)), (1.25, (254, 224, 144)), (1.5, (253, 174, 97)), (2.0, (244, 109, 67)),
                 (3.0, (215, 48, 39)), (4.5, (165, 0, 38)), (7.0, (70, 0, 40)))
OMEGA_STOPS = ((0.0, (247, 251, 255)), (10.0, (198, 219, 239)), (20.0, (107, 174, 214)), (30.0, (33, 113, 181)),
               (45.0, (8, 48, 107)), (60.0, (84, 39, 143)), (90.0, (40, 0, 60)))


# ------------------------------------------------------------------ geometry
def densify(pts, step=DENSIFY_DEG):
    """Insert points so no segment exceeds ``step`` degrees in Δλ or latitude."""
    pts = np.asarray(pts, dtype=float)
    if len(pts) < 2:
        return pts
    p0, p1 = pts[:-1], pts[1:]
    n = np.maximum(1, np.ceil(np.max(np.abs(p1 - p0), axis=1) / step)).astype(np.int64)
    seg = np.repeat(np.arange(len(n)), n)
    start = np.cumsum(n) - n
    t = (np.arange(n.sum()) - start[seg]) / n[seg]
    out = p0[seg] + t[:, None] * (p1 - p0)[seg]
    return np.vstack([out, pts[-1:]])


def _pieces(dl_ring):
    """Split a ring given in unwrapped Δλ at the seam; yield (exterior, [holes]) in [-180, 180]."""
    if dl_ring[:, 0].min() >= -180.0 and dl_ring[:, 0].max() <= 180.0:
        yield dl_ring, []
        return
    poly = Polygon(dl_ring).buffer(0)
    for shift in (0.0, -360.0, 360.0):
        piece = poly.intersection(box(-180.0 - shift, -90.0, 180.0 - shift, 90.0))
        if piece.is_empty:
            continue
        piece = translate(piece, xoff=shift)
        geoms = getattr(piece, "geoms", [piece])
        for g in geoms:
            if g.geom_type != "Polygon" or g.area == 0:
                continue
            ext = np.clip(np.asarray(g.exterior.coords), [-180, -90], [180, 90])
            yield ext, [np.clip(np.asarray(i.coords), [-180, -90], [180, 90]) for i in g.interiors]


def land_shapes(records, lon0, lat_floor=-61.0):
    """[(dl_lat_ring, fill)] in unwrapped Δλ/lat, seam-split; fill 1 = land, 0 = hole. Stable order."""
    out = []
    for rec in records:
        if not rec or max(r[:, 1].max() for r in rec) < lat_floor:
            continue  # Antarctica and the islands south of the frame
        ext, holes = [], []
        for ring in rec:
            (holes if naturalearth.ring_is_hole(ring) else ext).append(ring)
        for fill, rings in ((1, ext), (0, holes)):
            for ring in rings:
                d = np.asarray(ee.wrap_lon(ring[:, 0], lon0), dtype=float)
                d = np.degrees(np.unwrap(np.radians(d)))
                for e, inner in _pieces(np.column_stack([d, ring[:, 1]])):
                    out.append((e, fill))
                    out.extend((i, 1 - fill) for i in inner)
    return out


def seam_crossings(records, lon0):
    """Rings north of 60° S crossed by the seam meridian: list of (lon_min, lon_max, lat_min, lat_max)."""
    res = []
    for rec in records:
        for ring in rec:
            if ring[:, 1].max() < -60:
                continue
            d = np.degrees(np.unwrap(np.radians(np.asarray(ee.wrap_lon(ring[:, 0], lon0), dtype=float))))
            if d.min() < -180 or d.max() > 180:
                res.append((float(ring[:, 0].min()), float(ring[:, 0].max()),
                            float(ring[:, 1].min()), float(ring[:, 1].max())))
    return res


def land_mask(canvas, shapes):
    """uint8[H, W] (0/255) land raster of the seam-split shapes on ``canvas``."""
    img = Image.new("L", (canvas.W, canvas.H), 0)
    dr = ImageDraw.Draw(img)
    for ring, fill in shapes:
        p = densify(ring)
        col, row = canvas.to_pixel_dl(p[:, 0], p[:, 1])
        if len(col) >= 3:
            dr.polygon(list(zip(col.tolist(), row.tolist())), fill=255 * fill)
    return np.asarray(img, dtype=np.uint8)


# ------------------------------------------------------------------ drawing helpers
def _line(canvas, dl, lat):
    col, row = canvas.to_pixel_dl(dl, lat)
    return list(zip(col.tolist(), row.tolist()))


def draw_graticule(canvas, img, scale=1.0, frame=True):
    """Graticule every 15°, λb meridians, the 60° S..90° N frame (and EE's outline)."""
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    lat_lo = float(ee.inverse(0.0, canvas.y_top - (canvas.H - canvas.margin) / canvas.scale)[1])
    lat_lo = max(-90.0, min(lat_lo, canvas.lat_min) - 0.5)
    lats = np.arange(lat_lo, 90.0 + 1e-9, 0.25)
    wide = max(1, int(round(2 * scale)))
    for lon in range(-180, 180, 15):
        d = float(ee.wrap_lon(lon, canvas.lon0))
        dr.line(_line(canvas, np.full_like(lats, d), lats), fill=GRATICULE, width=wide)
    dls = np.arange(-180.0, 180.0 + 1e-9, 0.25)
    for la in range(-45, 90, 15):
        dr.line(_line(canvas, dls, np.full_like(dls, float(la))), fill=GRATICULE, width=wide)
    if not canvas.is_plain_ee:
        for s in (-1, 1):
            dr.line(_line(canvas, np.full_like(lats, s * canvas.lambda_b), lats), fill=LB_COLOUR,
                    width=max(1, int(round(5 * scale))))
    if frame:
        fw = max(1, int(round(5 * scale)))
        for la in (canvas.lat_min, canvas.lat_max):
            dr.line(_line(canvas, dls, np.full_like(dls, la)), fill=FRAME, width=fw)
        if canvas.is_plain_ee:
            for s in (-1, 1):
                dr.line(_line(canvas, np.full_like(lats, s * 180.0), lats), fill=FRAME, width=fw)
        dr.rectangle([0, 0, canvas.W - 1, canvas.H - 1], outline=FRAME, width=fw)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def _font(size):
    return ImageFont.load_default(size=size)


def label(img, text, xy=(10, None), size=20):
    img = img.copy()
    dr = ImageDraw.Draw(img)
    f = _font(size)
    l, t, r, b = dr.textbbox((0, 0), text, font=f)
    x = xy[0]
    y = xy[1] if xy[1] is not None else img.height - (b - t) - 22
    dr.rectangle([x - 6, y - 6, x + (r - l) + 6, y + (b - t) + 8], fill=(255, 255, 255))
    dr.text((x - l, y - t), text, fill=(0, 0, 0), font=f)
    return img


def colour_ramp(v, stops, log=False):
    vals = np.array([s[0] for s in stops], dtype=float)
    cols = np.array([s[1] for s in stops], dtype=float)
    vv = np.asarray(v, dtype=float)
    if log:
        vals, vv = np.log(vals), np.log(np.maximum(vv, 1e-12))
    vv = np.clip(vv, vals[0], vals[-1])
    out = np.stack([np.interp(vv, vals, cols[:, i]) for i in range(3)], axis=-1)
    return np.round(out).astype(np.uint8)


def legend(img, stops, title, log=False, fmt="{:g}"):
    img = img.copy()
    dr = ImageDraw.Draw(img)
    f = _font(15)
    bw, bh = 420, 16
    x0, y0 = img.width - bw - 30, img.height - bh - 48
    vals = np.array([s[0] for s in stops], dtype=float)
    t = np.linspace(0, 1, bw)
    if log:
        v = np.exp(np.log(vals[0]) + t * (np.log(vals[-1]) - np.log(vals[0])))
    else:
        v = vals[0] + t * (vals[-1] - vals[0])
    bar = colour_ramp(v, stops, log)
    dr.rectangle([x0 - 10, y0 - 30, x0 + bw + 10, y0 + bh + 26], fill=(255, 255, 255))
    img.paste(Image.fromarray(np.repeat(bar[None, :, :], bh, axis=0)), (x0, y0))
    dr.text((x0, y0 - 26), title, fill=(0, 0, 0), font=f)
    for val in vals:
        tt = (np.log(val) - np.log(vals[0])) / (np.log(vals[-1]) - np.log(vals[0])) if log else \
            (val - vals[0]) / (vals[-1] - vals[0])
        xx = x0 + int(round(tt * (bw - 1)))
        dr.line([xx, y0 + bh, xx, y0 + bh + 4], fill=(0, 0, 0))
        s = fmt.format(val)
        l, _, r, _ = dr.textbbox((0, 0), s, font=f)
        dr.text((xx - (r - l) // 2, y0 + bh + 5), s, fill=(0, 0, 0), font=f)
    return img


def downscale(mask_or_img, factor=2):
    if isinstance(mask_or_img, np.ndarray):
        h, w = mask_or_img.shape[:2]
        a = mask_or_img.astype(np.float64).reshape(h // factor, factor, w // factor, factor, *mask_or_img.shape[2:])
        return np.round(a.mean(axis=(1, 3))).astype(np.uint8)
    return mask_or_img.resize((mask_or_img.width // factor, mask_or_img.height // factor), Image.BOX)


def png_bytes(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=6)
    return buf.getvalue()


# ------------------------------------------------------------------ images
def render_land(canvas, mask):
    """Full-resolution RGB preview: land on blue, off-globe dark, graticule + frame."""
    on = canvas.on_globe()
    window = canvas.globe_mask()
    rgb = np.empty((canvas.H, canvas.W, 3), np.uint8)
    rgb[:] = OFF_GLOBE
    rgb[on] = OCEAN_OUT
    rgb[window] = OCEAN
    rgb[(mask > 127) & on] = LAND
    return draw_graticule(canvas, Image.fromarray(rgb), scale=1.0)


def pixel_lonlat(canvas):
    rows, cols = np.mgrid[0:canvas.H, 0:canvas.W] + 0.5
    return canvas.to_lonlat(cols, rows)


def coast(mask_small):
    land = mask_small > 127
    return land & ~ndimage.binary_erosion(land, structure=np.ones((3, 3), bool), border_value=1)


def heat_image(canvas, values, stops, mask_small, title, log, fmt):
    rgb = colour_ramp(np.where(np.isnan(values), 1.0 if log else 0.0, values), stops, log)
    rgb[np.isnan(values)] = OFF_GLOBE
    rgb[coast(mask_small) & ~np.isnan(values)] = (0, 0, 0)
    img = draw_graticule(canvas, Image.fromarray(rgb), scale=0.5)
    img = legend(img, stops, title, log, fmt)
    return label(img, f"{canvas.label()}: {title}")


def sheet(images, labels, cols=2, tile=(1280, 576), pad=8):
    rows = (len(images) + cols - 1) // cols
    out = Image.new("RGB", (cols * tile[0] + (cols + 1) * pad, rows * tile[1] + (rows + 1) * pad), (255, 255, 255))
    for i, (im, text) in enumerate(zip(images, labels)):
        t = label(im.resize(tile, Image.BOX), text, xy=(12, 12), size=18)
        out.paste(t, (pad + (i % cols) * (tile[0] + pad), pad + (i // cols) * (tile[1] + pad)))
    return out


# ------------------------------------------------------------------ the preview run
def _land_stats(canvas, mask):
    """Full-res land statistics for one variant (lon/lat computed for land pixels only)."""
    land = (mask > 127) & canvas.globe_mask()
    rows, cols = np.nonzero(land)
    lon, lat = canvas.to_lonlat(cols + 0.5, rows + 0.5)
    d = np.abs(np.asarray(ee.wrap_lon(lon, canvas.lon0)))
    s = canvas.stretch(lon, lat)
    return {
        "variant": canvas.tag(), "lambda_b": f"{canvas.lambda_b:g}", "ramp": f"{canvas.ramp:g}",
        "land_px": int(land.sum()),
        "land_px_band": int((d > canvas.lambda_b).sum()) if not canvas.is_plain_ee else 0,
        "land_px_stretch_gt_1_5": int((s > 1.5).sum()), "land_px_stretch_gt_2": int((s > 2.0).sum()),
        "land_px_stretch_gt_3": int((s > 3.0).sum()), "max_land_stretch": f"{float(s.max()):.3f}",
        "land_px_within_50_of_seam": int(((cols < SEAM_BAND_PX) | (cols >= canvas.W - SEAM_BAND_PX)).sum()),
        "land_px_on_edge_columns": int(((cols == 0) | (cols == canvas.W - 1)).sum()),
    }


def _csv(rows, cols) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


def seam_sensitivity(records, lambda_b=90.0, ramp=hybrid.DEFAULT_RAMP, lon0s=(5.9, 10.9, 15.9)):
    rows = []
    for lon0 in lon0s:
        c = hybrid.HybridCanvas(lon0=lon0, lambda_b=lambda_b, ramp=ramp)
        m = land_mask(c, land_shapes(records, lon0))
        land = (m > 127) & c.globe_mask()
        cols = np.nonzero(land)[1]
        near = (cols < SEAM_BAND_PX) | (cols >= c.W - SEAM_BAND_PX)
        cross = seam_crossings(records, lon0)
        pr = places.rows_for(places.SEAM_PLACES, lambda_b, ramp, lon0=lon0)
        row = {"lon0": f"{lon0:g}", "seam_lon": f"{float(ee.wrap_lon(lon0 + 180, 0)):.1f}", "lambda_b": f"{lambda_b:g}",
               "land_px_within_50_of_seam": int(near.sum()),
               "land_px_on_edge_columns": int(((cols == 0) | (cols == c.W - 1)).sum()),
               "rings_cut_by_seam": len(cross),
               "cut_rings": "; ".join(f"lon {a:.1f}..{b:.1f} lat {e:.1f}..{f:.1f}" for a, b, e, f in cross) or "-"}
        for p in pr:
            row[f"stretch {p['place']}"] = p["stretch_ew"]
            row[f"side {p['place']}"] = "E" if float(p["dlon"]) > 0 else "W"
        rows.append(row)
    return rows


def run_preview(lambdas, ramp, out_dir: Path, check=False, download=True):
    out_dir = Path(out_dir)
    records = naturalearth.load_land(download=download)
    files: dict[str, bytes] = {}
    text = []
    variants = [180.0] + [float(lb) for lb in lambdas]
    land_imgs, land_labels, stretch_imgs, stretch_labels, omega_imgs, omega_labels = [], [], [], [], [], []
    stats = []
    shapes = land_shapes(records, hybrid.LON0)
    for lb in variants:
        full = hybrid.HybridCanvas(lambda_b=lb, ramp=ramp)
        small = hybrid.HybridCanvas(PREVIEW_W, PREVIEW_H, lambda_b=lb, ramp=ramp)
        mask = land_mask(full, shapes)
        stats.append(_land_stats(full, mask))
        img = downscale(render_land(full, mask))
        img = label(img, f"{full.label()}  |  lon0 {full.lon0:g}, 60S..90N frame (black), graticule 15 deg"
                         + ("" if full.is_plain_ee else ", lambda_b meridians red"))
        files[f"previews/land_{full.tag()}.png"] = png_bytes(img)
        land_imgs.append(img)
        land_labels.append(full.label())
        mask_s = downscale(mask)
        lon, lat = pixel_lonlat(small)
        on = ~np.isnan(lon)
        d = np.where(on, ee.wrap_lon(np.where(on, lon, 0.0), small.lon0), 0.0)
        la = np.clip(np.where(on, lat, 0.0), -89.9, 89.9)
        t = metrics.tissot(d, la, lb, ramp)
        omega = np.where(on, t["omega_deg"], np.nan)
        om_img = heat_image(small, omega, OMEGA_STOPS, mask_s, "max angular distortion (deg)", False, "{:g}")
        files[f"previews/angular_{small.tag()}.png"] = png_bytes(om_img)
        omega_imgs.append(om_img)
        omega_labels.append(small.label())
        if not small.is_plain_ee:
            s = np.where(on, small.stretch(np.where(on, lon, 0.0), np.where(on, lat, 0.0)), np.nan)
            st_img = heat_image(small, s, STRETCH_STOPS, mask_s, "E-W stretch vs Equal Earth", True, "{:g}")
            files[f"previews/stretch_{small.tag()}.png"] = png_bytes(st_img)
            stretch_imgs.append(st_img)
            stretch_labels.append(small.label())
            area = np.where(on, t["area"], np.nan)  # numeric Jacobian; EE's own area factor is 1 on the unit sphere
            ar_img = heat_image(small, area, STRETCH_STOPS, mask_s, "area factor vs Equal Earth (interior 1.0)", True, "{:g}")
            files[f"previews/area_{small.tag()}.png"] = png_bytes(ar_img)
            dev = float(np.nanmax(np.abs(area - s)))
            text.append(f"{small.tag()}: area factor (numeric Jacobian) vs analytic E-W stretch: max |diff| {dev:.2e} "
                        "(identical by construction: y depends on latitude only)")
            if dev > 1e-3:
                raise RuntimeError(f"area factor and stretch disagree ({dev})")
    files["previews/compare.png"] = png_bytes(sheet(land_imgs, land_labels))
    files["previews/compare_stretch.png"] = png_bytes(sheet(stretch_imgs, stretch_labels, cols=1))
    files["previews/compare_angular.png"] = png_bytes(sheet(omega_imgs, omega_labels))
    table = places.table(lambdas, ramp)
    files["places.csv"] = places.csv_text(table).encode("utf-8")
    files["summary.csv"] = _csv(stats, list(stats[0].keys()))
    files["top_edge.csv"] = reports.top_edge_csv().encode("utf-8")
    seam = seam_sensitivity(records, ramp=ramp)
    files["seam_sensitivity.csv"] = _csv(seam, list(seam[0].keys()))
    text = [reports.band_summary(lambdas, ramp), places.format_table(table), reports.top_edge_report()] + text
    text.append("land statistics (full canvas, inside the 60S..90N window):")
    for s in stats:
        text.append("  " + ", ".join(f"{k}={v}" for k, v in s.items()))
    text.append("seam sensitivity (lambda_b 90):")
    for s in seam:
        text.append("  " + ", ".join(f"{k}={v}" for k, v in s.items()))
    report = "\n".join(text) + "\n"
    files["report.txt"] = report.encode("utf-8")
    print(report)
    for name in sorted(files):
        digest = hashlib.sha256(files[name]).hexdigest()
        if check:
            print(f"check {digest}  {name}")
        else:
            p = out_dir / name
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "wb") as fh:
                fh.write(files[name])
            print(f"wrote {digest}  {p}")
    return 0
