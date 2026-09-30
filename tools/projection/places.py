"""Key-place distortion table (P00d deliverable 4).

Coordinates are approximate city-centre (or cape) positions, WGS84, rounded to 0.01°; they are
only used to report distortion, never as map geometry.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import numpy as np

from projection import hybrid, metrics

# (name, lon, lat)
KEY_PLACES = (
    ("Anchorage", -149.90, 61.22),
    ("Nome", -165.41, 64.50),
    ("Anadyr", 177.51, 64.73),
    ("Petropavlovsk-Kamchatsky", 158.65, 53.02),
    ("Magadan", 150.80, 59.56),
    ("Yakutsk", 129.73, 62.03),
    ("Vladivostok", 131.89, 43.12),
    ("Tokyo", 139.69, 35.68),
    ("Sapporo", 141.35, 43.06),
    ("Honolulu", -157.86, 21.31),
    ("Auckland", 174.76, -36.85),
    ("Wellington", 174.78, -41.29),
    ("Sydney", 151.21, -33.87),
    ("Brisbane", 153.03, -27.47),
    ("Suva", 178.44, -18.14),
    ("Vancouver", -123.12, 49.28),
    ("Seattle", -122.33, 47.61),
    ("San Francisco", -122.42, 37.77),
    ("Los Angeles", -118.24, 34.05),
    ("Lima", -77.04, -12.05),
    ("Santiago", -70.67, -33.45),
    ("Beijing", 116.40, 39.90),
    ("Manila", 120.98, 14.60),
)

# extra points for the seam-sensitivity report
SEAM_PLACES = (
    ("Cape Dezhnev (Chukotka)", -169.65, 66.08),
    ("Anadyr", 177.51, 64.73),
    ("Cape Prince of Wales (Alaska)", -168.09, 65.64),
    ("Nome", -165.41, 64.50),
    ("Anchorage", -149.90, 61.22),
)

COLUMNS = ("lambda_b", "ramp", "place", "lon", "lat", "dlon", "zone", "u", "stretch_ew", "area_factor",
           "omega_ee_deg", "omega_hybrid_deg", "shift_px")


def rows_for(places, lambda_b, ramp, lon0=hybrid.LON0):
    names = [p[0] for p in places]
    lon = np.array([p[1] for p in places], dtype=float)
    lat = np.array([p[2] for p in places], dtype=float)
    d = hybrid.ee.wrap_lon(lon, lon0)
    s = hybrid.stretch(lon, lat, lon0, lambda_b, ramp)
    t_h = metrics.tissot(d, lat, lambda_b, ramp)
    t_e = metrics.tissot(d, lat, 180.0, ramp)
    c_h = hybrid.HybridCanvas(lon0=lon0, lambda_b=lambda_b, ramp=ramp)
    c_e = hybrid.HybridCanvas(lon0=lon0, lambda_b=180.0)
    shift = c_h.to_pixel(lon, lat)[0] - c_e.to_pixel(lon, lat)[0]
    lb = np.radians(lambda_b)
    u = np.clip((np.radians(np.abs(d)) - lb) / (np.pi - lb), 0, 1) if lambda_b < 180 else np.zeros_like(d)
    out = []
    for i, n in enumerate(names):
        out.append({
            "lambda_b": f"{lambda_b:g}", "ramp": f"{ramp:g}", "place": n,
            "lon": f"{lon[i]:.2f}", "lat": f"{lat[i]:.2f}", "dlon": f"{d[i]:.2f}",
            "zone": "interior" if abs(d[i]) <= lambda_b else "band",
            "u": f"{u[i]:.3f}", "stretch_ew": f"{s[i]:.3f}", "area_factor": f"{t_h['area'][i] / t_e['area'][i]:.3f}",
            "omega_ee_deg": f"{t_e['omega_deg'][i]:.1f}", "omega_hybrid_deg": f"{t_h['omega_deg'][i]:.1f}",
            "shift_px": f"{shift[i]:.1f}",
        })
    return out


def table(lambdas=hybrid.LAMBDA_B_CANDIDATES, ramp=hybrid.DEFAULT_RAMP, places=KEY_PLACES):
    rows = []
    for lb in lambdas:
        rows.extend(rows_for(places, lb, ramp))
    return rows


def csv_text(rows) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def write_csv(rows, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(csv_text(rows))
    return path


def format_table(rows) -> str:
    """One line per place: stretch (= area factor) per lambda_b, '*' marks interior."""
    lbs = sorted({r["lambda_b"] for r in rows}, key=float)
    by = {(r["place"], r["lambda_b"]): r for r in rows}
    names = list(dict.fromkeys(r["place"] for r in rows))
    head = f"{'place':26s} {'dlon':>8s} " + " ".join(f"{'lb=' + lb:>17s}" for lb in lbs)
    lines = ["key places: E-W stretch = area factor vs EE (omega hybrid/EE deg); * = interior (pure EE)", head]
    for n in names:
        first = by[(n, lbs[0])]
        cells = []
        for lb in lbs:
            r = by[(n, lb)]
            mark = "*" if r["zone"] == "interior" else " "
            cells.append(f"{mark}{float(r['stretch_ew']):5.2f} ({float(r['omega_hybrid_deg']):4.1f}/{float(r['omega_ee_deg']):4.1f})")
        lines.append(f"{n:26s} {first['dlon']:>8s} " + " ".join(f"{c:>17s}" for c in cells))
    return "\n".join(lines)
