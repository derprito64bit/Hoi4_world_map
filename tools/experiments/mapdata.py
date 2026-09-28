"""Province-map primitives shared by the experiments (pure functions on numpy arrays / text).

Conventions: ``pid`` is an (H, W) int32 array of province IDs, row 0 = north.
The map wraps horizontally (column W-1 touches column 0). Type codes: 0 land,
1 sea, 2 lake. Game coordinates (buildings.txt, unitstacks.txt, weatherpositions)
use x = column + 0.5 and z = H - row - 0.5, the same pixel-centre convention as
``ee_project.Canvas.to_game_xz`` (z counted from the bottom); vanilla 1.19.3
positions map back to their province with row = H - 1 - floor(z) (97 % of
unitstacks lines, the rest sit on borders).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from .common import KitError

LAND, SEA, LAKE = 0, 1, 2
TYPE_CODE = {"land": LAND, "sea": SEA, "lake": LAKE}
TYPE_NAME = {v: k for k, v in TYPE_CODE.items()}


# ------------------------------------------------------------------ definition.csv
@dataclass
class Definition:
    rows: list            # list[list[str]] with 8+ fields; rows[i][0] == str(i)
    trailing_newline: bool

    @classmethod
    def parse(cls, text: str) -> "Definition":
        lines = text.split("\n")
        trailing = text.endswith("\n")
        if trailing:
            lines = lines[:-1]
        rows = [ln.rstrip("\r").split(";") for ln in lines if ln.strip()]
        for i, r in enumerate(rows):
            if len(r) < 8 or r[0] != str(i):
                raise KitError(f"definition.csv row {i} malformed or out of sequence: {';'.join(r)}")
        return cls(rows=rows, trailing_newline=trailing)

    def format(self) -> str:
        s = "\n".join(";".join(r) for r in self.rows)
        return s + ("\n" if self.trailing_newline else "")

    def copy(self) -> "Definition":
        return Definition(rows=[list(r) for r in self.rows], trailing_newline=self.trailing_newline)

    @property
    def n(self) -> int:
        """Number of rows including the dummy row 0 (= max id + 1)."""
        return len(self.rows)

    def colors(self) -> np.ndarray:
        return np.array([[int(r[1]), int(r[2]), int(r[3])] for r in self.rows], dtype=np.uint8)

    def types(self) -> np.ndarray:
        t = np.array([TYPE_CODE.get(r[4], -1) for r in self.rows], dtype=np.int8)
        t[0] = -1
        return t

    def coastal(self) -> np.ndarray:
        return np.array([r[5] == "true" for r in self.rows], dtype=bool)


def color_keys(colors: np.ndarray) -> np.ndarray:
    c = colors.astype(np.int64)
    return (c[:, 0] << 16) | (c[:, 1] << 8) | c[:, 2]


def pid_from_rgb(rgb: np.ndarray, colors: np.ndarray) -> np.ndarray:
    """(H, W, 3) RGB -> (H, W) province IDs using definition colours; unknown colour -> error."""
    lut = np.full(1 << 24, -1, dtype=np.int32)
    keys = color_keys(colors)
    lut[keys[1:]] = np.arange(1, len(colors), dtype=np.int32)
    p = rgb.astype(np.int32)
    pid = lut[(p[..., 0] << 16) | (p[..., 1] << 8) | p[..., 2]]
    if (pid < 0).any():
        raise KitError(f"{int((pid < 0).sum())} pixels have a colour without a definition row")
    return pid


def rgb_from_pid(pid: np.ndarray, colors: np.ndarray) -> np.ndarray:
    return colors[pid]


def new_colors(existing: np.ndarray, count: int, seed: int) -> np.ndarray:
    """``count`` unique RGB colours not in ``existing`` and not black; deterministic for a seed."""
    used = set(color_keys(existing).tolist()) | {0}
    rng = np.random.default_rng(seed)
    out = []
    while len(out) < count:
        cand = rng.integers(0, 1 << 24, size=max(64, 2 * (count - len(out))), dtype=np.int64)
        for k in cand.tolist():
            if k not in used:
                used.add(k)
                out.append(k)
                if len(out) == count:
                    break
    k = np.array(out, dtype=np.int64).reshape(-1)
    return np.stack([(k >> 16) & 255, (k >> 8) & 255, k & 255], 1).astype(np.uint8)


# ------------------------------------------------------------------ raster analysis
def areas(pid: np.ndarray, n: int) -> np.ndarray:
    return np.bincount(pid.ravel(), minlength=n)


def bboxes(pid: np.ndarray, n: int):
    """(xmin, xmax, ymin, ymax) per ID, no wrap handling (callers keep provinces off the seam)."""
    H, W = pid.shape
    flat = pid.ravel()
    ys, xs = np.divmod(np.arange(flat.size), W)
    xmin = np.full(n, W); xmax = np.full(n, -1); ymin = np.full(n, H); ymax = np.full(n, -1)
    np.minimum.at(xmin, flat, xs); np.maximum.at(xmax, flat, xs)
    np.minimum.at(ymin, flat, ys); np.maximum.at(ymax, flat, ys)
    return xmin, xmax, ymin, ymax


def neighbours_4(mask: np.ndarray) -> np.ndarray:
    """Pixels 4-adjacent to mask (horizontal wrap), like validate_map.py."""
    o = np.zeros_like(mask)
    o[1:] |= mask[:-1]
    o[:-1] |= mask[1:]
    o[:, 1:] |= mask[:, :-1]
    o[:, :-1] |= mask[:, 1:]
    o[:, 0] |= mask[:, -1]
    o[:, -1] |= mask[:, 0]
    return o


def coastal_flags(pid: np.ndarray, types: np.ndarray) -> np.ndarray:
    """bool per ID: land touching sea, or sea touching land (lakes: False; caller keeps vanilla lake flags)."""
    t = types[pid]
    land, sea = t == LAND, t == SEA
    out = np.zeros(len(types), dtype=bool)
    out[np.unique(pid[land & neighbours_4(sea)])] = True
    out[np.unique(pid[sea & neighbours_4(land)])] = True
    return out


def adjacency_pairs(pid: np.ndarray) -> np.ndarray:
    """Sorted unique (a, b) pairs with a < b of 4-adjacent different IDs (horizontal wrap)."""
    pw = np.concatenate([pid, pid[:, :1]], axis=1)
    a = np.concatenate([pw[:, :-1].ravel(), pid[:-1].ravel()]).astype(np.int64)
    b = np.concatenate([pw[:, 1:].ravel(), pid[1:].ravel()]).astype(np.int64)
    m = a != b
    lo, hi = np.minimum(a[m], b[m]), np.maximum(a[m], b[m])
    k = np.unique(lo * (1 << 32) + hi)
    return np.stack([k >> 32, k & 0xFFFFFFFF], 1)


def pair_set(pairs: np.ndarray) -> set:
    return set(map(tuple, pairs.tolist()))


def adjacency_links(text: str) -> set:
    """(a, b) pairs (a < b) that adjacencies.csv connects (every row except type 'impassable')."""
    out = set()
    for ln in text.splitlines()[1:]:
        s = ln.split(";")
        if len(s) < 4 or not s[0].strip().lstrip("-").isdigit() or s[0].strip() == "-1":
            continue
        if s[2].strip() == "impassable":
            continue
        a, b = int(s[0]), int(s[1])
        out.add((min(a, b), max(a, b)))
    return out


def x_crossings(pid: np.ndarray):
    """(rows, cols) of the top-left pixel of every 2x2 block with four distinct IDs (wrap included)."""
    pw = np.concatenate([pid, pid[:, :1]], axis=1)
    a, b, c, d = pw[:-1, :-1], pw[:-1, 1:], pw[1:, :-1], pw[1:, 1:]
    x = (a != b) & (a != c) & (a != d) & (b != c) & (b != d) & (c != d)
    return np.nonzero(x)


def x_crossings_window(pid: np.ndarray, r0: int, r1: int, c0: int, c1: int):
    """X-crossings whose 2x2 block lies within rows r0..r1-1, cols c0..c1-1 (no wrap)."""
    sub = pid[max(0, r0):r1, max(0, c0):c1]
    a, b, c, d = sub[:-1, :-1], sub[:-1, 1:], sub[1:, :-1], sub[1:, 1:]
    x = (a != b) & (a != c) & (a != d) & (b != c) & (b != d) & (c != d)
    ys, xs = np.nonzero(x)
    return ys + max(0, r0), xs + max(0, c0)


def fix_x_crossings(pid: np.ndarray, can_take, max_rounds: int = 20) -> int:
    """Remove X-crossings in place by giving one pixel of the 2x2 block the ID of a block neighbour.

    ``can_take(src_id, dst_id) -> bool`` says whether a pixel of ``src_id`` may
    become ``dst_id`` (e.g. only between siblings of one split province, or only
    between filler provinces). Edge neighbours are preferred over the diagonal.
    Returns the number of pixels changed; raises if a crossing cannot be fixed.
    """
    H, W = pid.shape
    changed = 0
    order = [(0, 1), (0, 2), (1, 0), (1, 3), (2, 0), (2, 3), (3, 1), (3, 2), (0, 3), (3, 0), (1, 2), (2, 1)]
    seam_order = [(0, 2), (2, 0), (1, 3), (3, 1)]      # never hand a pixel across the wrap seam
    for _ in range(max_rounds):
        ys, xs = x_crossings(pid)
        if len(ys) == 0:
            return changed
        for y, x in zip(ys.tolist(), xs.tolist()):
            cells = [(y, x), (y, (x + 1) % W), (y + 1, x), (y + 1, (x + 1) % W)]
            ids = [int(pid[c]) for c in cells]
            if len(set(ids)) < 4:
                continue
            for i, j in (seam_order if x == W - 1 else order):
                if can_take(ids[i], ids[j]):
                    pid[cells[i]] = ids[j]
                    changed += 1
                    break
            else:
                raise KitError(f"cannot fix X-crossing at col {x}, row {y}: IDs {ids}")
    if len(x_crossings(pid)[0]):
        raise KitError("X-crossings remain after the repair rounds")
    return changed


def interior_points(pid: np.ndarray, ids=None):
    """{id: (row, col)} of the pixel farthest from the province's border (ties: smallest row, col).

    Wrap is ignored for the distance (provinces never straddle the seam here).
    """
    H, W = pid.shape
    border = np.zeros(pid.shape, dtype=bool)
    border[1:] |= pid[1:] != pid[:-1]
    border[:-1] |= pid[:-1] != pid[1:]
    border[:, 1:] |= pid[:, 1:] != pid[:, :-1]
    border[:, :-1] |= pid[:, :-1] != pid[:, 1:]
    border[0, :] = border[-1, :] = True
    dist = ndimage.distance_transform_edt(~border)
    flat_id = pid.ravel()
    sel = np.arange(flat_id.size)
    if ids is not None:
        want = np.zeros(int(pid.max()) + 1, dtype=bool)
        want[np.asarray(list(ids), dtype=np.int64)] = True
        sel = sel[want[flat_id]]
    # sort by id asc, distance desc, index asc -> first entry per id wins
    order = np.lexsort((sel, -dist.ravel()[sel], flat_id[sel]))
    s = sel[order]
    sid = flat_id[s]
    first = np.r_[True, sid[1:] != sid[:-1]]
    rows, cols = np.divmod(s[first], W)
    return {int(i): (int(r), int(c)) for i, r, c in zip(sid[first], rows, cols)}


def coast_points(pid: np.ndarray, types: np.ndarray, ids, near: dict):
    """{land id: (row, col, sea id)}: a pixel of the province 4-adjacent to sea, nearest to ``near[id]``."""
    H, W = pid.shape
    t = types[pid]
    want = np.zeros(len(types), dtype=bool)
    want[np.asarray(sorted(ids), dtype=np.int64)] = True
    cand = want[pid] & (t == LAND)
    best: dict = {}
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nb = np.roll(pid, (-dr, -dc), axis=(0, 1))
        ok = cand & (types[nb] == SEA)
        if dr == -1:
            ok[0, :] = False
        if dr == 1:
            ok[-1, :] = False
        rs, cs = np.nonzero(ok)
        for r, c in zip(rs.tolist(), cs.tolist()):
            i = int(pid[r, c])
            nr, nc = near[i]
            d = (r - nr) ** 2 + (c - nc) ** 2
            key = (d, r, c, dr, dc)
            if i not in best or key < best[i][0]:
                best[i] = (key, (r, c, int(nb[r, c])))
    return {i: v[1] for i, v in best.items()}


def components(mask: np.ndarray):
    lab, n = ndimage.label(mask, structure=[[0, 1, 0], [1, 1, 1], [0, 1, 0]])
    return lab, n


# ------------------------------------------------------------------ coordinates
def game_xz(row: float, col: float, H: int):
    return col + 0.5, H - row - 0.5


def game_to_pixel(x: float, z: float, H: int):
    return int(np.floor(x)), H - 1 - int(np.floor(z))


def height_at(heightmap: np.ndarray, row: int, col: int) -> float:
    return max(float(heightmap[row, col]) / 10.0, 9.5)


# ------------------------------------------------------------------ Clausewitz text blocks
def _scan(text: str):
    """Yield (index, char) for structural characters outside comments and strings."""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "#":
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if ch == '"':
            j = text.find('"', i + 1)
            i = n if j < 0 else j + 1
            continue
        if ch in "{}=":
            yield i, ch
        i += 1


def find_block(text: str, key: str, depth: int = 1):
    """(open, close) indices of the braces of ``key = { ... }`` at the given brace depth."""
    d = 0
    toks = list(_scan(text))
    for k, (i, ch) in enumerate(toks):
        if ch == "{":
            d += 1
        elif ch == "}":
            d -= 1
        elif ch == "=" and d == depth and k + 1 < len(toks) and toks[k + 1][1] == "{":
            m = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*$", text[:i])
            if m and m.group(1) == key and text[i + 1:toks[k + 1][0]].strip() == "":
                open_i = toks[k + 1][0]
                dd = 0
                for i2, ch2 in toks[k + 1:]:
                    dd += 1 if ch2 == "{" else -1 if ch2 == "}" else 0
                    if dd == 0:
                        return open_i, i2
                raise KitError(f"unbalanced braces after '{key}'")
    raise KitError(f"no '{key} = {{ }}' block at depth {depth}")


def block_ids(text: str, key: str, depth: int = 1) -> list:
    o, c = find_block(text, key, depth)
    body = re.sub(r"#[^\n]*", "", text[o + 1:c])
    return [int(t) for t in body.split()]


def append_ids(text: str, key: str, ids, depth: int = 1) -> str:
    """Append IDs to the end of ``key = { ... }`` keeping the original layout."""
    if not ids:
        return text
    o, c = find_block(text, key, depth)
    body = text[o + 1:c]
    core = body.rstrip()
    trail = body[len(core):]
    sep = "" if core == "" or core.endswith((" ", "\t")) else " "
    new = core + sep + " ".join(str(i) for i in ids) + (trail if trail else " ")
    return text[:o + 1] + new + text[c:]
