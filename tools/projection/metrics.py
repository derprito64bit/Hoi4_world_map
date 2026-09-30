"""Distortion metrics of the hybrid (numeric Jacobian of hybrid.forward_dl; no EE maths copied).

On the unit sphere a map (λ, φ) -> (x, y) has the ground-to-map vectors
E = ∂(x, y)/∂λ / cos φ (east) and N = ∂(x, y)/∂φ (north). With h = |N|, k = |E| and
σ = |E × N| (areal scale), the Tissot semi-axes satisfy a + b = sqrt(h² + k² + 2σ),
a - b = sqrt(h² + k² - 2σ) and the maximum angular distortion is ω = 2 asin((a - b)/(a + b)).
Equal Earth is equal-area on the unit sphere (σ = 1), so σ is also the area factor relative to EE.
"""
from __future__ import annotations

import numpy as np

from projection import hybrid

EPS_DEG = 1e-5


def jacobian(dl, lat, lambda_b, ramp, eps=EPS_DEG):
    """(x_λ, x_φ, y_φ) per radian at unwrapped Δλ ``dl`` and ``lat`` (degrees); central differences."""
    dl, lat = np.broadcast_arrays(np.asarray(dl, dtype=float), np.asarray(lat, dtype=float))
    dp = np.minimum(dl + eps, 180.0)
    dm = np.maximum(dl - eps, -180.0)
    xp = hybrid.forward_dl(dp, lat, lambda_b, ramp)[0]
    xm = hybrid.forward_dl(dm, lat, lambda_b, ramp)[0]
    x_l = (xp - xm) / np.radians(dp - dm)
    lp = np.minimum(lat + eps, 90.0)
    lm = np.maximum(lat - eps, -90.0)
    xa, ya = hybrid.forward_dl(dl, lp, lambda_b, ramp)
    xb, yb = hybrid.forward_dl(dl, lm, lambda_b, ramp)
    step = np.radians(lp - lm)
    return x_l, (xa - xb) / step, (ya - yb) / step


def tissot(dl, lat, lambda_b, ramp):
    """dict of h, k, area (σ), omega_deg at Δλ ``dl`` / ``lat`` in degrees (|lat| < 90)."""
    x_l, x_p, y_p = jacobian(dl, lat, lambda_b, ramp)
    cphi = np.cos(np.radians(lat))
    k = np.abs(x_l) / cphi
    h = np.hypot(x_p, y_p)
    area = np.abs(x_l * y_p) / cphi
    s = h * h + k * k
    apb = np.sqrt(s + 2 * area)
    amb = np.sqrt(np.maximum(s - 2 * area, 0.0))
    omega = np.degrees(2 * np.arcsin(np.clip(amb / apb, 0.0, 1.0)))
    return {"h": h, "k": k, "area": area, "omega_deg": omega}
