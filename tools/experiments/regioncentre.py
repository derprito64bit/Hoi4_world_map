"""Offline model of HOI4 1.19.3's strategic-region centre calculation (the EXP-03-24k crash).

Evidence (P00b-f3): both EXP-03-24k crash dumps stop in ``strategicregiontemplate.cpp``
(hoi4.exe 1.19.3.0.c01a, crash RVA 0x15A4CDC, caller RVA 0x15A4770). Reconstructed
from the disassembly and the dumped registers / region object ("Northern Norway",
54 provinces, rect (2990, 1854, 302, 170), mean point (3141, 1961)):

1. Every province carries a box ``(x0, y0, w, h)``: x0 = min column, y0 = min row
   counted from the **bottom** (BMP order), ``w = xmax - xmin + 1``, ``h = ymax - ymin + 1``.
   Its centre is ``(x0 + w // 2, y0 + h // 2)``.
2. The region's mean point M is the integer mean (truncating) of its provinces' centres.
3. If M lies inside (inclusive) the box of any member province, that province's centre
   becomes the region centre: done, no division.
4. Otherwise (the fallback) the engine marches along the line from the region
   rectangle's centre towards M. The region rectangle is the union of the member
   boxes with width ``max(x0 + w) - min(x0) + 1`` (= column span + 2; the dump shows
   302 for a 300-px span) and likewise the height. The slope is computed with an
   **integer division by ``M.x - (rx0 + rw // 2)``**, unguarded: if the mean point is
   vertically aligned with the rectangle's centre, the game dies with
   EXCEPTION_INT_DIVIDE_BY_ZERO during map loading (before "Loaded N provinces").

So a region is *unsafe* when step 3 fails and the divisor of step 4 is 0. Whether the
fallback runs at all depends only on geometry and membership, so the generator can
test and avoid it. Regions whose members touch the wrap seam are reported as
``seam`` (the engine keeps a second rectangle for them; this model does not cover it).

Checked against every in-game run so far: only EXP-03-24k is unsafe (region 191,
divisor -10 / -10 / -11 / 0 / +2 for vanilla / 16k / 20k / 24k / 30k). Vanilla
already takes the fallback in 14 regions with non-zero divisors, which is harmless.

Rules for the real map (P05 and the region builder):
* no region may be unsafe; re-check after every change to provinces or membership;
* prefer regions whose mean point falls inside a member box (the fallback never runs);
  ring-, C- and strip-shaped regions are the ones that take the fallback;
* symmetric or regular layouts (grid or strip filler, mirrored regions) put the mean
  exactly on the rectangle centre; EXP-09a-e region 113 is such a case.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .mapdata import bboxes


@dataclass(frozen=True)
class RegionCentre:
    region: int
    n: int
    mean: tuple            # (x, y) engine coordinates, y from the bottom
    rect: tuple            # (x0, y0, w, h) of the region rectangle
    fallback: bool         # mean point outside every member box -> line march runs
    divisor: int | None    # M.x - rect centre x (None when the fallback does not run)
    seam: bool             # a member touches column 0 or W-1

    @property
    def unsafe(self) -> bool:
        return self.fallback and self.divisor == 0


def province_boxes(pid: np.ndarray, n: int):
    """Engine boxes per ID: arrays x0, y0 (from the bottom), w, h; w = h = 0 for IDs without pixels."""
    H, W = pid.shape
    xmin, xmax, ymin, ymax = bboxes(pid, n)
    present = xmax >= 0
    x0 = np.where(present, xmin, 0)
    w = np.where(present, xmax - xmin + 1, 0)
    y0 = np.where(present, H - 1 - ymax, 0)
    h = np.where(present, ymax - ymin + 1, 0)
    return x0.astype(np.int64), y0.astype(np.int64), w.astype(np.int64), h.astype(np.int64)


def _trunc_div(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def region_centre(rid: int, members, boxes, W: int) -> RegionCentre:
    x0, y0, w, h = boxes
    ids = np.asarray(sorted(int(i) for i in members), dtype=np.int64)
    if len(ids) == 0:
        return RegionCentre(rid, 0, (0, 0), (0, 0, 0, 0), False, None, False)
    bx, by, bw, bh = x0[ids], y0[ids], w[ids], h[ids]
    cx = bx + bw // 2
    cy = by + bh // 2
    mx = _trunc_div(int(cx.sum()), len(ids))
    my = _trunc_div(int(cy.sum()), len(ids))
    inside = (bx <= mx) & (mx <= bx + bw) & (by <= my) & (my <= by + bh)
    rx0, ry0 = int(bx.min()), int(by.min())
    rw = int((bx + bw).max()) - rx0 + 1
    rh = int((by + bh).max()) - ry0 + 1
    seam = bool(((bx == 0) | (bx + bw >= W)).any())
    fallback = not bool(inside.any())
    divisor = mx - (rx0 + rw // 2) if fallback else None
    return RegionCentre(rid, len(ids), (mx, my), (rx0, ry0, rw, rh), fallback, divisor, seam)


def region_centres(pid: np.ndarray, regions: dict) -> dict:
    """{region id: RegionCentre} for ``regions`` = {region id: [province ids]}."""
    n = int(pid.max()) + 1
    for ids in regions.values():
        if len(ids):
            n = max(n, max(ids) + 1)
    boxes = province_boxes(pid, n)
    W = pid.shape[1]
    return {rid: region_centre(rid, regions[rid], boxes, W) for rid in sorted(regions)}


def unsafe_regions(pid: np.ndarray, regions: dict) -> list:
    """Region IDs whose centre calculation divides by zero in the engine (sorted)."""
    return [r for r, c in region_centres(pid, regions).items() if c.unsafe]
