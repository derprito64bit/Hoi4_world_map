"""Conservative offline model of HOI4 1.19.3's strategic-region centre calculation (the EXP-03-24k crash).

Source: both EXP-03-24k crash dumps (hoi4.exe 1.19.3.0.c01a) stop at ``idiv ecx`` with
ecx = 0, RVA 0x15A4CDC, inside the routine RVA 0x15A4C20..0x15A4E8B. Its caller is
RVA 0x15A4770, which asserts ``IsRegionCenterSet()`` from ``strategicregiontemplate.cpp``.
The region object in the dump is "Northern Norway" (region 191 of the build, 54 provinces).

Evidence levels:

OBSERVED (dump registers / region object)
  * mean point M = (3141, 1961), region rect = (x0 2990, y0 1854, w 302, h 170), divisor 0.
  * y is counted from the bottom (BMP order); rect y0 = 1854 only fits bottom-up rows.
READ FROM THE DISASSEMBLY (not executed, not observed in memory)
  * M is the truncating integer mean of the members' box centres ``x0 + w/2, y0 + h/2``.
  * Before the fallback, each member box is tested with ``x0 <= M.x <= x0 + w`` (the same for y);
    the first hit becomes the centre and nothing is divided.
  * The fallback computes ``(...) / (M.x - (rx0 + rw/2))``. The routine contains exactly
    this one ``idiv``; a division by the y difference was not seen in it. The routine
    it calls next (RVA 0x15A4E90) was not read.
  * A region with 0 provinces returns early (no division).
  * The routine first tests M against the region rectangle; if M is outside it, it reads a
    second rectangle stored 16 bytes further on. What that second rectangle holds (probably
    the wrapped part of a region crossing the seam) was not observed.
INFERRED (only a fit to the dump numbers)
  * The stored box width. Two conventions reproduce the dump exactly:
    (A) w = span + 1 (span = xmax - xmin), rect = union + 1;
    (B) w = span + 2, centre x0 + (w - 1)/2, rect = plain union.
    Both give the same centre and rect (region 191 in 24k: xmax - xmin = 300, i.e.
    301 columns, rect width 302), but the upper bound of the inside test is xmax + 1
    in (A) and xmax + 2 in (B).
  * The compare direction. The disassembly reads ``jl`` / ``jg`` (inclusive at both ends),
    but that reading is the only source: nothing observed decides whether the bounds are
    ``<=`` or ``<``. So each end may be exclusive: the lower bound xmin + 1, the upper xmax.

What the model does, conservatively:
  * ``fallback_strict`` (used for the dx test): M counts as inside only when
    xmin < M.x <= xmax and ymin < M.y <= ymax, i.e. inside under EVERY convention (the
    intersection). Means on a member's left or bottom edge count as outside. This matters
    for strip or grid layouts, where the mean sits exactly on the shared edge of two boxes
    (EXP-09a: ~140 regions).
  * ``fallback`` (used for the dy test): the inclusive lower bound, xmin <= M <= xmax.
    The dy test cannot use the strict lower bound: vanilla region 1 has dx 10, dy 0 and its
    mean lies on a box's lower edge, so "strict lower bound" and "the engine divides by dy"
    cannot both be true, and vanilla loads. dy == 0 is only flagged because the next
    routine was not read; dx == 0 is the observed crash, so it gets the stricter test.
  * ``fallback_all``: outside every member box even with the widest convention.
  * ``unsafe``: not wrapping and ((fallback_strict and dx == 0) or (fallback and dy == 0)).
  * ``unknown``: fallback_strict in a region whose members cover column 0 AND column W-1
    (it wraps). The model does not cover these.
  * Guards (``guard_failures``) reject unsafe regions and unknown regions without an
    identical twin in a map observed loading. For new geometry pass ``observed = {}``:
    then every wrapping region that takes the fallback fails. ``unsafe_regions`` alone
    never returns an unknown region and is not a guard.

Supporting observations (vanilla 1.19.3 loads):
  * 13 vanilla regions have dx == 0 with M inside a member box, so the gate before the
    fallback is real (a guard on "dx != 0 always" would be wrong).
  * Using pixel membership (M's pixel belongs to a member) instead of boxes as the gate
    would make vanilla region 207 crash, so boxes it is.
  * Vanilla has 6 unknown regions (88, 95, 96, 97, 178, 180; 178 even has dy == 0). EXP-02-300
    (region 95) and EXP-02-1200 (region 97) changed a wrapping fallback region and still loaded:
    unknown-but-observed-loading, i.e. weak evidence that wrapping regions are handled.
  * Only EXP-03-24k is flagged among the builds run in game. Region 191's dx is
    -10 / -10 / -11 / 0 / +2 in vanilla / 16k / 20k / 24k / 30k.

Rules for the real map (P05 and the region builder):
  * ``guard_failures(region_centres(pid, regions), observed)`` must be empty (``observed``
    = {} for new geometry); re-check after every change to provinces or membership;
  * keep region means off member box edges (margin >= 1 px), so the compare direction
    never decides;
  * prefer regions whose mean point falls inside a member box (the fallback never runs);
    ring-, C- and strip-shaped regions are the ones that take the fallback;
  * symmetric or regular layouts (grid or strip filler, mirrored regions) put the mean
    exactly on the rectangle centre; EXP-09a-e region 113 is such a case.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from .common import KitError
from .mapdata import bboxes

INSIDE_SLACK = (0, 1, 2)   # inside-test upper bound = xmax + slack for the conventions above


@dataclass(frozen=True)
class RegionCentre:
    region: int
    n: int
    mean: tuple            # (x, y) engine coordinates, y from the bottom
    rect: tuple            # (x0, y0, w, h) of the region rectangle
    fallback: bool         # mean outside every member's box xmin <= M <= xmax (dy test)
    fallback_all: bool     # mean outside every member box even with the widest convention
    dx: int                # mean.x - rect centre x (the observed divisor)
    dy: int                # mean.y - rect centre y (flagged conservatively)
    gap: int               # Chebyshev distance of the mean to the nearest member pixel bbox (0 = inside)
    seam: bool             # members cover column 0 and column W-1 (the region wraps)
    signature: str         # hash of the sorted member boxes: identical member boxes on the same canvas width
    fallback_strict: bool = False   # mean outside every box xmin < M <= xmax (dx test; intersection)
    margin: int = 0                 # max over members of the mean's distance to the nearest edge of that box
                                    # (>= 1: inside a member box under every convention, no fallback)

    @property
    def divisor(self):
        return self.dx if self.fallback_strict else None

    @property
    def unsafe(self) -> bool:
        return not self.seam and ((self.fallback_strict and self.dx == 0) or (self.fallback and self.dy == 0))

    @property
    def unknown(self) -> bool:
        return self.fallback_strict and self.seam

    @property
    def clear(self) -> bool:
        """The mean lies >= 1 px inside a member box: the fallback never runs, whatever the box convention."""
        return self.margin >= 1


def pixel_boxes(pid: np.ndarray, n: int):
    """Per ID: xmin, xmax, and ymin, ymax counted from the bottom; xmax = -1 for IDs without pixels."""
    H, W = pid.shape
    xmin, xmax, ymin, ymax = bboxes(pid, n)
    present = xmax >= 0
    yb0 = np.where(present, H - 1 - ymax, 0)
    yb1 = np.where(present, H - 1 - ymin, -1)
    return (xmin.astype(np.int64), xmax.astype(np.int64), yb0.astype(np.int64), yb1.astype(np.int64))


def province_boxes(pid: np.ndarray, n: int):
    """Engine boxes per ID under convention (A): x0, y0 (from the bottom), w = span + 1, h = span + 1."""
    x0, x1, y0, y1 = pixel_boxes(pid, n)
    present = x1 >= 0
    return (np.where(present, x0, 0), np.where(present, y0, 0), np.where(present, x1 - x0 + 1, 0),
            np.where(present, y1 - y0 + 1, 0))


def _trunc_div(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def mean_point(x0, x1, y0, y1) -> tuple:
    """(M.x, M.y): the truncating integer mean of the member box centres ``x0 + w/2`` (w = span + 1).

    Arguments are arrays of pixel boxes (y from the bottom), one entry per member.
    """
    n = len(x0)
    cx = x0 + (x1 - x0 + 1) // 2
    cy = y0 + (y1 - y0 + 1) // 2
    return _trunc_div(int(cx.sum()), n), _trunc_div(int(cy.sum()), n)


def inner_margin(mx: int, my: int, x0, x1, y0, y1) -> int:
    """max over members of min(M.x - xmin, xmax - M.x, M.y - ymin, ymax - M.y) (pixel boxes).

    >= 1: M lies strictly inside a member box and off all its edges, so the engine finds a
    member box before the fallback under every box convention of the model (no division).
    <= 0: M sits on a box edge or outside every box.
    """
    m = np.minimum(np.minimum(mx - x0, x1 - mx), np.minimum(my - y0, y1 - my))
    return int(m.max()) if len(m) else 0


def region_centre(rid: int, members, boxes, W: int) -> RegionCentre:
    """``boxes`` = pixel_boxes() arrays (xmin, xmax, ymin, ymax; y from the bottom)."""
    bx0, bx1, by0, by1 = boxes
    ids = np.asarray(sorted(int(i) for i in members), dtype=np.int64)
    if len(ids) == 0:
        return RegionCentre(rid, 0, (0, 0), (0, 0, 0, 0), False, False, 0, 0, 0, False, "")
    if (ids >= len(bx1)).any() or (bx1[ids[ids < len(bx1)]] < 0).any():
        missing = [int(i) for i in ids if i >= len(bx1) or bx1[i] < 0]
        raise KitError(f"strategic region {rid}: member provinces without pixels {missing[:10]}")
    x0, x1, y0, y1 = bx0[ids], bx1[ids], by0[ids], by1[ids]
    mx, my = mean_point(x0, x1, y0, y1)
    inside = {s: bool(((x0 <= mx) & (mx <= x1 + s) & (y0 <= my) & (my <= y1 + s)).any()) for s in INSIDE_SLACK}
    inside_strict = bool(((x0 < mx) & (mx <= x1) & (y0 < my) & (my <= y1)).any())
    rx0, ry0 = int(x0.min()), int(y0.min())
    rw = int(x1.max()) - rx0 + 2
    rh = int(y1.max()) - ry0 + 2
    gx = np.maximum(np.maximum(x0 - mx, mx - x1), 0)
    gy = np.maximum(np.maximum(y0 - my, my - y1), 0)
    gap = int(np.maximum(gx, gy).min())
    seam = bool((x0 == 0).any() and (x1 == W - 1).any())
    sig = hashlib.sha256(np.stack([x0, x1, y0, y1], 1).astype("<i8").tobytes()).hexdigest()[:16]
    return RegionCentre(rid, len(ids), (mx, my), (rx0, ry0, rw, rh), not inside[min(INSIDE_SLACK)],
                        not inside[max(INSIDE_SLACK)], mx - (rx0 + rw // 2), my - (ry0 + rh // 2), gap, seam, sig,
                        not inside_strict, inner_margin(mx, my, x0, x1, y0, y1))


def region_centres(pid: np.ndarray, regions: dict) -> dict:
    """{region id: RegionCentre} for ``regions`` = {region id: [province ids]}."""
    n = int(pid.max()) + 1
    for ids in regions.values():
        if len(ids):
            n = max(n, max(ids) + 1)
    boxes = pixel_boxes(pid, n)
    W = pid.shape[1]
    return {rid: region_centre(rid, regions[rid], boxes, W) for rid in sorted(regions)}


def unsafe_regions(pid: np.ndarray, regions: dict) -> list:
    """Region IDs whose centre calculation (conservatively) divides by zero in the engine (sorted)."""
    return [r for r, c in region_centres(pid, regions).items() if c.unsafe]


def unknown_regions(pid: np.ndarray, regions: dict) -> list:
    """Wrapping regions that take the fallback: outside the model (sorted)."""
    return [r for r, c in region_centres(pid, regions).items() if c.unknown]


def not_clear(centres: dict) -> list:
    """Regions whose mean is not >= 1 px inside a member box (they take, or may take, the fallback)."""
    return [r for r, c in centres.items() if c.n and not c.clear]


def guard_failures(centres: dict, observed: dict | None = None) -> list:
    """Regions a generator must not produce: unsafe, or unknown without an identical observed-loading twin.

    ``observed`` = {region id: RegionCentre} of a map that loaded in game (e.g. vanilla).
    """
    observed = observed or {}
    out = []
    for r, c in centres.items():
        twin = observed.get(r)
        if c.unsafe or (c.unknown and not (twin is not None and twin.signature == c.signature)):
            out.append(r)
    return out


def describe(c: RegionCentre) -> str:
    return (f"{c.region} ({c.n} provinces, mean {c.mean}, rect {c.rect}, dx {c.dx}, dy {c.dy}, "
            f"margin {c.margin}{', wraps' if c.seam else ''})")


def guard_problems(centres: dict, observed: dict | None = None, clear_ids=None) -> list:
    """--check messages (P00b-f4): guard failures, and regions whose mean is not >= 1 px inside a member box.

    ``observed``: centres of a map seen loading (vanilla) for the wrapping-region twin rule; {} for new
    geometry. ``clear_ids``: the regions that must never take the fallback (None = all of them).
    """
    probs = []
    fails = guard_failures(centres, observed)
    if fails:
        probs.append(f"region-centre guard: {len(fails)} regions fail (fallback with divisor 0, or a wrapping "
                     "fallback without an identical vanilla twin): "
                     + "; ".join(describe(centres[r]) for r in fails[:5]))
    ids = sorted(centres) if clear_ids is None else sorted(r for r in clear_ids if r in centres)
    loose = [r for r in ids if centres[r].n and not centres[r].clear]
    if loose:
        probs.append(f"region-centre guard: {len(loose)} regions take the fallback (mean not >= 1 px inside a "
                     "member box): " + "; ".join(describe(centres[r]) for r in loose[:5]))
    return probs
