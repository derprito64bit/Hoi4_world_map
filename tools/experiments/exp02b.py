"""EXP-02b: larger province-size variants of EXP-02 (owner request after EXP-02-300/600/1200 loaded).

Three builds, each changing one property against vanilla 1.19.3:

* ``EXP-02b-strip-full`` -- the EXP-02 strip method (``exp02.widen``) pushed to the
  widest span the map allows: the sea strip runs through the all-sea rows at the
  southern map edge and is ``STRIP_WIDTH[SEA]`` px wide (the map is 5,632 px; the
  strip stops short of the wrap seam, so the game and the validator measure the
  same box). A land strip may only run through land, so land is capped by the
  widest all-land run on the map (northern Eurasia), ``STRIP_WIDTH[LAND]`` px.
  The EXP-02 rules apply, with one difference: the only all-sea rows hold unit
  and weather positions, so positions on strip pixels are relocated into their
  own province (as in the block builds) instead of being avoided. Widths were
  found with ``widest_strip`` (5,629 px, the non-seam maximum, has no valid host).
* ``EXP-02b-block-400`` / ``-800`` -- one land and one sea province become a
  solid, filled square of 400 x 400 / 800 x 800 px. The host province lies inside
  the square; it takes over the pixels of every *eligible donor* inside the
  square (same kind, not protected, see ``protected_ids``). A donor that also
  extends outside the square keeps its outside part; a donor whose outside part
  is below ``REMNANT`` px keeps a compact ``REMNANT``-px remnant (grown from its
  outside part, or a small island around its interior point). No province
  disappears, no donor drops below 8 px, definitions, states and strategic
  regions are untouched. Protected provinces and other kinds (lakes inside a
  land block) stay intact inside the square.

Consistency rules (checked at build and again by ``--check``):

* the square and a 1-px ring around it hold no sea (land block) / only sea (sea
  block), so no coastal flag changes;
* protected = on a railway, a supply node, named in adjacencies.csv or
  adjacency_rules.txt, a naval base's sea province, and vanilla's 280-px
  province 7855; they keep every pixel, so railways, supply, straits and canals
  stay valid;
* buildings.txt / unitstacks.txt / weatherpositions.txt lines whose position
  lies on a re-assigned pixel are moved to a pixel of the same province (the
  donor's remnant; same state and region); only their x/y/z fields change;
* lost province contacts all involve a donor; new contacts all involve the host.

Side effects that follow from the property and are documented, not hidden: a
donor that lies wholly inside the square becomes a small enclave of the host,
so its state can become non-contiguous (``--check`` allows that only for states
that contain a donor) and its sea/land neighbours change.
"""
from __future__ import annotations

import re
from collections import deque
from pathlib import Path

import numpy as np
from scipy import ndimage

from . import texts
from .base import Expected, Experiment, check_descriptor, check_file_set
from .bmpio import read_bmp, write_bmp
from .common import KitError, decode, encode, fmt2, write_bytes
from .exp02 import MIN_PX, Exp02, strip_problems, widen
from .mapdata import (LAND, SEA, adjacency_ids, adjacency_links, adjacency_pairs, areas, bboxes, coastal_flags,
                      game_to_pixel, game_xz, height_at, interior_points, pid_from_rgb, rgb_from_pid, x_crossings,
                      x_crossings_window)
from .positions import join_lines, split_lines

PROV = "map/provinces.bmp"
POS_FILES = {"map/buildings.txt": (2, 3, 4), "map/unitstacks.txt": (2, 3, 4), "map/weatherpositions.txt": (1, 2, 3)}
KIND_NAME = {LAND: "land", SEA: "sea"}

# widest valid strips on vanilla 1.19.3 (search: ``widest_strip``); the build fails loudly if one no longer fits
STRIP_WIDTH = {SEA: 5625, LAND: 2188}
# block squares on vanilla 1.19.3: size -> kind -> (top row, left column, host province); search: ``find_sites``
# (land 400: Siberia, away from the map edge; land 800: the only non-sea 800-px square is in inner Eurasia and
# holds lakes and many railway provinces, which stay whole; sea 400: North Pacific; sea 800: South Pacific)
BLOCKS = {400: {LAND: (33, 4513, 1852), SEA: (257, 289, 2755)},
          800: {LAND: (113, 3785, 12686), SEA: (925, 473, 4497)}}
REMNANT = 9            # px a donor keeps when (almost) all of it lies inside the square (>= MIN_PX)
XFIX_SLACK = 4         # extra px per donor the X-crossing repair may leave inside the square
BBOX_BASELINE = 7855   # vanilla's own 280-px land province: never a donor or host


# ------------------------------------------------------------------ protected provinces
def protected_ids(v) -> set:
    """Provinces whose pixels must not move (see module doc)."""
    out = set(adjacency_ids(v.text("map/adjacencies.csv")))
    for ln in v.text("map/railways.txt").splitlines():
        s = ln.split()
        out |= {int(x) for x in s[2:]}
    for ln in v.text("map/supply_nodes.txt").splitlines():
        s = ln.split()
        if len(s) >= 2:
            out.add(int(s[1]))
    rules = re.sub(r"#[^\n]*", "", v.text("map/adjacency_rules.txt"))
    for m in re.finditer(r"required_provinces\s*=\s*\{([^}]*)\}", rules):
        out |= {int(x) for x in m.group(1).split()}
    for m in re.finditer(r"\bicon\s*=\s*(\d+)", rules):
        out.add(int(m.group(1)))
    for ln in v.text("map/buildings.txt").splitlines():
        s = ln.split(";")
        if len(s) >= 7 and s[1] == "naval_base_spawn":
            try:
                out.add(int(float(s[6])))
            except ValueError:
                pass
    out.add(BBOX_BASELINE)
    return out


# ------------------------------------------------------------------ square geometry
def ring_ok(tmap: np.ndarray, kind: int, r0: int, c0: int, n: int) -> bool:
    """Square plus 1-px ring: no sea for a land block, only sea for a sea block (never touching the map edge)."""
    H, W = tmap.shape
    if r0 < 1 or c0 < 1 or r0 + n + 1 > H or c0 + n + 1 > W:
        return False
    t = tmap[r0 - 1:r0 + n + 1, c0 - 1:c0 + n + 1]
    return bool((t != SEA).all()) if kind == LAND else bool((t == SEA).all())


def block_donors(pid: np.ndarray, types: np.ndarray, kind: int, host: int, r0: int, c0: int, n: int,
                 protected: set) -> list:
    """Sorted IDs allowed to shrink: every province of ``kind`` with pixels in the square, except host/protected."""
    ids = np.unique(pid[r0:r0 + n, c0:c0 + n]).tolist()
    return sorted(i for i in ids if types[i] == kind and i != host and i not in protected)


def _bfs(mask: np.ndarray, seeds, need: int):
    """First ``need`` pixels of a 4-neighbour BFS inside ``mask`` from ``seeds`` (deterministic order)."""
    seen = np.zeros(mask.shape, dtype=bool)
    q = deque()
    for s in seeds:
        if mask[s] and not seen[s]:
            seen[s] = True
            q.append(s)
    out = []
    while q and len(out) < need:
        r, c = q.popleft()
        out.append((r, c))
        for dr, dc in ((-1, 0), (0, -1), (0, 1), (1, 0)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < mask.shape[0] and 0 <= cc < mask.shape[1] and mask[rr, cc] and not seen[rr, cc]:
                seen[rr, cc] = True
                q.append((rr, cc))
    return out


def make_block(pid: np.ndarray, types: np.ndarray, kind: int, host: int, r0: int, c0: int, n: int,
               protected: set, keep: int = REMNANT):
    """Grow ``host`` into a filled n x n square at (r0, c0). Returns (new pid, info). Raises KitError if invalid."""
    H, W = pid.shape
    tmap = types[pid]
    if types[host] != kind:
        raise KitError(f"EXP-02b: host {host} is not {KIND_NAME[kind]}")
    if not ring_ok(tmap, kind, r0, c0, n):
        raise KitError(f"EXP-02b: square ({r0}, {c0}, {n}) or its ring is not all {KIND_NAME[kind]}")
    area = areas(pid, len(types))
    sub = pid[r0:r0 + n, c0:c0 + n]
    if int((sub == host).sum()) != int(area[host]):
        raise KitError(f"EXP-02b: host {host} is not wholly inside the square")
    donors = block_donors(pid, types, kind, host, r0, c0, n, protected)
    if not donors:
        raise KitError("EXP-02b: no donors in the square")
    dmask = np.zeros(len(types), dtype=bool)
    dmask[donors] = True
    take = dmask[sub].copy()
    kept = {}
    for d in donors:
        inside = sub == d
        n_in = int(inside.sum())
        n_out = int(area[d]) - n_in
        if n_out >= keep:
            kept[d] = 0
            continue
        need = keep - n_out
        if n_out > 0:
            outside = np.zeros((n + 2, n + 2), dtype=bool)
            outside[:] = pid[r0 - 1:r0 + n + 1, c0 - 1:c0 + n + 1] == d
            outside[1:-1, 1:-1] = False
            touch = ndimage.binary_dilation(outside, structure=[[0, 1, 0], [1, 1, 1], [0, 1, 0]])[1:-1, 1:-1] & inside
            seeds = list(zip(*[a.tolist() for a in np.nonzero(touch)]))
        else:
            dist = ndimage.distance_transform_edt(np.pad(inside, 1))[1:-1, 1:-1]
            seeds = [tuple(int(x) for x in np.unravel_index(int(np.argmax(dist)), dist.shape))]
        px = _bfs(inside, seeds, need)
        if len(px) < min(need, n_in):
            raise KitError(f"EXP-02b: donor {d} cannot keep {need} px inside the square")
        for r, c in px:
            take[r, c] = False
        kept[d] = len(px)
    out = pid.copy()
    win = out[r0:r0 + n, c0:c0 + n]
    win[take] = host
    flips = fix_block_crossings(out, pid, host, dmask, r0, c0, n)
    info = {"kind": KIND_NAME[kind], "host": int(host), "r0": r0, "c0": c0, "size": n, "donors": donors,
            "remnant_inside": {int(k): int(v) for k, v in kept.items() if v}, "xfix": flips,
            "fill": round(float((out[r0:r0 + n, c0:c0 + n] == host).mean()), 4)}
    return out, info


def fix_block_crossings(out: np.ndarray, orig: np.ndarray, host: int, dmask: np.ndarray, r0: int, c0: int, n: int,
                        rounds: int = 50) -> int:
    """Remove X-crossings around the square in place; a pixel may only switch between host and its original donor."""
    flips = 0
    for _ in range(rounds):
        ys, xs = x_crossings_window(out, r0 - 2, r0 + n + 2, c0 - 2, c0 + n + 2)
        if len(ys) == 0:
            return flips
        for y, x in zip(ys.tolist(), xs.tolist()):
            cells = [(y, x), (y, x + 1), (y + 1, x), (y + 1, x + 1)]
            ids = [int(out[c]) for c in cells]
            if len(set(ids)) < 4:
                continue
            for k, cell in enumerate(cells):
                r, c = cell
                if not (r0 <= r < r0 + n and c0 <= c < c0 + n and dmask[orig[cell]]):
                    continue
                alt = int(orig[cell]) if ids[k] == host else host
                if alt in ids[:k] + ids[k + 1:]:
                    out[cell] = alt
                    flips += 1
                    break
            else:
                raise KitError(f"EXP-02b: cannot fix X-crossing at row {y}, col {x}: IDs {ids}")
    raise KitError("EXP-02b: X-crossings remain after the repair rounds")


# ------------------------------------------------------------------ positions
def _pos(line: str, cols, H: int, W: int):
    s = line.split(";")
    try:
        c, r = game_to_pixel(float(s[cols[0]]), float(s[cols[2]]), H)
    except (ValueError, IndexError):
        return None
    return min(max(r, 0), H - 1), c % W


def position_owner(rel: str, line: str, van: np.ndarray, px) -> int:
    """Province a position line belongs to: unitstacks name it in column 0; the others by their vanilla pixel."""
    if rel == "map/unitstacks.txt":
        return int(line.split(";")[0])
    return int(van[px])


def relocate_positions(v, van: np.ndarray, got: np.ndarray) -> tuple:
    """({rel: new text} for files with moved lines, {rel: moved line count}). Moved lines go to a remnant pixel."""
    H, W = van.shape
    diff = got != van
    hm = v.heightmap
    plan = {}
    targets = set()
    for rel, cols in sorted(POS_FILES.items()):
        lines, trailing = split_lines(v.text(rel))
        moved = []
        for i, ln in enumerate(lines):
            px = _pos(ln, cols, H, W)
            if px is not None and diff[px]:
                p = position_owner(rel, ln, van, px)
                moved.append((i, p))
                targets.add(p)
        plan[rel] = (lines, trailing, moved)
    anchor = interior_points(got, targets) if targets else {}
    out, counts = {}, {}
    for rel, (lines, trailing, moved) in plan.items():
        if not moved:
            continue
        cols = POS_FILES[rel]
        lines = list(lines)
        for i, p in moved:
            if p not in anchor:
                raise KitError(f"EXP-02b: {rel} line {i + 1}: province {p} has no pixel left")
            r, c = anchor[p]
            x, z = game_xz(r, c, H)
            s = lines[i].split(";")
            s[cols[0]], s[cols[1]], s[cols[2]] = fmt2(x), fmt2(height_at(hm, r, c)), fmt2(z)
            lines[i] = ";".join(s)
        out[rel] = join_lines(lines, trailing)
        counts[rel] = len(moved)
    return out, counts


def position_problems(v, van: np.ndarray, got: np.ndarray, rel: str, text: str | None) -> list:
    """A position file is vanilla except lines on re-assigned pixels, which moved (x/y/z only) into their province."""
    H, W = van.shape
    cols = POS_FILES[rel]
    diff = got != van
    a, _ = split_lines(v.text(rel))
    b, _ = split_lines(text) if text is not None else (a, None)
    if len(a) != len(b):
        return [f"{rel}: {len(b)} lines, vanilla has {len(a)}"]
    probs = []
    for i, (la, lb) in enumerate(zip(a, b)):
        px = _pos(la, cols, H, W)
        on_moved = px is not None and bool(diff[px])
        if la == lb:
            if on_moved:
                probs.append(f"{rel} line {i + 1}: position lies on a re-assigned pixel and was not moved")
            continue
        if not on_moved:
            probs.append(f"{rel} line {i + 1}: changed although its position was not re-assigned")
            continue
        sa, sb = la.split(";"), lb.split(";")
        if len(sa) != len(sb) or any(sa[k] != sb[k] for k in range(len(sa)) if k not in cols):
            probs.append(f"{rel} line {i + 1}: fields other than x/y/z changed")
            continue
        q = _pos(lb, cols, H, W)
        want = position_owner(rel, la, van, px)
        if q is None or int(got[q]) != want or diff[q]:
            probs.append(f"{rel} line {i + 1}: moved position is not on an unchanged pixel of province {want}")
    return probs


# ------------------------------------------------------------------ states
def noncontiguous_states(pid: np.ndarray, types: np.ndarray, province_state: dict, links: set) -> set:
    """State IDs whose land provinces are not connected (pixel contacts + adjacencies.csv), as validate_map.py."""
    by_state = {}
    for p, (sid, _) in province_state.items():
        if 0 < p < len(types) and types[p] == LAND:
            by_state.setdefault(sid, []).append(p)
    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    sid_of = {p: s for s, ps in by_state.items() for p in ps}
    for p in sid_of:
        parent[p] = p
    pairs = [tuple(x) for x in adjacency_pairs(pid).tolist()] + sorted(links)
    for a, b in pairs:
        if a in sid_of and b in sid_of and sid_of[a] == sid_of[b]:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    return {s for s, ps in by_state.items() if len({find(p) for p in ps}) > 1}


def rail_gaps(text: str, pairs: set) -> list:
    out = []
    for n, ln in enumerate(text.splitlines(), 1):
        s = [int(z) for z in ln.split()]
        for u, w in zip(s[2:], s[3:]):
            if (min(u, w), max(u, w)) not in pairs:
                out.append((n, u, w))
    return out


# ------------------------------------------------------------------ block rules on a finished map
def block_problems(v, van: np.ndarray, got: np.ndarray, size: int, protected: set) -> list:
    """Every rule of a block build, on the finished province map (positions are checked separately)."""
    probs = []
    types = v.types
    n = len(types)
    spec = BLOCKS[size]
    diff = got != van
    allowed_px = np.zeros(van.shape, dtype=bool)
    hosts = {}
    for kind, (r0, c0, host) in sorted(spec.items()):
        hosts[kind] = host
        donors = block_donors(van, types, kind, host, r0, c0, size, protected)
        dm = np.zeros(n, dtype=bool)
        dm[donors] = True
        win = np.zeros(van.shape, dtype=bool)
        win[r0:r0 + size, c0:c0 + size] = True
        allowed_px |= win & dm[van]
        if not ring_ok(types[van], kind, r0, c0, size):
            probs.append(f"{KIND_NAME[kind]} square or its ring holds the wrong kind of province")
        bb = bboxes(got, n)
        box = (int(bb[0][host]), int(bb[1][host]), int(bb[2][host]), int(bb[3][host]))
        if box != (c0, c0 + size - 1, r0, r0 + size - 1):
            probs.append(f"{KIND_NAME[kind]} host {host}: bounding box {box}, expected the {size}-px square "
                         f"{(c0, c0 + size - 1, r0, r0 + size - 1)}")
        if (diff & win & (got != host)).any():
            probs.append(f"{KIND_NAME[kind]} square: re-assigned pixels that did not go to host {host}")
        a_van = areas(van, n)
        in_sq = np.bincount(van[r0:r0 + size, c0:c0 + size].ravel(), minlength=n)
        left = np.bincount(got[r0:r0 + size, c0:c0 + size].ravel(), minlength=n)
        for d in donors:
            cap = max(0, REMNANT - int(a_van[d] - in_sq[d])) + XFIX_SLACK
            if left[d] > cap:
                probs.append(f"donor {d} keeps {int(left[d])} px inside the square (at most {cap}): block not filled")
    if (diff & ~allowed_px).any():
        bad = sorted(set(van[diff & ~allowed_px].tolist()))
        probs.append(f"pixels changed outside the allowed donors of the squares: provinces {bad[:10]}")
    if (types[van[diff]] != types[got[diff]]).any():
        probs.append("a re-assignment changed the type (land/sea/lake) of some pixels")
    if not set(got[diff].tolist()) <= set(hosts.values()):
        probs.append("changed pixels belong to a province other than the two hosts")
    a = areas(got, n)
    if (a[1:] < MIN_PX).any():
        probs.append(f"provinces below {MIN_PX} px: {(np.nonzero(a[1:] < MIN_PX)[0][:10] + 1).tolist()}")
    if len(x_crossings(got)[0]):
        probs.append("X-crossings present")
    if (coastal_flags(van, types) != coastal_flags(got, types)).any():
        probs.append("coastal flags would change (definition.csv would be stale)")
    before = {tuple(x) for x in adjacency_pairs(van).tolist()}
    after = {tuple(x) for x in adjacency_pairs(got).tolist()}
    shrunk = set(np.unique(van[diff]).tolist())
    lost = [p for p in before - after if not set(p) & shrunk]
    if lost:
        probs.append(f"contacts lost between provinces that are not donors: {sorted(lost)[:5]}")
    stray = [p for p in after - before if not set(p) & set(hosts.values())]
    if stray:
        probs.append(f"new contacts that do not involve a host: {sorted(stray)[:5]}")
    links = adjacency_links(v.text("map/adjacencies.csv"))
    gaps = rail_gaps(v.text("map/railways.txt"), after | links)
    if gaps:
        probs.append(f"railway steps no longer adjacent: {gaps[:5]}")
    if shrunk & protected:
        probs.append(f"protected provinces lost pixels: {sorted(shrunk & protected)[:10]}")
    donor_states = {v.province_state[p][0] for p in shrunk if p in v.province_state}
    nc0 = noncontiguous_states(van, types, v.province_state, links)
    nc1 = noncontiguous_states(got, types, v.province_state, links)
    if nc0 - nc1:
        probs.append(f"states became contiguous (unexpected): {sorted(nc0 - nc1)[:10]}")
    if nc1 - nc0 - donor_states:
        probs.append(f"states without a donor became non-contiguous: {sorted(nc1 - nc0 - donor_states)[:10]}")
    return probs


# ------------------------------------------------------------------ search helpers (used to choose the constants)
def rows_with_run(tmap: np.ndarray, kind: int, length: int) -> list:
    """Rows whose 3-row band holds a run of ``kind`` of at least ``length`` + 4 columns (EXP-02 strip candidates)."""
    H = tmap.shape[0]
    out = []
    for r in range(2, H - 2):
        ok = (tmap[r - 1] == kind) & (tmap[r] == kind) & (tmap[r + 1] == kind)
        d = np.diff(np.r_[0, ok.astype(np.int8), 0])
        s, e = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
        if len(s) and int((e - s).max()) >= length + 4:
            out.append(r)
    return out


def strip(v, kind: int, width: int, pid: np.ndarray | None = None):
    """The EXP-02 strip of ``width`` px for ``kind`` (rows restricted to those with a long enough run).

    Unlike EXP-02, position pixels are not avoided: the only all-sea rows (southern map edge) hold unit and
    weather positions, so lines on strip pixels are moved into their province instead (``relocate_positions``).
    """
    pid = np.asarray(v.pid) if pid is None else pid
    rows = rows_with_run(v.types[pid], kind, width)
    free = np.zeros(pid.shape, dtype=bool)
    return widen(pid, v.types, free, kind, width, rows=rows, avoid={BBOX_BASELINE}, step=1)


def widest_strip(v, kind: int, start: int, stop: int, step: int = -1) -> int:
    """First width in range(start, stop, step) for which a valid strip exists (0 if none)."""
    for w in range(start, stop, step):
        try:
            strip(v, kind, w)
            return w
        except KitError:
            continue
    return 0


def find_sites(v, kind: int, n: int, step: int = 16, protected: set | None = None, limit: int = 10) -> list:
    """Candidate squares, best first: (new non-contiguous states estimate, protected px, fully-inside donors, r0, c0, host)."""
    pid = np.asarray(v.pid)
    types = v.types
    tmap = types[pid]
    H, W = pid.shape
    protected = protected_ids(v) if protected is None else protected
    bad = (tmap == SEA) if kind == LAND else (tmap != SEA)
    ii = np.pad(bad.astype(np.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    area = areas(pid, len(types))
    sid = np.zeros(len(types), dtype=np.int64)
    for p, (s, _) in v.province_state.items():
        sid[p] = s
    nprov = np.bincount(sid[sid > 0])
    res = []
    for r0 in range(1, H - n - 1, step):
        for c0 in range(1, W - n - 1, step):
            rr, cc = r0 - 1, c0 - 1
            if ii[rr + n + 2, cc + n + 2] - ii[rr, cc + n + 2] - ii[rr + n + 2, cc] + ii[rr, cc]:
                continue
            ids, cnt = np.unique(pid[r0:r0 + n, c0:c0 + n], return_counts=True)
            full = {int(i) for i, c in zip(ids, cnt) if c == area[i]}
            hosts = [i for i in full if types[i] == kind and i not in (BBOX_BASELINE,)]
            if not hosts:
                continue
            inside_all = [int(i) for i in full if types[i] == kind and i not in protected]
            # host: the fully-inside province whose state owns most fully-inside donors (fewest cut-off states)
            host = max(hosts, key=lambda h: (sum(1 for d in inside_all if sid[d] == sid[h]), int(area[h]), -h))
            prot_px = int(sum(c for i, c in zip(ids, cnt) if i in protected or types[i] != kind))
            donors = [int(i) for i in ids if types[i] == kind and i not in protected and i != host]
            inside = [d for d in donors if d in full]
            split = len([d for d in inside if kind == LAND and sid[d] != sid[host] and nprov[sid[d]] > 1])
            res.append((split, prot_px, len(inside), r0, c0, host))
    res.sort()
    return res[:limit]


# ------------------------------------------------------------------ experiment
class Exp02b(Experiment):
    exp_id = "EXP-02b"
    title = "larger province-size variants"
    priority = 2

    def build_ids(self, ctx):
        return ["EXP-02b-strip-full"] + [f"EXP-02b-block-{s}" for s in sorted(BLOCKS)]

    def size(self, build_id):
        return None if build_id.endswith("strip-full") else int(build_id.split("-")[-1])

    def title_for(self, build_id):
        s = self.size(build_id)
        if s is None:
            return f"one sea province {STRIP_WIDTH[SEA]} px and one land province {STRIP_WIDTH[LAND]} px wide (strips)"
        return f"one land + one sea province filled {s}x{s} px"

    def expected(self, build_id):
        s = self.size(build_id)
        if s is None:
            what = (f"WARN BBOX_LARGE now lists the two test provinces (sea {STRIP_WIDTH[SEA]} px, land "
                    f"{STRIP_WIDTH[LAND]} px) besides vanilla's 7855 (280 px); that is the property under test.")
        else:
            what = (f"WARN BBOX_LARGE now lists the two test provinces ({s} px) besides vanilla's 7855 (280 px); that "
                    "is the property under test. WARN STATE_NONCONTIGUOUS lists more states than vanilla's 30: "
                    "states of donor provinces that now sit as small remnants inside the block (a consequence of "
                    "keeping every donor alive, see the README).")
        return Expected(text=what + " Everything else as the vanilla baseline (0 ERROR, no PROVINCE_TOO_SMALL; WARN "
                                    "DEF_SEA_CONTINENT, STATE_NONCONTIGUOUS, RIVERS_ON_SEA, RIVERS_THICK, "
                                    "STATE_CATEGORY_DUP).")

    # -------------------------------------------------------------- build
    def make_strips(self, v):
        pid1, land = strip(v, LAND, STRIP_WIDTH[LAND])
        pid2, sea = strip(v, SEA, STRIP_WIDTH[SEA], pid1)
        return pid2, land, sea

    def make_blocks(self, v, size):
        pid = np.asarray(v.pid)
        prot = protected_ids(v)
        infos = {}
        out = pid
        for kind in (LAND, SEA):
            r0, c0, host = BLOCKS[size][kind]
            out, infos[kind] = make_block(out, v.types, kind, host, r0, c0, size, prot)
        probs = block_problems(v, pid, out, size, prot)
        if probs:
            raise KitError("EXP-02b: block build breaks its own rules: " + "; ".join(probs[:5]))
        return out, infos

    def build(self, ctx, build_id, out: Path):
        v = ctx.vanilla
        colors = v.definition.colors()
        s = self.size(build_id)
        if s is None:
            pid, land, sea = self.make_strips(v)
            write_bytes(out, PROV, write_bmp(v.provinces_bmp, rgb_from_pid(pid, colors), keep_tail=True))
            files, moved = relocate_positions(v, np.asarray(v.pid), pid)
            for rel, text in sorted(files.items()):
                write_bytes(out, rel, encode(text))
            return {"land": land, "sea": sea, "moved": moved,
                    "land_where": v.province_state[land["host"]][1].rsplit(".", 1)[0],
                    "sea_where": v.province_region[sea["host"]][1].rsplit(".", 1)[0]}
        pid, infos = self.make_blocks(v, s)
        van = np.asarray(v.pid)
        write_bytes(out, PROV, write_bmp(v.provinces_bmp, rgb_from_pid(pid, colors), keep_tail=True))
        files, moved = relocate_positions(v, van, pid)
        for rel, text in sorted(files.items()):
            write_bytes(out, rel, encode(text))
        links = adjacency_links(v.text("map/adjacencies.csv"))
        nc = sorted(noncontiguous_states(pid, v.types, v.province_state, links)
                    - noncontiguous_states(van, v.types, v.province_state, links))
        land, sea = infos[LAND], infos[SEA]
        return {"land": land, "sea": sea, "moved": moved, "new_noncontiguous": nc,
                "land_where": v.province_state[land["host"]][1].rsplit(".", 1)[0],
                "sea_where": v.province_region[sea["host"]][1].rsplit(".", 1)[0]}

    # -------------------------------------------------------------- README
    def readme(self, ctx, build_id, info):
        s = self.size(build_id)
        L, S = info["land"], info["sea"]
        cannot = ["EXP-02"]
        extra = ["one filled province of this size is not a full map of them: it does not show what many such "
                 "provinces together (a whole ocean of large sea zones) do to loading, pathing or performance"]
        send = ["Did the game reach the main menu? Did a game start? (yes/no each)",
                "Loading time (roughly, in seconds).",
                f"Every error.log line that contains 'BOX', 'box', '{L['host']}' or '{S['host']}' (copy them exactly)."]
        moved = ", ".join(f"{k.split('/')[-1]} {v} lines" for k, v in sorted(info["moved"].items())) or "none"
        if s is None:
            prop = (f"map/provinces.bmp: sea province {S['host']} gets a 1-pixel-high strip {STRIP_WIDTH[SEA]} "
                    f"pixels wide (the map is 5632 px wide; the strip stops just short of the left/right wrap edge), "
                    f"and land province {L['host']} a strip {STRIP_WIDTH[LAND]} pixels wide. Land is narrower because "
                    f"a land strip may only run through land: {STRIP_WIDTH[LAND]} px is the widest valid land span on "
                    "the map (northern Eurasia). The strips borrow pixels from neighbouring provinces; no province "
                    "is removed, no state, coast or terrain changes. Unit, building and weather positions that stood "
                    f"on a strip pixel moved into their own province ({moved}); nothing else in those files changes.")
            why = ("EXP-02-300/600/1200 all loaded. This pushes the same thin-strip test to the largest box the map "
                   "allows, to see whether any width limit exists at all.")
            steps = ["If the main menu appears: start a new game with any country and let it run for 2-3 days.",
                     f"Optional: look at sea province {S['host']} (strategic region '{info['sea_where']}', row "
                     f"{S['row']} from the top, far south) and land province {L['host']} (state file "
                     f"'{info['land_where']}'); a thin 1-pixel line running east from each is expected."]
            notes = ["Control: EXP-02-1200 (1,200 px strips) loaded without a BOX line."]
            extra = ["a 1-pixel strip is not a filled province (EXP-02b-block-400/800 test that), and one very wide "
                     "province is not a full map of them: it does not show what many such provinces together do to "
                     "loading, pathing or performance"]
            return texts.readme(build_id, self.title_for(build_id), prop=prop, why=why, launch=texts.LAUNCH_NORMAL,
                                steps=steps, send=send, expected=self.expected(build_id).text, cannot=cannot,
                                cannot_extra=extra, user_dir=ctx.user, notes=notes)
        nc = info["new_noncontiguous"]
        prop = (f"map/provinces.bmp: land province {L['host']} and sea province {S['host']} each become a solid, "
                f"filled square of {s} x {s} pixels (vanilla's largest boxes are land 280 px and sea 179 px). They "
                f"take over the pixels of neighbouring provinces inside the square: {len(L['donors'])} land and "
                f"{len(S['donors'])} sea donor provinces. No province is removed: a donor that lay (almost) wholly inside "
                f"the square keeps a small remnant of at least {REMNANT} pixels, so it stays on the map with its state, region "
                f"and victory points. Land block filled {L['fill']:.1%}, sea block {S['fill']:.1%} (the rest are "
                "those remnants, lakes and provinces that must not move: railways, supply nodes, straits). "
                f"Building, unit and weather positions that stood on taken pixels moved into their own province's "
                f"remnant ({moved}); nothing else in those files changes.")
        why = ("EXP-02 only tested thin 1-pixel strips. This tests whether a large province that is actually filled "
               "loads, which is what open-ocean and off-map filler provinces would look like. It decides BBOX_MAX "
               "(today land 250 / sea 180 px).")
        steps = ["If the main menu appears: start a new game with any country and let it run for 2-3 days.",
                 f"Optional: look at land province {L['host']} (state file '{info['land_where']}') and sea province "
                 f"{S['host']} (strategic region '{info['sea_where']}'): each should be one big square with small "
                 "enclaves (the donor remnants, a few pixels each) in it."]
        notes = [f"Side effect, on purpose: {len(nc)} states now have a small remnant province cut off from the rest "
                 f"of the state (states {', '.join(str(x) for x in nc[:40])}{' ...' if len(nc) > 40 else ''}). The "
                 "normal game already has 30 such states; if something about these states looks odd in-game, "
                 "report it, but it is not the thing under test.",
                 "Side effect, on purpose: the donor remnants are enclaves inside the host, so their neighbours "
                 "changed (a remnant sea zone can only be reached through the big sea zone). Pathing near the "
                 "blocks is not under test.",
                 "Test block-400 before block-800. If block-400 fails and EXP-02-1200 loaded, say so: the filled "
                 "area (not the width) would then matter."]
        return texts.readme(build_id, self.title_for(build_id), prop=prop, why=why, launch=texts.LAUNCH_NORMAL,
                            steps=steps, send=send, expected=self.expected(build_id).text, cannot=cannot,
                            cannot_extra=extra, user_dir=ctx.user, notes=notes)

    # -------------------------------------------------------------- check
    def check(self, ctx, build_id, out):
        v = ctx.vanilla
        s = self.size(build_id)
        van = np.asarray(v.pid)
        present = {rel for rel in POS_FILES if (out / rel).is_file()}
        probs = check_file_set(out, {PROV} | present)
        probs += check_descriptor(self, build_id, out)
        p = out / PROV
        if not p.is_file():
            return probs
        try:
            got = pid_from_rgb(read_bmp(p.read_bytes()).pixels, v.definition.colors())
        except KitError as e:
            return probs + [f"provinces.bmp: {e}"]
        if s is None:        # positions on strip pixels are relocated, so the position mask is empty here
            probs += strip_problems(v, van, got, STRIP_WIDTH, np.zeros(van.shape, dtype=bool))
        else:
            probs += block_problems(v, van, got, s, protected_ids(v))
        for rel in sorted(POS_FILES):
            text = decode((out / rel).read_bytes()) if rel in present else None
            if text is not None and text == v.text(rel):
                probs.append(f"{rel} is present but identical to vanilla")
            probs += position_problems(v, van, got, rel, text)[:5]
        return probs
