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


def winter_icy(text: str, months=(0, 1, 2), both: bool = False) -> bool:
    """True if every given month (0 = January) is below freezing at night and has snow or arctic water
    (``both=True``: snow AND arctic water)."""
    per = {p["start_month"]: p for p in parse_periods(text)}

    def ok(p):
        s, a = p["snow"] > 0, p["arctic_water"] > 0
        return p["tmin"] < 0 and ((s and a) if both else (s or a))
    return all(m in per and ok(per[m]) for m in months)


def with_snow_of(weather: str, donor: str) -> str:
    """``weather`` (a weather block) with each period's ``snow`` weight taken from the donor region's
    period of the same month; every other value stays as it is."""
    snow = {p["start_month"]: p["snow"] for p in parse_periods(donor)}
    out, pos = [], 0
    for m in re.finditer(r"period\s*=\s*\{", weather):
        start = m.end()
        end = _period_end(weather, start)
        body = weather[start:end]
        b = re.search(r"between\s*=\s*\{\s*[\d.]+\.(\d+)", body)
        month = int(b.group(1)) if b else 0
        if month not in snow:
            raise ValueError(f"donor region has no period for month {month}")
        new_body, n = re.subn(r"\bsnow\s*=\s*-?[\d.]+", f"snow={snow[month]:.3f}", body)
        if n != 1:
            raise ValueError("period without exactly one snow weight")
        out.append(weather[pos:start] + new_body)
        pos = end
    out.append(weather[pos:])
    return "".join(out)


def _period_end(text: str, start: int) -> int:
    """Index of the '}' closing the period block whose body starts at ``start``."""
    depth = 1
    i = start
    while depth:
        c = text[i]
        depth += 1 if c == "{" else -1 if c == "}" else 0
        i += 1
    return i - 1
