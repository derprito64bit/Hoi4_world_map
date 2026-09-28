"""Deterministic brick tiling of a mask into provinces (filler seas, off-globe lakes, padding)."""
from __future__ import annotations

import numpy as np
from scipy import ndimage

FOUR = [[0, 1, 0], [1, 1, 1], [0, 1, 0]]


def relabel_row_major(labels: np.ndarray) -> tuple:
    """Relabel 0..k-1 by the first pixel of each label in row-major order (-1 stays -1)."""
    flat = labels.ravel()
    sel = flat >= 0
    if not sel.any():
        return labels.copy(), 0
    vals = flat[sel]
    idx = np.nonzero(sel)[0]
    first = np.full(int(vals.max()) + 1, np.iinfo(np.int64).max, dtype=np.int64)
    np.minimum.at(first, vals, idx)
    present = np.nonzero(first < np.iinfo(np.int64).max)[0]
    order = present[np.argsort(first[present], kind="stable")]
    remap = np.full(len(first), -1, dtype=np.int64)
    remap[order] = np.arange(len(order))
    out = np.full(labels.shape, -1, dtype=np.int32)
    out.ravel()[idx] = remap[vals]
    return out, len(order)


def tile(mask: np.ndarray, cw: int, ch: int, brick: bool = True, row0: int = 0) -> tuple:
    """Cut ``mask`` into cells of cw x ch (every other band shifted by cw/2), one label per
    4-connected piece of a cell. Cells never cross the left/right image edge."""
    H, W = mask.shape
    rows = np.arange(H)[:, None]
    cols = np.arange(W)[None, :]
    band = (rows - row0) // ch
    off = np.where((band % 2 == 1) & brick, cw // 2, 0)
    cx = (cols + off) // cw
    ncx = W // cw + 3
    key = (band - band.min()) * ncx + cx
    key = np.where(mask, key, -1).astype(np.int64)
    comp = np.full(mask.shape, -1, dtype=np.int64)
    nxt = 0
    objs = ndimage.find_objects((key + 1).astype(np.int32))
    for k, sl in enumerate(objs):
        if sl is None:
            continue
        m = key[sl] == k
        lab, n = ndimage.label(m, structure=FOUR)
        sub = comp[sl]
        sub[m] = lab[m] - 1 + nxt
        nxt += n
    return relabel_row_major(comp)


def merge_small(labels: np.ndarray, min_px: int, max_rounds: int = 10) -> tuple:
    """Merge labels with fewer than ``min_px`` pixels into the neighbouring label sharing the
    longest border (neighbours are other labels >= 0; the wrap seam is ignored)."""
    labels = labels.astype(np.int64).copy()
    for _ in range(max_rounds):
        n = int(labels.max()) + 1
        area = np.bincount(labels[labels >= 0].ravel(), minlength=n)
        small = [i for i in range(n) if 0 < area[i] < min_px]
        if not small:
            break
        objs = ndimage.find_objects((labels + 1).astype(np.int32))
        changed = False
        for i in small:
            sl = objs[i]
            if sl is None:
                continue
            r0, r1 = max(0, sl[0].start - 1), min(labels.shape[0], sl[0].stop + 1)
            c0, c1 = max(0, sl[1].start - 1), min(labels.shape[1], sl[1].stop + 1)
            win = labels[r0:r1, c0:c1]
            m = win == i
            ring = ndimage.binary_dilation(m, structure=FOUR) & ~m
            cand = win[ring]
            cand = cand[cand >= 0]
            if cand.size:
                win[m] = int(np.bincount(cand).argmax())
                changed = True
        if not changed:
            break
    return relabel_row_major(labels)
