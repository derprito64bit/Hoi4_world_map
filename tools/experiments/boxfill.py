"""Clean filled shapes for the TOO LARGE BOX probes (P00b-f6).

A *shape* is one rectangle, or a union of non-overlapping rectangles (the L of EXP-02c-sea-L),
of one kind (land or sea). One host province takes every pixel of the shape, so that the host's
bounding box is the shape's bounding box, with none of the side effects that spoiled
EXP-02b-block-400:

* every rectangle and its 1-px ring (clipped at the top / bottom map edge) hold only provinces of
  the host's kind (no lake inside a land shape, no land in or next to a sea shape), so no coastal
  flag and no province type changes; no rectangle touches the wrap seam (columns 0 and W-1);
* the host lies wholly inside the shape and takes every pixel of it: no enclave, no donor remnant
  inside (fill exactly 1.0);
* every other province with pixels in the shape (a *donor*) is not protected
  (``exp02b.protected_ids``) and keeps a part outside the shape of at least ``REMNANT`` px, in
  which each of its original 4-connected parts stays one connected piece (``donor_splits``): no
  donor is cut in two and no piece of a donor vanishes;
* no X-crossing appears (only the corners of the rectangles can make one);
* whole-map rules, checked on the finished map by ``exp02c.whole_map_problems``: the sea provinces
  of every naval strategic region stay one 4-connected piece (``fractioned_naval``), no strategic
  region and no state becomes non-contiguous, and the region-centre guard has 0 failures.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from .mapdata import SEA, areas, bboxes, x_crossings_window

FOUR = [[0, 1, 0], [1, 1, 1], [0, 1, 0]]
REMNANT = 9            # px every donor keeps outside the shape (EXP-04: the engine logs provinces of <= 8 px)


class Rect(tuple):
    """(r0, c0, h, w): top row, left column, height, width (pixels, row 0 = north)."""

    def __new__(cls, r0, c0, h, w):
        return super().__new__(cls, (int(r0), int(c0), int(h), int(w)))

    r0 = property(lambda s: s[0])
    c0 = property(lambda s: s[1])
    h = property(lambda s: s[2])
    w = property(lambda s: s[3])

    def window(self):
        return slice(self.r0, self.r0 + self.h), slice(self.c0, self.c0 + self.w)


def as_shape(shape) -> tuple:
    """A Rect or an iterable of Rects -> tuple of Rects (sorted: deterministic)."""
    if isinstance(shape, Rect):
        return (shape,)
    return tuple(sorted(Rect(*r) for r in shape))


def overlaps(shape) -> bool:
    rs = as_shape(shape)
    for i, a in enumerate(rs):
        for b in rs[i + 1:]:
            if a.r0 < b.r0 + b.h and b.r0 < a.r0 + a.h and a.c0 < b.c0 + b.w and b.c0 < a.c0 + a.w:
                return True
    return False


def bounding(shape) -> tuple:
    """(x0, x1, y0, y1) inclusive bounding box of the shape (row 0 = north)."""
    rs = as_shape(shape)
    return (min(r.c0 for r in rs), max(r.c0 + r.w - 1 for r in rs), min(r.r0 for r in rs),
            max(r.r0 + r.h - 1 for r in rs))


def shape_mask(shape, hw: tuple) -> np.ndarray:
    m = np.zeros(hw, dtype=bool)
    for r in as_shape(shape):
        m[r.window()] = True
    return m


def kind_ok(tmap: np.ndarray, kind: int, shape) -> bool:
    """Each rectangle and its ring (clipped at the top/bottom map edge) hold only ``kind``; none touches the seam."""
    H, W = tmap.shape
    for r in as_shape(shape):
        r0, c0, h, w = r
        if r0 < 0 or r0 + h > H or c0 < 1 or c0 + w > W - 1 or h < 1 or w < 1:
            return False
        t = tmap[max(0, r0 - 1):min(H, r0 + h + 1), c0 - 1:c0 + w + 1]
        if not (t == kind).all():
            return False
    return True


def _integral(mask: np.ndarray) -> np.ndarray:
    return np.pad(mask.astype(np.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))


def _box_sum(ii: np.ndarray, r0: int, c0: int, r1: int, c1: int) -> int:
    """Sum of the mask over rows r0..r1-1, cols c0..c1-1."""
    return int(ii[r1, c1] - ii[r0, c1] - ii[r1, c0] + ii[r0, c0])


def donor_splits(pid: np.ndarray, d: int, shape, bb) -> tuple:
    """(outside px, ok): ``ok`` = every original 4-connected part of donor ``d`` keeps >= 1 px outside the
    shape and that outside part is one connected piece (wrap ignored: shapes and donors stay off the seam)."""
    x0, x1, y0, y1 = int(bb[0][d]), int(bb[1][d]), int(bb[2][d]), int(bb[3][d])
    win = pid[y0:y1 + 1, x0:x1 + 1] == d
    out = win.copy()
    for r in as_shape(shape):
        a0, a1 = max(r.r0, y0) - y0, min(r.r0 + r.h, y1 + 1) - y0
        b0, b1 = max(r.c0, x0) - x0, min(r.c0 + r.w, x1 + 1) - x0
        if a0 < a1 and b0 < b1:
            out[a0:a1, b0:b1] = False
    lab0, n0 = ndimage.label(win, structure=FOUR)
    _, n1 = ndimage.label(out, structure=FOUR)
    kept = len(np.unique(lab0[out])) if out.any() else 0
    return int(out.sum()), bool(n1 == n0 and kept == n0)


def shape_candidate(pid: np.ndarray, types: np.ndarray, area: np.ndarray, bb, kind: int, shape,
                    protected: set, avoid=()) -> dict | None:
    """{"host", "donors"} if the shape can be filled cleanly (module rules, except the whole-map ones)."""
    rs = as_shape(shape)
    if overlaps(rs):
        return None
    sub = np.concatenate([pid[r.window()].ravel() for r in rs])
    ids, cnt = np.unique(sub, return_counts=True)
    whole = [int(i) for i, c in zip(ids.tolist(), cnt.tolist()) if c == area[i]]
    if len(whole) != 1:
        return None
    host = whole[0]
    if types[host] != kind or host in protected or host in set(avoid):
        return None
    donors = sorted(int(i) for i in ids.tolist() if i != host)
    for d in donors:
        if types[d] != kind or d in protected:
            return None
        n_out, ok = donor_splits(pid, d, rs, bb)
        if not ok or n_out < REMNANT:
            return None
    return {"host": host, "donors": donors}


def fill(pid: np.ndarray, shape, host: int) -> np.ndarray:
    out = pid.copy()
    for r in as_shape(shape):
        out[r.window()] = host
    return out


def corner_crossings(pid: np.ndarray, shape) -> int:
    n = 0
    for r in as_shape(shape):
        ys, _ = x_crossings_window(pid, r.r0 - 1, r.r0 + r.h + 1, r.c0 - 1, r.c0 + r.w + 1)
        n += len(ys)
    return n


def find_rects(pid: np.ndarray, types: np.ndarray, kind: int, h: int, w: int, protected: set, *, rows=None,
               cols=None, step: int = 2, limit: int = 1, avoid=()) -> list:
    """[(Rect, {"host", "donors"})]: clean h x w rectangles of ``kind`` (module rules except the whole-map
    ones), row-major from the top left. ``rows`` / ``cols``: candidate top rows / left columns (default:
    every ``step``-th, starting at row 0 / column 2, i.e. on even pixels for even steps). Deterministic.
    """
    H, W = pid.shape
    n = len(types)
    tmap = types[pid]
    area = areas(pid, n)
    bb = bboxes(pid, n)
    ii = _integral(tmap != kind)
    bx0, bx1, by0, by1 = (np.asarray(a) for a in bb)
    present = bx1 >= 0
    rows = range(0, H - h + 1, step) if rows is None else rows
    cols = range(2, W - w, step) if cols is None else cols
    out = []
    for r0 in rows:
        cand_r = present & (by0 >= r0) & (by1 < r0 + h)
        if not cand_r.any():
            continue
        for c0 in cols:
            if c0 < 1 or c0 + w > W - 1:
                continue
            if _box_sum(ii, max(0, r0 - 1), c0 - 1, min(H, r0 + h + 1), c0 + w + 1):
                continue
            inside = cand_r & (bx0 >= c0) & (bx1 < c0 + w)
            if int(inside.sum()) != 1:
                continue
            rect = Rect(r0, c0, h, w)
            got = shape_candidate(pid, types, area, bb, kind, rect, protected, avoid)
            if got is None or corner_crossings(fill(pid, rect, got["host"]), rect):
                continue
            out.append((rect, got))
            if len(out) >= limit:
                return out
    return out


def ell(H: int, c_arm: int, arm_w: int, arm_h: int, band_w: int, band_h: int, arm_left: bool) -> tuple:
    """An L on the bottom map edge: a band ``band_w`` x ``band_h`` along the last rows and a vertical arm
    ``arm_w`` wide rising from it to a total height ``arm_h``, at the band's left (``arm_left``) or right end.
    Two non-overlapping rectangles; bounding box ``band_w`` x ``arm_h``."""
    c_band = c_arm if arm_left else c_arm + arm_w - band_w
    return as_shape([Rect(H - band_h, c_band, band_h, band_w), Rect(H - arm_h, c_arm, arm_h - band_h, arm_w)])


def find_ells(pid: np.ndarray, types: np.ndarray, kind: int, arm_w: int, arm_h: int, band_w: int, band_h: int,
              protected: set, *, cols=None, step: int = 2, limit: int = 1, avoid=()) -> list:
    """[(shape, {"host", "donors"})]: clean bottom-edge Ls (``ell``), arm column left to right, arm on the
    band's left end before its right end. Deterministic."""
    H, W = pid.shape
    n = len(types)
    tmap = types[pid]
    area = areas(pid, n)
    bb = bboxes(pid, n)
    ii = _integral(tmap != kind)
    cols = range(2, W - arm_w, step) if cols is None else cols
    out = []
    for c in cols:
        for left in (True, False):
            shape = ell(H, c, arm_w, arm_h, band_w, band_h, left)
            if any(r.c0 < 1 or r.c0 + r.w > W - 1 or
                   _box_sum(ii, max(0, r.r0 - 1), r.c0 - 1, min(H, r.r0 + r.h + 1), r.c0 + r.w + 1)
                   for r in shape):
                continue
            got = shape_candidate(pid, types, area, bb, kind, shape, protected, avoid)
            if got is None or corner_crossings(fill(pid, shape, got["host"]), shape):
                continue
            out.append((shape, got))
            if len(out) >= limit:
                return out
    return out


# ------------------------------------------------------------------ whole-map rules
def pixel_groups_split(pid: np.ndarray, groups: dict) -> set:
    """Keys of ``groups`` ({key: [ids]}) whose members are not connected by 4-contacts (wrap included)."""
    from .exp02b import noncontiguous_groups
    return noncontiguous_groups(pid, groups, set())


def naval_regions(province_region: dict, types: np.ndarray) -> dict:
    """{region id: [sea province ids]} for every region that holds a sea province (naval strategic region).

    Only the sea members: 41 vanilla naval regions also list land (island) provinces, and those need not
    touch the sea members by pixels (vanilla region 93 Banda Sea's islands do not, and vanilla loads).
    """
    by = {}
    for p, (rid, _) in province_region.items():
        if 0 < p < len(types) and types[p] == SEA:
            by.setdefault(rid, []).append(p)
    return {r: sorted(ps) for r, ps in sorted(by.items())}


def fractioned_naval(pid: np.ndarray, province_region: dict, types: np.ndarray) -> set:
    """Naval strategic regions whose sea provinces are not one 4-connected piece (wrap included, no
    adjacencies.csv links): the engine's fatal ``MAP_ERROR: Naval strategic region ... is fractioned``.
    Vanilla 1.19.3: none of its 98 naval regions; EXP-02b-block-400: exactly the two the game reported."""
    return pixel_groups_split(pid, naval_regions(province_region, types))


def fractioned_parts(pid: np.ndarray, province_region: dict, types: np.ndarray) -> dict:
    """{region id: sorted sea provinces outside the piece that holds the region's lowest sea ID} for
    fractioned naval regions: the IDs the engine lists as "separated from the rest".

    P00b-f7: the engine keeps the piece of the lowest ID, not the largest piece: in EXP-09a's region
    "extra sea 37" it listed the 18-province piece and kept the 6-province piece of 14455. All 8 logged
    regions (EXP-02b-block-400: 2, EXP-09a: 6) fit this; in each of them the lowest sea ID is also the
    first one listed in the region file, so "the piece of the first listed province" fits equally."""
    from .mapdata import adjacency_pairs
    groups = naval_regions(province_region, types)
    bad = fractioned_naval(pid, province_region, types)
    pairs = adjacency_pairs(pid).tolist()
    out = {}
    for rid in sorted(bad):
        ms = set(groups[rid])
        parent = {p: p for p in ms}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for a, b in pairs:
            if a in ms and b in ms:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
        comps = {}
        for p in sorted(ms):
            comps.setdefault(find(p), []).append(p)
        keep = comps[find(min(ms))]
        out[rid] = sorted(ms - set(keep))
    return out
