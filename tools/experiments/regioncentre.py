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

P00b-f5 refinement (after EXP-03-div0 loaded although this model predicted a crash):
READ FROM THE DISASSEMBLY (hoi4.exe 1.19.3.0.c01a, whole path read, not executed)
  * Caller RVA 0x15A4770: 0 members -> centre = the stored rect centre (region + 0xE0), return.
    Otherwise M = truncating mean of ``x0 + w/2, y0 + h/2`` over the members' boxes (province
    object + 0x88: x0, y0, w, h as int32). For each member it calls RVA 0x15A5C20, which is
    ``x0 <= M.x <= x0 + w and y0 <= M.y <= y0 + h`` (``jl`` / ``jg``: inclusive at both ends, one
    box per province, no pixel test). First hit -> centre = that member's box centre, no division.
  * No hit -> RVA 0x15A4C20. It picks the region rect (region + 0xF0 points to a vector of
    rects; the dump's region 191 holds exactly one) if M lies inside it (inclusive), else the next
    rect 16 bytes on, and then divides ``(h/2 + M.y - ry0) / (M.x - (rx0 + rw/2))`` at once:
    there is no zero check and no condition between the member test and this ``idiv``. The line
    march (steps of +-10 px in x, ending when it leaves the rect or hits a member box) runs
    after the division, so it cannot prevent it.
  * If the centre is still <= 0 in x or y, RVA 0x15A4E90 picks the member box centre nearest to
    M (floating-point distances, a sort); it and its sort helpers contain no integer division.
    So a zero dy divides by nothing on this path; the dy rule below is kept only as caution.
OBSERVED (both 24k dumps, identical): besides M, the rect and the divisor, the caller's frame
  still holds the last member's box (province 19700): (3164, 1952, 16, 16). Its pixels span
  x 3164..3178 (15 columns) and y 1952..1967 (16 rows, from the bottom): w = 16 is NOT span + 1.
INFERRED (fit): the engine boxes lie on a 2-px grid (``engine_boxes``): x0 = 2 * (xmin // 2),
  x0 + w = 2 * (xmax // 2 + 1), the same in y (bottom-up; H is even, so the parity is the same
  counted from the top). With these boxes the dump is reproduced exactly: M (3141, 1961) from all
  54 members, the rect (2990, 1854, 302, 170) as the plain union of the member boxes, and box
  19700. No other simple rule tried fits all three (span + k for k = 0..3 fails M or the rect; a
  4-px grid fails the rect; "round the size up to even" fails M). Why the engine snaps to 2 px
  (e.g. a half-resolution province map) was not found: the code that fills province + 0x88 was
  not located.
  * Out-of-sample check: under the 2-px grid, EXP-03-div0's region 193 has mean (4952, 417),
    rect (4834, 336, 234, 154) and dx = +1, not 0: it predicts that div0 loads, which it did.
    Every other build run in game (EXP-01/02/02b/05/06/07, EXP-03 16k/20k/24k-fix/30k) has no
    region with the fallback and dx_g2 == 0; 24k has exactly region 191. EXP-08/09 have none.
  * What is still unknown: the rule is fitted to one region of one map plus that one load; the
    wrapping (seam) regions and the second rect are still not observed.
What the model does now (conservative): ``crash_g2`` is the 2-px-grid prediction (exact
  inclusive test, dx only). ``unsafe`` = the old conservative rule OR ``crash_g2``, so nothing the
  old model flagged becomes SAFE (EXP-03-div0 region 193 stays flagged although it loaded). Only
  when the owner's EXP-03-191only / EXP-03-div0b runs confirm the grid rule should the old rule be
  retired; that decision is not taken here. ``unknown`` also counts wrapping regions whose mean
  misses every grid box.

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
GRID = 2                   # P00b-f5: engine boxes snap to this grid (fitted to the 24k dump)
DUMP_REGION = 191          # EXP-03-24k, both dumps
DUMP_MEAN = (3141, 1961)
DUMP_RECT = (2990, 1854, 302, 170)
DUMP_BOX = (19700, (3164, 1952, 16, 16))   # last member's engine box, left in the caller's frame


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
    # P00b-f5: the same computation on 2-px-grid engine boxes (``engine_boxes``)
    mean_g2: tuple = (0, 0)
    rect_g2: tuple = (0, 0, 0, 0)
    fallback_g2: bool = False       # mean outside every grid box (inclusive test, as in RVA 0x15A5C20)
    dx_g2: int = 0                  # mean_g2.x - (rect_g2 x0 + w/2): the divisor on the grid model

    @property
    def divisor(self):
        return self.dx if self.fallback_strict else None

    @property
    def unsafe_old(self) -> bool:
        """The P00b-f3 r3 rule (pixel boxes, every compare convention; dx or dy)."""
        return not self.seam and ((self.fallback_strict and self.dx == 0) or (self.fallback and self.dy == 0))

    @property
    def crash_g2(self) -> bool:
        """The 2-px-grid model's prediction of the RVA 0x15A4CDC divide by zero (non-wrapping regions)."""
        return not self.seam and self.fallback_g2 and self.dx_g2 == 0

    @property
    def unsafe(self) -> bool:
        """Conservative: flagged by the old rule OR predicted by the grid model."""
        return self.unsafe_old or self.crash_g2

    @property
    def unknown(self) -> bool:
        return self.seam and (self.fallback_strict or self.fallback_g2)

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


def engine_boxes(x0, x1, y0, y1, grid: int = GRID):
    """(bx0, by0, bw, bh): pixel boxes (inclusive xmin..xmax, y from the bottom) snapped to the engine grid.

    x0 = grid * (xmin // grid), x0 + w = grid * (xmax // grid + 1); the same in y. grid = 1 gives the
    old convention (A) boxes (w = span + 1).
    """
    x0, x1, y0, y1 = (np.asarray(a, dtype=np.int64) for a in (x0, x1, y0, y1))
    bx0 = (x0 // grid) * grid
    by0 = (y0 // grid) * grid
    return bx0, by0, (x1 // grid + 1) * grid - bx0, (y1 // grid + 1) * grid - by0


def grid_centre(x0, x1, y0, y1, grid: int = GRID) -> tuple:
    """(mean, rect, fallback, dx) of one region on engine boxes, as in RVA 0x15A4770 / 0x15A5C20 / 0x15A4C20.

    mean = truncating mean of ``x0 + w/2, y0 + h/2``; rect = union of the member boxes; fallback = the
    mean lies in no member box (inclusive at both ends); dx = mean.x - (rect x0 + rect w / 2).
    """
    bx, by, bw, bh = engine_boxes(x0, x1, y0, y1, grid)
    n = len(bx)
    mx = _trunc_div(int((bx + bw // 2).sum()), n)
    my = _trunc_div(int((by + bh // 2).sum()), n)
    inside = bool(((bx <= mx) & (mx <= bx + bw) & (by <= my) & (my <= by + bh)).any())
    rx0, ry0 = int(bx.min()), int(by.min())
    rw, rh = int((bx + bw).max()) - rx0, int((by + bh).max()) - ry0
    return (mx, my), (rx0, ry0, rw, rh), not inside, mx - (rx0 + rw // 2)


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
    gmean, grect, gfb, gdx = grid_centre(x0, x1, y0, y1)
    return RegionCentre(rid, len(ids), (mx, my), (rx0, ry0, rw, rh), not inside[min(INSIDE_SLACK)],
                        not inside[max(INSIDE_SLACK)], mx - (rx0 + rw // 2), my - (ry0 + rh // 2), gap, seam, sig,
                        not inside_strict, inner_margin(mx, my, x0, x1, y0, y1), gmean, grect, gfb, gdx)


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
            f"margin {c.margin}, grid model dx {c.dx_g2}{' fallback' if c.fallback_g2 else ''}"
            f"{', wraps' if c.seam else ''})")


def split_known(fails: list, centres: dict, known: dict | None) -> tuple:
    """(remaining failures, [known-risk notes]) for ``known`` = {region id: (member-box signature, reason)}.

    A failure is allowed only when its region is listed AND its signature matches exactly (same member
    boxes, hence the same mean, rect and divisors); any other failure, or a changed signature, stays.
    """
    known = known or {}
    rest, notes = [], []
    for r in fails:
        k = known.get(r)
        if k is not None and centres[r].signature == k[0]:
            notes.append(f"KNOWN RISK (allowed): region {describe(centres[r])}, signature {k[0]}: {k[1]}")
        else:
            rest.append(r)
    return rest, notes


def guard_problems(centres: dict, observed: dict | None = None, clear_ids=None, known: dict | None = None,
                   notes: list | None = None) -> list:
    """--check messages (P00b-f4): guard failures, and regions whose mean is not >= 1 px inside a member box.

    ``observed``: centres of a map seen loading (vanilla) for the wrapping-region twin rule; {} for new
    geometry. ``clear_ids``: the regions that must never take the fallback (None = all of them).
    ``known``: {region id: (signature, reason)} accepted as a documented known risk (``split_known``);
    their notes are appended to ``notes``.
    """
    probs = []
    fails, known_notes = split_known(guard_failures(centres, observed), centres, known)
    if notes is not None:
        notes.extend(known_notes)
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
