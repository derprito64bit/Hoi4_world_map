"""Group new filler provinces into strategic regions that never take the engine's centre fallback (P00b-f4).

The EXP-03-24k crash (``regioncentre.py``) happens only when a region's mean point lies
in no member box. ``grow_regions`` builds regions whose mean lies >= 1 px inside a
member box (``regioncentre.inner_margin``), so the fallback never runs under any box
convention, and which never contain members at both column 0 and column W-1 (the model
does not cover wrapping regions). Every region is one 4-connected piece (P00b-f7): the engine
refuses a naval strategic region whose sea provinces fall apart (``MAP_ERROR: Naval strategic
region ... is fractioned``; EXP-09a, 2026-09-30), so members are dropped again only when the rest
stays connected (``connected``). Pure numpy, deterministic, testable on tiny maps.
"""
from __future__ import annotations

import numpy as np

from .common import KitError
from .regioncentre import inner_margin, mean_point, pixel_boxes


class Boxes:
    """Pixel boxes (y from the bottom) of a pid array, with the region-centre test for member lists."""

    def __init__(self, pid: np.ndarray, n: int | None = None):
        n = int(pid.max()) + 1 if n is None else n
        self.x0, self.x1, self.y0, self.y1 = pixel_boxes(pid, n)
        self.W = pid.shape[1]

    def margin(self, ids) -> int:
        a = np.asarray(ids, dtype=np.int64)
        x0, x1, y0, y1 = self.x0[a], self.x1[a], self.y0[a], self.y1[a]
        mx, my = mean_point(x0, x1, y0, y1)
        return inner_margin(mx, my, x0, x1, y0, y1)

    def wraps(self, ids) -> bool:
        a = np.asarray(ids, dtype=np.int64)
        return bool((self.x0[a] == 0).any() and (self.x1[a] == self.W - 1).any())

    def ok(self, ids, margin: int = 1) -> bool:
        """Mean >= ``margin`` px inside a member box and the members do not reach both image edges."""
        return self.margin(ids) >= margin and not self.wraps(ids)


def neighbours(pid: np.ndarray, ids) -> dict:
    """{id: sorted 4-neighbours among ``ids``} (no wrap: a region never joins across the seam)."""
    want = np.zeros(int(pid.max()) + 1, dtype=bool)
    want[np.asarray(sorted(ids), dtype=np.int64)] = True
    a = np.concatenate([pid[:, :-1].ravel(), pid[:-1].ravel()]).astype(np.int64)
    b = np.concatenate([pid[:, 1:].ravel(), pid[1:].ravel()]).astype(np.int64)
    m = (a != b) & want[a] & want[b]
    k = np.unique(np.minimum(a[m], b[m]) * (1 << 32) + np.maximum(a[m], b[m]))
    out = {int(i): [] for i in ids}
    for lo, hi in zip((k >> 32).tolist(), (k & 0xFFFFFFFF).tolist()):
        out[lo].append(hi)
        out[hi].append(lo)
    return {i: sorted(v) for i, v in out.items()}


def connected(members, nb: dict) -> bool:
    """True if ``members`` form one piece over the neighbour lists ``nb`` ({id: [ids]})."""
    ms = set(members)
    if len(ms) <= 1:
        return True
    start = min(ms)
    seen, todo = {start}, [start]
    while todo:
        for j in nb[todo.pop()]:
            if j in ms and j not in seen:
                seen.add(j)
                todo.append(j)
    return len(seen) == len(ms)


def grow_regions(pid: np.ndarray, ids, cls: dict | None = None, max_members: int = 40, margin: int = 1,
                 boxes: Boxes | None = None, keep_connected: bool = True) -> list:
    """Partition ``ids`` into regions (sorted lists) that each pass ``Boxes.ok``.

    The smallest unassigned ID seeds a region, which grows breadth-first over 4-neighbours of
    the same class (``cls[id]``, e.g. north/south weather), nearest to the seed first, to at most
    ``max_members``. If its mean is not >= ``margin`` px inside a member box, members are dropped
    again (the first single removal, farthest first, that makes it pass; else the farthest one)
    and seed later regions. With ``keep_connected`` (default; P00b-f7) only members whose removal
    leaves the rest one 4-connected piece are dropped (a connected region always has such a member
    besides the seed), so every region stays one piece; ``keep_connected=False`` is the pre-f7
    behaviour that cut 6 EXP-09 sea regions in pieces, kept only to reproduce that record (EXP-08's
    padding regions come out byte-identical either way). A single member passes when its box is
    >= 3 px each way; a region that still fails is merged into a neighbouring region of its class with which the union
    passes, else KitError.
    """
    ids = sorted(int(i) for i in ids)
    if not ids:
        return []
    cls = cls or {}
    bx = boxes or Boxes(pid)
    cx = bx.x0 + (bx.x1 - bx.x0 + 1) // 2
    cy = bx.y0 + (bx.y1 - bx.y0 + 1) // 2
    nb = neighbours(pid, ids)
    group_of: dict = {}
    groups: list = []

    def dist(j, seed):
        return (int(cx[j]) - int(cx[seed])) ** 2 + (int(cy[j]) - int(cy[seed])) ** 2

    for seed in ids:
        if seed in group_of:
            continue
        c0 = cls.get(seed)
        g, inside = [seed], {seed}
        frontier = {j for j in nb[seed] if j not in group_of and cls.get(j) == c0}
        while len(g) < max_members and frontier:
            pick = min(frontier, key=lambda j: (dist(j, seed), j))
            frontier.discard(pick)
            g.append(pick)
            inside.add(pick)
            frontier |= {j for j in nb[pick] if j not in group_of and j not in inside and cls.get(j) == c0}
        while len(g) > 1 and not bx.ok(g, margin):
            far = sorted(g[1:], key=lambda j: (-dist(j, seed), j))
            if keep_connected:
                far = [j for j in far if connected([i for i in g if i != j], nb)]
            drop = next((j for j in far if bx.ok([i for i in g if i != j], margin)), far[0])
            g.remove(drop)
        gi = len(groups)
        for i in g:
            group_of[i] = gi
        groups.append(g)
    # a region that still fails (a single member with a box under 3 px) must join a neighbouring region; a
    # passing single-member region (a dropped member or an enclosed piece) joins one if the union passes
    # (up to a quarter above ``max_members``)
    for gi, g in enumerate(groups):
        if len(g) != 1 or not bx.ok(g, margin):
            continue
        near = sorted({group_of[j] for j in nb[g[0]] if group_of[j] != gi and cls.get(j) == cls.get(g[0])})
        for hj in near:
            if 1 < len(groups[hj]) < max_members + max_members // 4 and bx.ok(groups[hj] + g, margin):
                group_of[g[0]] = hj
                groups[hj] = groups[hj] + g
                groups[gi] = []
                break
    for gi, g in enumerate(groups):
        if not g or bx.ok(g, margin):
            continue
        near = sorted({group_of[j] for i in g for j in nb[i] if group_of[j] != gi and cls.get(j) == cls.get(g[0])})
        for hj in near:
            if groups[hj] and bx.ok(groups[hj] + g, margin):
                for i in g:
                    group_of[i] = hj
                groups[hj] = groups[hj] + g
                groups[gi] = []
                break
        else:
            raise KitError(f"cannot form a region around province {g[0]} whose mean lies inside a member box")
    out = [sorted(g) for g in groups if g]
    if keep_connected:
        split = [g[0] for g in out if not connected(g, nb)]
        if split:                         # cannot happen (growth, drops and merges keep pieces whole): fail loudly
            raise KitError(f"regions around provinces {split[:5]} are not one 4-connected piece")
    return out
