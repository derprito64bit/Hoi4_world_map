"""EXP-09 synthetic world layout (pure numpy; no game files needed, testable on tiny canvases).

"Minimum loadable world": the game's logical world is kept (every vanilla
province ID with its type, every state, strategic region, owner, unit, focus
and event that refers to them), but drawn on a synthetic geography on the
project canvas:

* every vanilla province (land, lake and sea) is a small bar (BAR_W x BAR_H px);
  a "unit" (for EXP-09: one vanilla strategic region = its states' land and lake
  bars, its loose lakes, then its sea provinces) is ONE contiguous run of bars in
  one "line" of a central block; lines are separated by thin sea channels, so every
  land province is coastal and every state is one contiguous piece;
* region-centre guard (P00b-f4, ``regioncentre.py``): a run of k bars has its middle
  bar doubled in width when k is even (``run_widths``), so the truncating mean of the
  member box centres lies >= 1 px inside a member box and the engine's centre
  fallback (the EXP-03-24k divide-by-zero) never runs for a vanilla region;
* four states sit at their real projected positions as landmarks for the owner
  (Chukotka at Cape Dezhnev, Alaska at Cape Prince of Wales, Greenland in the far
  north, Tierra del Fuego at Cape Horn), so screenshots can be taken at the seam
  and at the top/bottom edges; the rest of a landmark's region is placed in the
  same run next to it;
* all remaining on-globe pixels are new sea provinces (brick tiles); every
  off-globe pixel (outside the Equal Earth outline, from
  ``ee_project.Canvas.globe_mask``) belongs to a new lake province (the filler).
  Both are grouped into new regions by ``regiongroup.grow_regions`` (compact, mean
  inside a member box, never across the wrap seam, each region one 4-connected piece so
  no naval region is "fractioned", P00b-f7), after every pixel repair.
The geometry is not vanilla's and not real-world except for the four landmark
points; only IDs and attributes come from vanilla.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .common import KitError
from .mapdata import fix_x_crossings
from .regioncentre import inner_margin, mean_point
from .regiongroup import Boxes, grow_regions
from .tiling import merge_small, relabel_row_major, tile


@dataclass
class Params:
    bar_w: int = 6
    bar_h: int = 20
    gap: int = 8
    line_w: int = 3600
    sea_cell: int = 48            # sea tile width in the central block (height: one line pitch)
    open_cell: int = 64           # open-sea tiles elsewhere (square)
    off_cell: int = 120
    min_sea: int = 40
    min_off: int = 64
    margin: int = 2
    region_max: int = 40          # members per new sea / filler region
    connected_regions: bool = True   # P00b-f7: every new region one 4-connected piece (False: the pre-f7
                                     # grouping that cut 6 EXP-09 sea regions in pieces; kept to reproduce it)


@dataclass
class Layout:
    pid: np.ndarray                      # (H, W) int32 final province IDs
    sea_new: list                        # all new sea IDs (sea_north first, then the southern ones)
    off_ids: list                        # new off-globe lake IDs
    sea_north: list = field(default_factory=list)   # new sea IDs of the tiles above north_row
    lines: list = field(default_factory=list)       # list of [ids in one horizontal run of bars]
    anchors: dict = field(default_factory=dict)     # anchor key -> (row, col) of the landmark
    seam_fixes: list = field(default_factory=list)  # off-globe pixels given to sea at the seam (row, col)
    runs: dict = field(default_factory=dict)        # unit / anchor key -> [ids] placed as one run
    sea_regions: list = field(default_factory=list)  # [("north" | "south", [new sea ids])]
    off_regions: list = field(default_factory=list)  # [("north" | "south", [filler lake ids])]


def run_widths(k: int, w: int) -> list:
    """Bar widths of a run of ``k`` bars of width ``w``: the middle bar is 2w wide when k is even.

    With box centres ``x0 + w // 2`` the mean of an odd run is the middle bar's centre; for an
    even run it falls 1-2 px right of the doubled middle bar's left edge. ``w >= 4`` keeps it
    >= 1 px off every box edge (``run_margin``).
    """
    if k <= 0:
        return []
    ws = [w] * k
    if k % 2 == 0:
        ws[k // 2] = 2 * w
    return ws


def run_margin(widths: list, h: int) -> int:
    """``regioncentre.inner_margin`` of one run of bars with these widths and height ``h``."""
    x0 = np.cumsum([0] + list(widths[:-1])).astype(np.int64)
    x1 = x0 + np.asarray(widths, dtype=np.int64) - 1
    y0 = np.zeros(len(widths), dtype=np.int64)
    y1 = y0 + h - 1
    mx, my = mean_point(x0, x1, y0, y1)
    return inner_margin(mx, my, x0, x1, y0, y1)


def _widths(ids, p: Params, key) -> list:
    ws = run_widths(len(ids), p.bar_w)
    if ws and run_margin(ws, p.bar_h) < 1:
        raise KitError(f"run {key}: bars {p.bar_w}x{p.bar_h} px are too small for a region mean inside a bar "
                       "(need bar_w >= 4, bar_h >= 3)")
    return ws


def _fits(grid, globe, r0, c0, h, w, margin):
    H, W = grid.shape
    if r0 - margin < 0 or c0 - margin < 0 or r0 + h + margin > H or c0 + w + margin > W:
        return False
    win = (slice(r0 - margin, r0 + h + margin), slice(c0 - margin, c0 + w + margin))
    return bool(globe[win].all() and (grid[win] < 0).all())


def _put_run(grid, ids, widths, r0, c0, h):
    c = c0
    for i, w in zip(ids, widths):
        grid[r0:r0 + h, c:c + w] = i
        c += w


def layout(globe: np.ndarray, units: list, anchors: list, next_id: int, p: Params = Params(),
           centre_row: int | None = None, north_row: int | None = None) -> Layout:
    """Place the runs of bars, tile the sea and the off-globe area, group the new tiles into regions.

    units    : [(key, [province ids in bar order])] for the central block, in order; each one run
    anchors  : [(key, [ids], row, col, align, (i0, i1))], align in left/right/center: ids[i0:i1]
               (the landmark state) starts at / ends at / is centred on (row, col); placed first
    next_id  : first free ID (new seas, then off-globe lakes)
    north_row: sea tiles centred above this row get new IDs first (their regions get cold weather)
    """
    H, W = globe.shape
    grid = np.full((H, W), -1, dtype=np.int64)
    out_anchor, lines, runs = {}, [], {}
    for key, ids, row, col, align, (i0, i1) in anchors:
        ws = _widths(ids, p, key)
        w = sum(ws)
        off0, off1 = sum(ws[:i0]), sum(ws[:i1])
        c0 = {"left": col - off0, "right": col - off1, "center": col - (off0 + off1) // 2}[align]
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
            raise KitError(f"cannot place landmark run {key}")
        if not _fits(grid, globe, r0, c0, p.bar_h, w, p.margin):
            raise KitError(f"cannot place landmark run {key}")
        _put_run(grid, ids, ws, r0, c0, p.bar_h)
        out_anchor[key] = (int(row), int(col))
        lines.append(list(ids))
        runs[key] = list(ids)
    # central block: pack units (one run each, never split) into lines
    rows_of_units, cur, cur_w = [], [], 0
    for key, ids in units:
        ws = _widths(ids, p, key)
        w = sum(ws)
        if w > p.line_w:
            raise KitError(f"unit {key} is wider than a line")
        if cur and cur_w + w > p.line_w:
            rows_of_units.append(cur)
            cur, cur_w = [], 0
        cur.append((list(ids), ws))
        cur_w += w
        runs[key] = list(ids)
    if cur:
        rows_of_units.append(cur)
    pitch = p.bar_h + p.gap
    height = len(rows_of_units) * pitch - p.gap
    centre_row = H // 2 if centre_row is None else centre_row
    top = centre_row - height // 2
    span = (W, 0)                        # columns covered by the central lines
    for k, line_units in enumerate(rows_of_units):
        ids = [i for u, _ in line_units for i in u]
        ws = [x for _, wu in line_units for x in wu]
        w = sum(ws)
        r0, c0 = top + k * pitch, (W - w) // 2
        span = (min(span[0], c0), max(span[1], c0 + w))
        if not _fits(grid, globe, r0, c0, p.bar_h, w, p.margin):
            raise KitError("central block does not fit on the globe")
        _put_run(grid, ids, ws, r0, c0, p.bar_h)
        lines.append(ids)
    placed = grid >= 0
    # sea tiles, all new IDs: tiles whose centre lies above north_row first (cold new regions)
    # In the central block the bands are one pitch high and start at the first line (bar rows + the channel
    # below), so no band boundary cuts a channel into slivers that would merge into long, many-neighbour pieces.
    sea_mask = globe & ~placed
    zone = np.zeros((H, W), dtype=bool)
    zone[max(top, 0):max(0, min(H, top + len(rows_of_units) * pitch)),
         max(0, span[0] - p.sea_cell):max(0, min(W, span[1] + p.sea_cell))] = True
    lab1, n1 = tile(sea_mask & zone, p.sea_cell, pitch, row0=top)
    lab2, _ = tile(sea_mask & ~zone, p.open_cell, p.open_cell)
    lab, n = relabel_row_major(np.where(lab1 >= 0, lab1, np.where(lab2 >= 0, lab2 + n1, -1)))
    lab, n = merge_small(lab, p.min_sea, min_side=3)
    ys_, xs_ = np.nonzero(lab >= 0)
    ls = lab[ys_, xs_]
    cy = np.bincount(ls, weights=ys_, minlength=n) / np.maximum(np.bincount(ls, minlength=n), 1)
    is_north = [north_row is not None and cy[k] < north_row for k in range(n)]
    order = [k for k in range(n) if is_north[k]] + [k for k in range(n) if not is_north[k]]
    sea_map = np.zeros(n, dtype=np.int64)
    sea_map[order] = np.arange(next_id, next_id + n)
    sea_new = list(range(next_id, next_id + n))
    sea_north = sea_new[:sum(is_north)]
    next_id += n
    grid[lab >= 0] = sea_map[lab[lab >= 0]]
    # off-globe lakes
    olab, m = tile(~globe, p.off_cell, p.off_cell)
    olab, m = merge_small(olab, p.min_off, min_side=3)
    off_ids = list(range(next_id, next_id + m))
    grid[olab >= 0] = olab[olab >= 0] + next_id
    if (grid < 0).any():
        raise KitError("layout left pixels without a province")
    pid = grid.astype(np.int32)
    sea_set = np.zeros(int(pid.max()) + 1, dtype=bool)
    if sea_new:
        sea_set[np.asarray(sea_new, dtype=np.int64)] = True
    off_set = np.zeros_like(sea_set)
    if off_ids:
        off_set[np.asarray(off_ids, dtype=np.int64)] = True

    def can_take(a, b):
        # only new tiles give or take pixels: the bars, whose boxes decide the vanilla region centres, never change
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
    # new regions from the final pixels (after every repair): compact, mean inside a member box, no wrap
    bx = Boxes(pid)
    north_set = set(sea_north)
    sea_cls = {i: ("north" if i in north_set else "south") for i in sea_new}
    ys_, xs_ = np.nonzero(off_set[pid])
    oid = pid[ys_, xs_]
    ocy = np.bincount(oid, weights=ys_, minlength=len(off_set)) / np.maximum(np.bincount(oid, minlength=len(off_set)), 1)
    off_cls = {i: ("north" if ocy[i] < H / 2 else "south") for i in off_ids}
    kc = p.connected_regions
    sea_regions = [(sea_cls[g[0]], g) for g in grow_regions(pid, sea_new, sea_cls, p.region_max, boxes=bx,
                                                            keep_connected=kc)]
    off_regions = [(off_cls[g[0]], g) for g in grow_regions(pid, off_ids, off_cls, p.region_max, boxes=bx,
                                                            keep_connected=kc)]
    return Layout(pid=pid, sea_new=sea_new, sea_north=sea_north, off_ids=off_ids, lines=lines, anchors=out_anchor,
                  seam_fixes=seam_fixes, runs=runs, sea_regions=sea_regions, off_regions=off_regions)
