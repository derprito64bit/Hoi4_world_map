"""Read the monthly weather of a strategic-region file (used to pick cold regions for EXP-08/09 filler)."""
from __future__ import annotations

import re

KEYS = ("no_phenomenon", "rain_light", "rain_heavy", "snow", "blizzard", "arctic_water", "mud", "sandstorm",
        "min_snow_level")


def parse_periods(text: str) -> list:
    """[{start_month, tmin, tmax, snow, arctic_water, ...}] in file order; [] if there is no weather block."""
    body = re.sub(r"#[^\n]*", "", text)
    out = []
    for m in re.finditer(r"period\s*=\s*\{(.*?)\}\s*(?=period\s*=|\}\s*$|\}\s*\})", body, re.S):
        p = m.group(1)
        b = re.search(r"between\s*=\s*\{\s*([\d.]+)\s+([\d.]+)", p)
        t = re.search(r"temperature\s*=\s*\{\s*(-?[\d.]+)\s+(-?[\d.]+)", p)
        if not b or not t:
            continue
        start = b.group(1).split(".")                     # "day.month", both 0-based
        d = {"start_month": int(start[1]) if len(start) > 1 else 0,
             "tmin": float(t.group(1)), "tmax": float(t.group(2))}
        for k in KEYS:
            k_m = re.search(r"\b%s\s*=\s*(-?[\d.]+)" % k, p)
            d[k] = float(k_m.group(1)) if k_m else 0.0
        out.append(d)
    return out


def winter_icy(text: str, months=(0, 1, 2)) -> bool:
    """True if every given month (0 = January) is below freezing at night and has snow or arctic water."""
    per = {p["start_month"]: p for p in parse_periods(text)}
    return all(m in per and per[m]["tmin"] < 0 and (per[m]["snow"] > 0 or per[m]["arctic_water"] > 0)
               for m in months)
