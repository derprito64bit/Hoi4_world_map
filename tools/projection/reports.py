"""Text/CSV reports for P00d: band summary, top edge (Q-014), seam sensitivity."""
from __future__ import annotations

import csv
import io

import numpy as np

from projection import hybrid

ee = hybrid.ee

# northernmost land (approximate, degrees N); rows depend on latitude only
NORTH_FEATURES = (
    ("Kaffeklubben Island (Greenland)", 83.66),
    ("Cape Morris Jesup (Greenland)", 83.65),
    ("Cape Columbia (Ellesmere)", 83.11),
    ("Cape Fligely (Franz Josef Land)", 81.86),
    ("Cape Arctic (Severnaya Zemlya)", 81.28),
    ("Rossoya (Svalbard)", 80.83),
)
# southern land lost when lat_min moves north (approximate, degrees S)
SOUTH_FEATURES = (
    ("Southern Thule (S. Sandwich Is.)", -59.45),
    ("Montagu Island (S. Sandwich Is.)", -58.42),
    ("Saunders Island (S. Sandwich Is.)", -57.80),
    ("Candlemas Island (S. Sandwich Is.)", -57.08),
    ("Diego Ramirez Islands", -56.49),
    ("Zavodovski Island (S. Sandwich Is.)", -56.30),
    ("Cape Horn", -55.98),
    ("South Georgia (south tip)", -54.90),
    ("Macquarie Island", -54.76),
)
HIDDEN_SHARE = (0.01, 0.02, 0.03)  # EXP-09b/c: ~1-3 % of the screen height under the frame + top bar


def band_summary(lambdas, ramp):
    lats = np.array([0.0, 30.0, 45.0, 60.0, 66.0, 75.0, 90.0])
    w = hybrid.half_width(lats)
    lines = ["peak E-W stretch at the seam (= area factor there), by latitude:",
             "  lambda_b ramp  " + " ".join(f"{la:>6.0f}N" for la in lats)]
    for lb in lambdas:
        for r in sorted({ramp, 1.0, 0.5, 0.25}, reverse=True):
            k = 1.0 / (1.0 - 0.5 * r)
            peak = 1 + (hybrid.X_MAX / w - 1) * k * np.pi / (np.pi - np.radians(lb))
            mark = " <" if r == ramp else ""
            lines.append(f"  {lb:8g} {r:4g}  " + " ".join(f"{p:7.2f}" for p in peak) + mark)
    return "\n".join(lines)


def _row(canvas_scale, y_top, top_margin, lat):
    y = ee.forward(0.0, lat)[1]
    return top_margin + (y_top - y) * canvas_scale


def top_edge_options(width=hybrid.WIDTH, height=hybrid.HEIGHT):
    """Layouts with the same width/scale (so the interior stays exactly EE and y(phi) keeps its scale)."""
    scale = width / (2 * hybrid.X_MAX)
    y90 = float(ee.forward(0.0, 90.0)[1])
    kaffe = NORTH_FEATURES[0][1]
    opts = []
    for lat_min in (-60.0, -59.0, -58.0, -57.5, -57.0, -56.6):
        for bottom in (None, 7.0, 2.0, 0.0):
            gh = (y90 - float(ee.forward(0.0, lat_min)[1])) * scale
            if bottom is None:
                if lat_min != -60.0:
                    continue
                bottom = (height - gh) / 2
            top = height - gh - bottom
            if top < 0:
                continue
            k_row = _row(scale, y90, top, kaffe)
            lost = [n for n, la in SOUTH_FEATURES if la < lat_min]
            opts.append({"lat_min": lat_min, "bottom_margin": bottom, "top_margin": top,
                         "kaffeklubben_row": k_row, "kaffeklubben_pct": 100 * k_row / height,
                         "lost_south": "; ".join(lost) or "-"})
    return opts


def y_squeeze_needed(target_row, width=hybrid.WIDTH, height=hybrid.HEIGHT, bottom=14.33):
    """Vertical-only scale factor that would put Kaffeklubben at target_row with lat -60..90 (NOT EE any more)."""
    scale = width / (2 * hybrid.X_MAX)
    yk = float(ee.forward(0.0, NORTH_FEATURES[0][1])[1])
    ys = float(ee.forward(0.0, -60.0)[1])
    return (height - bottom - target_row) / ((yk - ys) * scale)


def top_edge_report(width=hybrid.WIDTH, height=hybrid.HEIGHT):
    c = hybrid.HybridCanvas(width, height)
    lines = [f"top edge (Q-014): current layout lat {c.lat_min:g}..{c.lat_max:g}, top margin {c.margin:.2f} rows "
             f"= {100 * c.margin / c.H:.2f} % of {c.H} rows (bottom margin the same)"]
    lines.append("  hidden rows if the frame + top bar cover " +
                 ", ".join(f"{100 * s:.0f} % -> {s * c.H:.0f}" for s in HIDDEN_SHARE) +
                 " rows (fully zoomed out, the map height fills the screen)")
    for n, la in NORTH_FEATURES:
        r = float(c.row_of_lat(la))
        lines.append(f"  {n:34s} {la:6.2f}N  row {r:6.1f} ({100 * r / c.H:4.2f} %)  {r - c.margin:5.1f} rows below 90N")
    lines.append("  layouts with the same scale (interior stays exact EE; rows shift by a constant):")
    lines.append(f"  {'lat_min':>7s} {'bottom':>6s} {'top':>6s} {'Kaffe row':>9s} {'%H':>5s}  lost in the south")
    for o in top_edge_options(width, height):
        lines.append(f"  {o['lat_min']:7.1f} {o['bottom_margin']:6.2f} {o['top_margin']:6.2f} "
                     f"{o['kaffeklubben_row']:9.1f} {o['kaffeklubben_pct']:5.2f}  {o['lost_south']}")
    f = y_squeeze_needed(0.03 * height, width, height)
    lines.append(f"  rejected: a vertical-only squeeze to put Kaffeklubben at 3 % needs y x {f:.4f} "
                 f"(breaks EE's equal area everywhere and the 'rows identical' rule)")
    return "\n".join(lines)


def top_edge_csv(width=hybrid.WIDTH, height=hybrid.HEIGHT) -> str:
    buf = io.StringIO()
    cols = ("lat_min", "bottom_margin", "top_margin", "kaffeklubben_row", "kaffeklubben_pct", "lost_south")
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for o in top_edge_options(width, height):
        w.writerow({k: (f"{v:.2f}" if isinstance(v, float) else v) for k, v in o.items()})
    return buf.getvalue()
