"""EXP-09 synthetic world layout (pure numpy; no game files needed, testable on tiny canvases).

"Minimum loadable world": the game's logical world is kept (every vanilla
province ID with its type, every state, strategic region, owner, unit, focus
and event that refers to them), but drawn on a synthetic geography on the
project canvas:

* every land/lake province is a small bar (BAR_W x BAR_H px); the bars of a state
  sit side by side, states follow each other in "lines" of a central block
  separated by thin sea channels, so every land province is coastal and every
  state is one contiguous piece;
* four states sit at their real projected positions as landmarks for the owner
  (Chukotka at Cape Dezhnev, Alaska at Cape Prince of Wales, Greenland in the far
  north, Tierra del Fuego at Cape Horn), so screenshots can be taken at the seam
  and at the top/bottom edges;
* all remaining on-globe pixels are sea, cut into brick tiles; the first tiles
  take the vanilla sea IDs, extra tiles get new sea IDs;
* every off-globe pixel (outside the Equal Earth outline, from
  ``ee_project.Canvas.globe_mask``) belongs to a new lake province (the filler).
The geometry is not vanilla's and not real-world except for the four landmark
points; only IDs and attributes come from vanilla.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .common import KitError
from .mapdata import fix_x_crossings
from .tiling import merge_small, tile


@dataclass
class Params:
    bar_w: int = 6
    bar_h: int = 20
    gap: int = 8
    line_w: int = 3600
    sea_cell: int = 48
    off_cell: int = 120
    min_sea: int = 40
    min_off: int = 64
    margin: int = 2


@dataclass
class Layout:
    pid: np.ndarray                      # (H, W) int32 final province IDs
    sea_new: list                        # new sea IDs (after the vanilla ones)
    off_ids: list                        # new off-globe lake IDs
    lines: list = field(default_factory=list)       # list of [ids in one horizontal run of bars]
    anchors: dict = field(default_factory=dict)     # state id -> (row, col) of the landmark
    seam_fixes: list = field(default_factory=list)  # off-globe pixels given to sea at the seam (row, col)


def _fits(grid, globe, r0, c0, h, w, margin):
    H, W = grid.shape
    if r0 - margin < 0 or c0 - margin < 0 or r0 + h + margin > H or c0 + w + margin > W:
        return False
    win = (slice(r0 - margin, r0 + h + margin), slice(c0 - margin, c0 + w + margin))
    return bool(globe[win].all() and (grid[win] < 0).all())


def _put_bars(grid, ids, r0, c0, p: Params):
    for k, i in enumerate(ids):
        grid[r0:r0 + p.bar_h, c0 + k * p.bar_w:c0 + (k + 1) * p.bar_w] = i


def layout(globe: np.ndarray, units: list, anchors: list, sea_ids: list, next_id: int, p: Params = Params(),
           centre_row: int | None = None) -> Layout:
    """Place bars, tile the sea and the off-globe area.

    units   : [(state id or None, [province ids in bar order])] for the central block, in order
    anchors : [(state id, [ids], row, col, align)] align in left/right/center; placed first
    sea_ids : vanilla sea IDs, in the order they take the sea tiles
    next_id : first free ID (new seas, then off-globe lakes)
    """
    H, W = globe.shape
    grid = np.full((H, W), -1, dtype=np.int64)
    out_anchor, lines = {}, []
    for sid, ids, row, col, align in anchors:
        w = len(ids) * p.bar_w
        c0 = {"left": col, "right": col - w, "center": col - w // 2}[align]
        r0 = row - p.bar_h // 2
        dc = {"left": 1, "right": -1, "center": 0}[align]
        dr = 0 if align != "center" else (1 if row < H // 2 else -1)
        for _ in range(600):
            if _fits(grid, globe, r0, c0, p.bar_h, w, p.margin):
                break
            c0 += dc
            r0 += dr if dc == 0 else 0
            if dc and not (0 <= c0 < W):
                break
        else:
            raise KitError(f"cannot place landmark state {sid}")
        if not _fits(grid, globe, r0, c0, p.bar_h, w, p.margin):
            raise KitError(f"cannot place landmark state {sid}")
        _put_bars(grid, ids, r0, c0, p)
        out_anchor[sid] = (int(row), int(col))
        lines.append(list(ids))
    # central block: pack units into lines
    rows_of_units, cur, cur_w = [], [], 0
    for sid, ids in units:
        w = len(ids) * p.bar_w
        if w > p.line_w:
            raise KitError(f"state {sid} is wider than a line")
        if cur and cur_w + w > p.line_w:
            rows_of_units.append(cur)
            cur, cur_w = [], 0
        cur.append(list(ids))
        cur_w += w
    if cur:
        rows_of_units.append(cur)
    pitch = p.bar_h + p.gap
    height = len(rows_of_units) * pitch - p.gap
    centre_row = H // 2 if centre_row is None else centre_row
    top = centre_row - height // 2
    for k, line_units in enumerate(rows_of_units):
        ids = [i for u in line_units for i in u]
        w = len(ids) * p.bar_w
        r0, c0 = top + k * pitch, (W - w) // 2
        if not _fits(grid, globe, r0, c0, p.bar_h, w, p.margin):
            raise KitError("central block does not fit on the globe")
        _put_bars(grid, ids, r0, c0, p)
        lines.append(ids)
    placed = grid >= 0
    # sea tiles
    sea_mask = globe & ~placed
    lab, n = tile(sea_mask, p.sea_cell, p.sea_cell)
    lab, n = merge_small(lab, p.min_sea)
    if n < len(sea_ids):
        raise KitError(f"only {n} sea tiles for {len(sea_ids)} vanilla sea provinces; use a smaller sea cell")
    sea_map = np.array(list(sea_ids) + list(range(next_id, next_id + n - len(sea_ids))), dtype=np.int64)
    sea_new = list(range(next_id, next_id + n - len(sea_ids)))
    next_id += n - len(sea_ids)
    grid[lab >= 0] = sea_map[lab[lab >= 0]]
    # off-globe lakes
    olab, m = tile(~globe, p.off_cell, p.off_cell)
    olab, m = merge_small(olab, p.min_off)
    off_ids = list(range(next_id, next_id + m))
    grid[olab >= 0] = olab[olab >= 0] + next_id
    if (grid < 0).any():
        raise KitError("layout left pixels without a province")
    pid = grid.astype(np.int32)
    sea_set = np.zeros(int(pid.max()) + 1, dtype=bool)
    sea_set[np.asarray(list(sea_ids) + sea_new, dtype=np.int64)] = True
    off_set = np.zeros_like(sea_set)
    off_set[np.asarray(off_ids, dtype=np.int64)] = True

    def can_take(a, b):
        return a != b and ((sea_set[a] and sea_set[b]) or (off_set[a] and off_set[b]))

    # Where the outline leaves both image edges in the same row (the tips of the off-globe lenses at the
    # equator), off-globe above sea on both sides of the wrap seam is an X-crossing that no same-class
    # change can fix without a province straddling the seam. The right-edge off-globe pixel of that row
    # goes to the sea province next to it instead (at most a few pixels, recorded).
    seam_fixes = []
    for r in range(H - 1):
        a, b, c, d = pid[r, W - 1], pid[r, 0], pid[r + 1, W - 1], pid[r + 1, 0]
        if len({int(a), int(b), int(c), int(d)}) < 4:
            continue
        for (r1, c1), (r2, c2) in (((r, W - 1), (r + 1, W - 1)), ((r + 1, W - 1), (r, W - 1))):
            if off_set[pid[r1, c1]] and sea_set[pid[r2, c2]] and off_set[pid[r1, (c1 + 1) % W]]:
                pid[r1, c1] = pid[r2, c2]
                seam_fixes.append((r1, c1))
                break
    fix_x_crossings(pid, can_take)
    return Layout(pid=pid, sea_new=sea_new, off_ids=off_ids, lines=lines, anchors=out_anchor,
                  seam_fixes=seam_fixes)
