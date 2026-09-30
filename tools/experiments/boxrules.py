"""Candidate rules for HOI4 1.19.3's ``map.cpp:1830 Province N has TOO LARGE BOX`` (P00b-f6).

What was observed with ``-debug`` (owner runs, ``to-check/2026-09-28_exp-results.md``):

* flagged: EXP-02-1200 (land 2972, sea 8337: 1-px strips 1,200 px wide) and EXP-02b-block-400
  (land 1852, sea 2755: filled 400 x 400 squares that also held donor remnants as enclaves);
* not flagged: EXP-02-600 (land 1664, sea 5367: strips 600 px wide) and every vanilla province
  (widest 7855, 280 x 115);
* not run with -debug (no evidence either way): EXP-02-300, EXP-02b-strip-full. strip-full is the
  tie-breaker of the EXP-02c run (``TIEBREAK``): its land host 3172 (2188 x 14, w*h 30,632) gets no
  line only under an area-type rule, so it is to be run with -debug before the four probes.

``OBSERVED`` pins the measured pixel boxes of those hosts and of the vanilla provinces that hold the
maximum of any metric below (``diag02.py`` re-measures them from the maps; a test compares).
A rule family is a metric m (of the box, or of the pixels) with the rule "flagged iff m > T"; it is
*consistent* with the observations iff max(m over clean) < min(m over flagged), and then T lies in
[max clean, min flagged). The two-axis family "w > Tw or h > Th" is evaluated separately
(``two_axis``). Engine boxes are the 2-px grid boxes of ``regioncentre.engine_boxes`` (fitted to the
EXP-03-24k dump); the pixel box is the plain span (w = xmax - xmin + 1).

ASSUMPTIONS (the probe design depends on them; a result that fits no row may mean one is wrong):

* one threshold for land and sea: the main families C1-C4 use every observation regardless of kind.
  Without it the area rule splits into a land limit in [32,200, 90,000) and a sea limit in
  [33,600, 61,200) (``C1k``);
* one rule, not a combination (e.g. "w > Tw or w*h > A" is not a candidate of its own);
* the line depends on the box only (not on the fill: the 1-px strips of EXP-02-1200 were flagged).

The probes of EXP-02c (``exp02c.PROBES``) plus ``TIEBREAK`` are chosen so that the main families
C1-C4 have disjoint sets of possible outcomes (``outcomes``, exact over every threshold the
observations allow). What stays ambiguous is named, not hidden (``ambiguous``): the row "only
sea-L-330x480 flagged" of C2 (w+h) is also produced by a 32-px or 64-px tile-count rule (a
quantised area rule), and the kind-specific area rule ``C1k`` overlaps C1 (the same reading). A
strip-full line rules out the land-only area limit behind that row; no line there rules out C2.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

H_VANILLA = 2048
W_VANILLA = 5632
INF = float("inf")


@dataclass(frozen=True)
class Box:
    """One province's pixel box (x0..x1, y0..y1 inclusive, row 0 = north) and pixel count."""
    label: str
    pid: int
    kind: str
    x0: int
    x1: int
    y0: int
    y1: int
    pixels: int
    flagged: bool | None = None       # True / False as observed with -debug; None = not observed
    confounded: bool = False          # flagged, but the build had another candidate cause (enclaves)

    @property
    def w(self) -> int:
        return self.x1 - self.x0 + 1

    @property
    def h(self) -> int:
        return self.y1 - self.y0 + 1

    def engine(self, H: int = H_VANILLA) -> tuple:
        """(bx0, by0, bw, bh) on the 2-px grid, y from the bottom (``regioncentre.engine_boxes``)."""
        yb0, yb1 = H - 1 - self.y1, H - 1 - self.y0
        bx0, by0 = 2 * (self.x0 // 2), 2 * (yb0 // 2)
        return bx0, by0, 2 * (self.x1 // 2 + 1) - bx0, 2 * (yb1 // 2 + 1) - by0

    def tiles(self, t: int) -> int:
        """Number of t x t map tiles (aligned at 0, 0) the box touches."""
        return (self.x1 // t - self.x0 // t + 1) * (self.y1 // t - self.y0 // t + 1)


def _ew(b):
    return b.engine()[2]


def _eh(b):
    return b.engine()[3]


METRICS = {
    "w": lambda b: b.w,
    "h": lambda b: b.h,
    "max(w,h)": lambda b: max(b.w, b.h),
    "w*h": lambda b: b.w * b.h,
    "w+h": lambda b: b.w + b.h,
    "diagonal": lambda b: round(math.hypot(b.w, b.h), 1),
    "pixels": lambda b: b.pixels,
    "w*h/pixels": lambda b: round(b.w * b.h / b.pixels, 2),
    "engine w": _ew,
    "engine max side": lambda b: max(_ew(b), _eh(b)),
    "engine w*h": lambda b: _ew(b) * _eh(b),
    "engine w+h": lambda b: _ew(b) + _eh(b),
    "32-px tiles": lambda b: b.tiles(32),
    "64-px tiles": lambda b: b.tiles(64),
    "128-px tiles": lambda b: b.tiles(128),
    "256-px tiles": lambda b: b.tiles(256),
}

# measured on vanilla 1.19.3 and the builds (diag02.py prints and re-checks these)
OBSERVED = (
    # vanilla: the provinces holding the maximum of some metric (all loaded with -debug, no BOX line)
    Box("vanilla", 7855, "land", 120, 399, 0, 114, 11914, False),        # widest; largest w*h, w+h
    Box("vanilla", 4455, "land", 5154, 5291, 25, 197, 11463, False),     # tallest (173)
    Box("vanilla", 4006, "land", 4907, 5122, 0, 126, 15697, False),      # most pixels
    Box("vanilla", 1823, "land", 5308, 5492, 190, 328, 9049, False),     # most 32 / 64-px tiles
    Box("vanilla", 3208, "land", 1649, 1821, 77, 208, 7732, False),      # most 128-px tiles
    Box("vanilla", 25, "sea", 5321, 5379, 733, 812, 2923, False),        # 4 256-px tiles (lowest id of several)
    Box("vanilla", 8370, "sea", 3578, 3756, 0, 113, 11983, False),       # widest sea (179)
    Box("vanilla", 10321, "land", 4248, 4271, 1227, 1292, 50, False),    # sparsest: w*h/pixels 31.7
    # EXP-02-600 (-debug 2026-09-30 07:24): no TOO LARGE BOX
    Box("EXP-02-600", 1664, "land", 3824, 4423, 172, 218, 2424, False),
    Box("EXP-02-600", 5367, "sea", 4674, 5273, 1011, 1066, 2274, False),
    # EXP-02-1200 (-debug 2026-09-29 23:06): TOO LARGE BOX for both
    Box("EXP-02-1200", 2972, "land", 4094, 5293, 0, 74, 10209, True),
    Box("EXP-02-1200", 8337, "sea", 87, 1286, 1442, 1492, 4060, True),
    # EXP-02b-block-400 (-debug 2026-09-29 23:02): TOO LARGE BOX for both; the squares held enclaves
    Box("EXP-02b-block-400", 1852, "land", 4513, 4912, 33, 432, 159464, True, True),
    Box("EXP-02b-block-400", 2755, "sea", 289, 688, 257, 656, 159712, True, True),
    # not run with -debug: no evidence (listed for the table only)
    Box("EXP-02-300", 1664, "land", 3824, 4123, 172, 218, 2124, None),
    Box("EXP-02-300", 5426, "sea", 21, 320, 988, 1037, 3394, None),
    Box("EXP-02b-strip-full", 3172, "land", 3156, 5343, 219, 232, 2292, None),
    Box("EXP-02b-strip-full", 6848, "sea", 0, 5624, 2001, 2047, 8634, None),
)


def split(boxes, drop_confounded: bool = False) -> tuple:
    """(clean, flagged) observed boxes; ``drop_confounded`` leaves the confounded flagged ones out."""
    clean = [b for b in boxes if b.flagged is False]
    flagged = [b for b in boxes if b.flagged is True and not (drop_confounded and b.confounded)]
    return clean, flagged


@dataclass(frozen=True)
class Family:
    name: str
    consistent: bool
    lo: float          # T >= lo (max over clean)
    hi: float          # T < hi (min over flagged)
    note: str = ""


def single(name: str, boxes, drop_confounded: bool = False) -> Family:
    """"flagged iff m > T" for metric ``name``: consistent iff max clean < min flagged."""
    m = METRICS[name]
    clean, flagged = split(boxes, drop_confounded)
    lo = max(m(b) for b in clean)
    hi = min(m(b) for b in flagged) if flagged else INF
    return Family(name, lo < hi, lo, hi)


@dataclass(frozen=True)
class TwoAxis:
    consistent: bool
    tw: tuple          # Tw in [lo, hi)
    th: tuple          # Th in [lo, hi)
    engine: bool = False


def two_axis(boxes, drop_confounded: bool = False, engine: bool = False) -> TwoAxis:
    """"flagged iff w > Tw or h > Th": Tw >= every clean w, Th >= every clean h, and each flagged box
    must exceed one of them; a flagged box that only its width can explain bounds Tw from above."""
    def wh(b):
        return (b.engine()[2], b.engine()[3]) if engine else (b.w, b.h)
    clean, flagged = split(boxes, drop_confounded)
    cw = max(wh(b)[0] for b in clean)
    ch = max(wh(b)[1] for b in clean)
    ok = all(wh(b)[0] > cw or wh(b)[1] > ch for b in flagged)
    tw_hi = min([wh(b)[0] for b in flagged if wh(b)[1] <= ch], default=INF)
    th_hi = min([wh(b)[1] for b in flagged if wh(b)[0] <= cw], default=INF)
    return TwoAxis(ok, (cw, tw_hi), (ch, th_hi), engine)


def predict_single(f: Family, value: float) -> str:
    """'F' (TOO LARGE BOX for every T in the interval), 'c' (clean for every T), '?' (depends on T)."""
    if value >= f.hi:
        return "F"
    if value <= f.lo:
        return "c"
    return "?"


def predict_two_axis(t: TwoAxis, w: int, h: int) -> str:
    if w >= t.tw[1] or h >= t.th[1]:
        return "F"
    if w <= t.tw[0] and h <= t.th[0]:
        return "c"
    return "?"


def probe_box(w: int, h: int, r0: int, c0: int, pixels: int | None = None, label: str = "probe") -> Box:
    return Box(label, 0, "", c0, c0 + w - 1, r0, r0 + h - 1, w * h if pixels is None else pixels)


# The candidate rules that survive the observations, as used for the EXP-02c probe design. Each is
# (id, description, predictor(box) -> 'F' / 'c' / '?'). ``candidates()`` builds them from OBSERVED.
def candidates(boxes=OBSERVED) -> list:
    """[(id, text, fn(Box) -> 'F'|'c'|'?')] for every rule family consistent with the observations."""
    out = []
    area = single("w*h", boxes)
    earea = single("engine w*h", boxes)
    if area.consistent and earea.consistent:
        out.append(("C1", f"box area w*h > A, A in [{area.lo:.0f}, {area.hi:.0f}) px "
                          f"(engine box: [{earea.lo:.0f}, {earea.hi:.0f}))",
                    lambda b, a=area, e=earea: _both(predict_single(a, METRICS["w*h"](b)),
                                                     predict_single(e, METRICS["engine w*h"](b)))))
    s = single("w+h", boxes)
    es = single("engine w+h", boxes)
    if s.consistent and es.consistent:
        out.append(("C2", f"half perimeter w+h > S, S in [{s.lo:.0f}, {s.hi:.0f}) px "
                          f"(engine box: [{es.lo:.0f}, {es.hi:.0f}))",
                    lambda b, a=s, e=es: _both(predict_single(a, METRICS["w+h"](b)),
                                               predict_single(e, METRICS["engine w+h"](b)))))
    t = two_axis(boxes)
    te = two_axis(boxes, engine=True)
    if t.consistent and te.consistent:
        out.append(("C3", f"either side: w > Tw or h > Th, Tw in [{t.tw[0]}, {t.tw[1]}), Th in [{t.th[0]}, "
                          f"{t.th[1]}) px (e.g. W/8 = {W_VANILLA // 8} and H/8 = {H_VANILLA // 8})",
                    lambda b, a=t, e=te: _both(predict_two_axis(a, b.w, b.h),
                                               predict_two_axis(e, b.engine()[2], b.engine()[3]))))
    wd = single("w", boxes, drop_confounded=True)
    md = single("max(w,h)", boxes, drop_confounded=True)
    if wd.consistent and md.consistent and not single("max(w,h)", boxes).consistent:
        out.append(("C4", f"width / longest side only, max(w,h) > T, T in [{md.lo:.0f}, {md.hi:.0f}) px, "
                          "if block-400's line came from its enclaves and not from its size (e.g. the "
                          f"validator's W/8 = {W_VANILLA // 8} or a 1024 cap); the same row also fits 'width, "
                          "or height >= 480, or area >= 158,400' (larger clean boxes are untested)",
                    lambda b, a=md: predict_single(a, METRICS["max(w,h)"](b))))
    return out


def narrows(cid: str, b: Box, boxes=OBSERVED) -> str:
    """What a TOO LARGE BOX line on box ``b`` would say about family ``cid``'s threshold (for '?' outcomes)."""
    if cid == "C1":
        a, e = single("w*h", boxes), single("engine w*h", boxes)
        px, eng = b.w * b.h, _ew(b) * _eh(b)
        parts = [f"A < {px}"] if a.lo < px < a.hi else []
        if e.lo < eng < e.hi and eng != px:
            parts.append(f"the engine box counts and A < {eng}")
        return " or ".join(parts)
    if cid == "C2":
        return f"S < {b.w + b.h}"
    if cid == "C3":
        t = two_axis(boxes)
        parts = []
        if t.tw[0] < b.w < t.tw[1]:
            parts.append(f"Tw < {b.w}")
        if t.th[0] < b.h < t.th[1]:
            parts.append(f"Th < {b.h}")
        return " or ".join(parts)
    if cid == "C4":
        return f"T < {max(b.w, b.h)}"
    raise KeyError(cid)


def grid_families(boxes=OBSERVED) -> list:
    """Consistent tile-count families ("the box touches more than K t x t tiles"): quantised forms of the
    area rule. They depend on where a box sits on the tile grid, so the EXP-02c probes do not separate them
    from C1 / C2; listed for the record only."""
    return [single(f"{t}-px tiles", boxes) for t in (32, 64, 128, 256) if single(f"{t}-px tiles", boxes).consistent]


def _both(a: str, b: str) -> str:
    """Combine the pixel-box and engine-box predictions: a firm answer only when both agree."""
    return a if a == b else "?"


def rejected(boxes=OBSERVED) -> list:
    """[(metric, clean max, flagged min)] for single-metric families the observations rule out."""
    out = []
    for name in METRICS:
        f = single(name, boxes)
        if not f.consistent:
            out.append((name, f.lo, f.hi))
    return out


# ------------------------------------------------------------------ exact outcome sets (P00b-f6 r2)
TIEBREAK = next(b for b in OBSERVED if b.label == "EXP-02b-strip-full" and b.kind == "land")

FAMILIES = {
    "C1": "box area w*h > A (one threshold for land and sea)",
    "C2": "half perimeter w+h > S",
    "C3": "either side: w > Tw or h > Th",
    "C4": "longest side only, max(w,h) > T (block-400 confounded by its enclaves)",
    "C1k": "box area with its own threshold for land and for sea",
    "G32": "more than K 32-px tiles touched (a quantised area rule)",
    "G64": "more than K 64-px tiles touched (a quantised area rule)",
}
MAIN = ("C1", "C2", "C3", "C4")


def _cuts(values, lo, hi) -> list:
    """Thresholds that give every distinct outcome of "v > T" for T in [lo, hi)."""
    return sorted({lo} | {v for v in values if lo <= v < hi})


def _single_outcomes(metric, intervals: dict, boxes) -> set:
    """Outcomes of "metric > T[kind]" over all allowed thresholds; ``intervals`` = {kind or None: (lo, hi)}."""
    keys = sorted(intervals, key=str)
    choices = [_cuts([metric(b) for b in boxes if k is None or b.kind == k], *intervals[k]) for k in keys]
    out = set()
    for ts in itertools.product(*choices):
        t = dict(zip(keys, ts))
        out.add(tuple(bool(metric(b) > t[None if None in t else b.kind]) for b in boxes))
    return out


def _interval(name: str, obs, kind=None, drop_confounded=False) -> tuple:
    f = single(name, [b for b in obs if kind is None or b.kind == kind], drop_confounded)
    if not f.consistent:
        raise ValueError(f"{name} ({kind or 'any kind'}) is not consistent with the observations")
    return f.lo, f.hi


def outcomes(fid: str, boxes, obs=OBSERVED) -> set:
    """Every outcome (tuple of flagged? per box) family ``fid`` allows for ``boxes``, over every threshold
    consistent with ``obs``, pixel box and engine box variants together."""
    out = set()
    if fid in ("C1", "C2", "G32", "G64"):
        names = {"C1": ("w*h", "engine w*h"), "C2": ("w+h", "engine w+h"), "G32": ("32-px tiles",),
                 "G64": ("64-px tiles",)}[fid]
        for n in names:
            out |= _single_outcomes(METRICS[n], {None: _interval(n, obs)}, boxes)
    elif fid == "C1k":
        for n in ("w*h", "engine w*h"):
            out |= _single_outcomes(METRICS[n], {k: _interval(n, obs, k) for k in ("land", "sea")}, boxes)
    elif fid == "C4":
        for n in ("max(w,h)", "engine max side"):
            out |= _single_outcomes(METRICS[n], {None: _interval(n, obs, drop_confounded=True)}, boxes)
    elif fid == "C3":
        for eng in (False, True):
            t = two_axis(obs, engine=eng)
            wh = [(b.engine()[2], b.engine()[3]) if eng else (b.w, b.h) for b in boxes]
            for tw in _cuts([w for w, _ in wh], *t.tw):
                for th in _cuts([h for _, h in wh], *t.th):
                    out.add(tuple(bool(w > tw or h > th) for w, h in wh))
    else:
        raise KeyError(fid)
    return out


def ambiguous(boxes, fids=None, obs=OBSERVED) -> list:
    """Pairs of families (sorted) that share at least one possible outcome on ``boxes``."""
    fids = list(FAMILIES) if fids is None else list(fids)
    sets = {f: outcomes(f, boxes, obs) for f in fids}
    return [(a, b) for i, a in enumerate(fids) for b in fids[i + 1:] if sets[a] & sets[b]]


def explain(outcome: tuple, boxes, obs=OBSERVED) -> list:
    """Families (in FAMILIES order) that allow an observed outcome (tuple of flagged? per box)."""
    return [f for f in FAMILIES if tuple(outcome) in outcomes(f, boxes, obs)]
