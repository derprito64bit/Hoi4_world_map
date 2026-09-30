"""EXP-02b: larger province-size variants of EXP-02 (owner request after EXP-02-300/600/1200 loaded).

Two builds (both run in game on 2026-09-29), each changing one property against vanilla
1.19.3. Every build records its side effects (host neighbour counts vs vanilla's maximum,
donors, enclaves, moved lines, newly non-contiguous states and strategic regions) in the
build info and prints them in its README (``side_effects``).

Retired in P00b-f6: ``EXP-02b-block-800-sea`` / ``-800-land`` (``RETIRED``). Their donor
remnants would cut 8 naval strategic regions in pieces (the fatal MAP_ERROR that stopped
block-400); no clean filled square of 400 px or more exists on the vanilla map
(``boxfill.find_rects``: some province always lies wholly inside and would stay as an
enclave); and every TOO LARGE BOX rule that fits the observations already predicts the line
for an 800 x 800 box. The threshold probes are EXP-02c.

block-400 was REJECTED in game (2026-09-29 23:02, -debug): TOO LARGE BOX for both hosts, and
the map was refused because its sea remnants cut North East Pacific and Central North Pacific
in pieces (``boxfill.fractioned_naval`` reproduces both regions and every separated province).
It stays buildable so the record can be reproduced; its README says not to run it again.

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
* ``EXP-02b-block-400`` -- a land and a sea province each become a
  solid, filled square of 400 x 400 px. The host province lies inside
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
so its state and strategic region can become non-contiguous (``--check`` allows
that only for states / regions that contain a donor) and its neighbours change.
Donors keep at least ``REMNANT`` px (or all of their pixels if they had fewer),
and moved position lines take y from the heightmap (sea level 9.50); ``--check``
enforces both.
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
# (land 400: Siberia, away from the map edge; sea 400: North Pacific). The 800-px squares were retired in P00b-f6.
BLOCKS = {400: {LAND: (33, 4513, 1852), SEA: (257, 289, 2755)}}
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
            continue
        y = fmt2(height_at(v.heightmap, q[0], q[1]))     # heightmap / 10, never below sea level 9.50
        if sb[cols[1]] != y:
            probs.append(f"{rel} line {i + 1}: moved position has height y={sb[cols[1]]}, the heightmap gives {y}")
    return probs


# ------------------------------------------------------------------ states
def noncontiguous_states(pid: np.ndarray, types: np.ndarray, province_state: dict, links: set) -> set:
    """State IDs whose land provinces are not connected (pixel contacts + adjacencies.csv), as validate_map.py."""
    by_state = {}
    for p, (sid, _) in province_state.items():
        if 0 < p < len(types) and types[p] == LAND:
            by_state.setdefault(sid, []).append(p)
    return noncontiguous_groups(pid, by_state, links)


def noncontiguous_regions(pid: np.ndarray, province_region: dict, links: set) -> set:
    """Strategic-region IDs whose provinces (land, sea and lake) are not connected (pixel contacts + adjacencies)."""
    by_region = {}
    for p, (rid, _) in province_region.items():
        by_region.setdefault(rid, []).append(p)
    return noncontiguous_groups(pid, by_region, links)


def noncontiguous_groups(pid: np.ndarray, groups: dict, links: set) -> set:
    """Keys of ``groups`` ({key: [province ids]}) whose members are not connected by contacts or links."""
    by_state = groups
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


def neighbour_counts(pid: np.ndarray, n: int) -> np.ndarray:
    """Number of distinct 4-adjacent provinces per ID (wrap included)."""
    pairs = adjacency_pairs(pid)
    return np.bincount(pairs.ravel(), minlength=n)


def rail_gaps(text: str, pairs: set) -> list:
    out = []
    for n, ln in enumerate(text.splitlines(), 1):
        s = [int(z) for z in ln.split()]
        for u, w in zip(s[2:], s[3:]):
            if (min(u, w), max(u, w)) not in pairs:
                out.append((n, u, w))
    return out


# ------------------------------------------------------------------ block rules on a finished map
def block_problems(v, van: np.ndarray, got: np.ndarray, size: int, kinds, protected: set) -> list:
    """Every rule of a block build (one square per kind in ``kinds``) on the finished province map.

    Positions are checked separately (``position_problems``).
    """
    probs = []
    types = v.types
    n = len(types)
    spec = {k: BLOCKS[size][k] for k in kinds}
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
        a_got = areas(got, n)
        for d in donors:
            cap = max(0, REMNANT - int(a_van[d] - in_sq[d])) + XFIX_SLACK
            if left[d] > cap:
                probs.append(f"donor {d} keeps {int(left[d])} px inside the square (at most {cap}): block not filled")
            if a_got[d] < min(REMNANT, int(a_van[d])):
                probs.append(f"donor {d} keeps {int(a_got[d])} px, below the {REMNANT}-px remnant the README promises")
    if (diff & ~allowed_px).any():
        bad = sorted(set(van[diff & ~allowed_px].tolist()))
        probs.append(f"pixels changed outside the allowed donors of the squares: provinces {bad[:10]}")
    if (types[van[diff]] != types[got[diff]]).any():
        probs.append("a re-assignment changed the type (land/sea/lake) of some pixels")
    if not set(got[diff].tolist()) <= set(hosts.values()):
        probs.append(f"changed pixels belong to a province other than the host(s) {sorted(hosts.values())}")
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
    donor_regions = {v.province_region[p][0] for p in shrunk if p in v.province_region}
    rc0 = noncontiguous_regions(van, v.province_region, links)
    rc1 = noncontiguous_regions(got, v.province_region, links)
    if rc0 - rc1:
        probs.append(f"strategic regions became contiguous (unexpected): {sorted(rc0 - rc1)[:10]}")
    if rc1 - rc0 - donor_regions:
        probs.append(f"strategic regions without a donor became non-contiguous: {sorted(rc1 - rc0 - donor_regions)[:10]}")
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


# ------------------------------------------------------------------ side effects (recorded in _meta and the README)
def side_effects(v, van: np.ndarray, got: np.ndarray, hosts: dict, moved: dict) -> dict:
    """What the build changes besides the box: host neighbour counts, donors, enclaves, moved lines, contiguity."""
    n = len(v.types)
    nb_van, nb_got = neighbour_counts(van, n), neighbour_counts(got, n)
    diff = got != van
    donors = sorted(set(np.unique(van[diff]).tolist()) - set(hosts.values()))
    touch = {}
    for a, b in adjacency_pairs(got).tolist():
        touch.setdefault(a, set()).add(b)
        touch.setdefault(b, set()).add(a)
    hs = set(hosts.values())
    enclaves = [d for d in donors if touch.get(d, set()) <= hs]
    links = adjacency_links(v.text("map/adjacencies.csv"))
    states = sorted(noncontiguous_states(got, v.types, v.province_state, links)
                    - noncontiguous_states(van, v.types, v.province_state, links))
    regions = sorted(noncontiguous_regions(got, v.province_region, links)
                     - noncontiguous_regions(van, v.province_region, links))
    return {"neighbours": {KIND_NAME[k]: int(nb_got[h]) for k, h in sorted(hosts.items())},
            "neighbours_before": {KIND_NAME[k]: int(nb_van[h]) for k, h in sorted(hosts.items())},
            "vanilla_max_neighbours": int(nb_van[1:].max()), "donor_count": len(donors),
            "enclaves": len(enclaves), "moved": dict(sorted(moved.items())), "moved_total": int(sum(moved.values())),
            "new_noncontiguous_states": states, "new_noncontiguous_regions": regions}


def _ids(xs, limit: int = 40) -> str:
    return (", ".join(str(x) for x in xs[:limit]) + (" ..." if len(xs) > limit else "")) if xs else "none"


# ------------------------------------------------------------------ experiment
# block builds: suffix -> (square size, kinds). block-800-sea / -land were retired in P00b-f6 (module doc).
BLOCK_BUILDS = {"block-400": (400, (LAND, SEA))}
RUN_ORDER = ["EXP-02b-strip-full", "EXP-02b-block-400"]
RETIRED = ("EXP-02b-block-800-sea", "EXP-02b-block-800-land")
ORDER_NOTE = ("The two EXP-02b builds, strip-full and block-400, were both run on 2026-09-29. strip-full is very "
              "wide but thin, like EXP-02-1200; block-400 is filled 400 px, land and sea. block-800-sea and "
              "block-800-land were retired (P00b-f6); the TOO LARGE BOX threshold probes are EXP-02c.")
REJECTED_NOTE = ("DO NOT RUN AGAIN: this build was run on 2026-09-29 and REJECTED. With -debug the game logged TOO "
                 "LARGE BOX for both hosts and refused the map with 'MAP_ERROR: Naval strategic region ... is "
                 "fractioned' (North East Pacific, Central North Pacific): the donor remnants cut those regions in "
                 "pieces. It is kept only so the record can be reproduced; run the EXP-02c builds instead.")
CANNOT_02B = {
    "size": ("the exact threshold: each EXP-02b build tests one size; a build that loads shows that this size works, "
             "a build that fails does not by itself locate the limit, because its host also has far more neighbours "
             "and enclaves than any vanilla province"),
    "block": ("one filled province of this size is not a full map of them: it does not show what many such provinces "
              "together (a whole ocean of large sea zones) do to loading, pathing or performance"),
    "strip": ("a 1-pixel strip is not a filled province (the block builds test that), and one very wide province is "
              "not a full map of them: it does not show what many such provinces together do to loading, pathing or "
              "performance"),
}


class Exp02b(Experiment):
    exp_id = "EXP-02b"
    title = "larger province-size variants"
    priority = 2

    def build_ids(self, ctx):
        return list(RUN_ORDER)

    def spec(self, build_id):
        """None for the strip build, else (square size, kinds)."""
        key = build_id.split("EXP-02b-", 1)[1]
        return None if key == "strip-full" else BLOCK_BUILDS[key]

    def title_for(self, build_id):
        sp = self.spec(build_id)
        if sp is None:
            return f"one sea province {STRIP_WIDTH[SEA]} px and one land province {STRIP_WIDTH[LAND]} px wide (strips)"
        size, kinds = sp
        what = " + one ".join(KIND_NAME[k] for k in kinds)
        return f"one {what} province filled {size}x{size} px"

    def expected(self, build_id):
        sp = self.spec(build_id)
        if sp is None:
            what = (f"WARN BBOX_LARGE lists the two test provinces (sea {STRIP_WIDTH[SEA]} px, land "
                    f"{STRIP_WIDTH[LAND]} px) besides vanilla's 7855 (280 px); that is the property under test.")
        else:
            size, kinds = sp
            n = "two test provinces" if len(kinds) == 2 else f"{KIND_NAME[kinds[0]]} test province"
            what = (f"WARN BBOX_LARGE lists the {n} ({size} px) besides vanilla's 7855 (280 px); that is the property "
                    "under test.")
            if LAND in kinds:
                what += (" WARN STATE_NONCONTIGUOUS lists more states than vanilla's 30: states of donor provinces "
                         "that now sit as small remnants inside the block (listed in the README).")
        return Expected(text=what + " Everything else as the vanilla baseline (0 ERROR, no PROVINCE_TOO_SMALL; WARN "
                                    "DEF_SEA_CONTINENT, STATE_NONCONTIGUOUS, RIVERS_ON_SEA, RIVERS_THICK, "
                                    "STATE_CATEGORY_DUP).")

    # -------------------------------------------------------------- build
    def make_strips(self, v):
        pid1, land = strip(v, LAND, STRIP_WIDTH[LAND])
        pid2, sea = strip(v, SEA, STRIP_WIDTH[SEA], pid1)
        return pid2, land, sea

    def make_blocks(self, v, size, kinds):
        pid = np.asarray(v.pid)
        prot = protected_ids(v)
        infos = {}
        out = pid
        for kind in kinds:
            r0, c0, host = BLOCKS[size][kind]
            out, infos[kind] = make_block(out, v.types, kind, host, r0, c0, size, prot)
        probs = block_problems(v, pid, out, size, kinds, prot)
        if probs:
            raise KitError("EXP-02b: block build breaks its own rules: " + "; ".join(probs[:5]))
        return out, infos

    def build(self, ctx, build_id, out: Path):
        v = ctx.vanilla
        van = np.asarray(v.pid)
        sp = self.spec(build_id)
        if sp is None:
            pid, land, sea = self.make_strips(v)
            infos = {LAND: land, SEA: sea}
        else:
            pid, infos = self.make_blocks(v, *sp)
        write_bytes(out, PROV, write_bmp(v.provinces_bmp, rgb_from_pid(pid, v.definition.colors()), keep_tail=True))
        files, moved = relocate_positions(v, van, pid)
        for rel, text in sorted(files.items()):
            write_bytes(out, rel, encode(text))
        hosts = {k: i["host"] for k, i in infos.items()}
        info = {KIND_NAME[k]: i for k, i in infos.items()}
        info["effects"] = side_effects(v, van, pid, hosts, moved)
        if LAND in infos:
            info["land_where"] = v.province_state[infos[LAND]["host"]][1].rsplit(".", 1)[0]
        if SEA in infos:
            info["sea_where"] = v.province_region[infos[SEA]["host"]][1].rsplit(".", 1)[0]
        return info

    # -------------------------------------------------------------- README
    def _effects_text(self, info):
        e = info["effects"]
        nb = " and ".join(f"the {k} host now touches {n} provinces (before: {e['neighbours_before'][k]})"
                          for k, n in e["neighbours"].items())
        moved = ", ".join(f"{k.split('/')[-1]} {n}" for k, n in e["moved"].items()) or "none"
        return (f"What else comes with it (not under test, but it could matter): {nb}; the most-connected province in "
                f"the normal game touches {e['vanilla_max_neighbours']}. {e['donor_count']} donor provinces lost "
                f"pixels, {e['enclaves']} of them are now enclaves inside a host. {e['moved_total']} position lines "
                f"moved ({moved}). Newly non-contiguous: {len(e['new_noncontiguous_states'])} states "
                f"({_ids(e['new_noncontiguous_states'])}) and {len(e['new_noncontiguous_regions'])} strategic "
                f"regions ({_ids(e['new_noncontiguous_regions'])}).")

    def _fail_line(self, info):
        e = info["effects"]
        nb = " / ".join(f"{n} ({k})" for k, n in e["neighbours"].items())
        return (f"If this build fails, it does NOT by itself show a size limit: the host also has {nb} neighbours "
                f"(normal game at most {e['vanilla_max_neighbours']}) and {e['enclaves']} enclaves; compare with the "
                "other EXP-02b builds and with EXP-02-1200.")

    def readme(self, ctx, build_id, info):
        sp = self.spec(build_id)
        hosts = [info[k]["host"] for k in ("land", "sea") if k in info]
        send = ["Did the game reach the main menu? Did a game start? (yes/no each)",
                "Loading time (roughly, in seconds).",
                "Every error.log line that contains 'BOX', 'box' or " + " or ".join(f"'{h}'" for h in hosts)
                + " (copy them exactly)."]
        notes = [self._fail_line(info), ORDER_NOTE]
        if sp is None:
            L, S = info["land"], info["sea"]
            prop = (f"map/provinces.bmp: sea province {S['host']} gets a 1-pixel-high strip {STRIP_WIDTH[SEA]} "
                    f"pixels wide (the map is 5632 px wide; the strip stops just short of the left/right wrap edge), "
                    f"and land province {L['host']} a strip {STRIP_WIDTH[LAND]} pixels wide. Land is narrower because "
                    f"a land strip may only run through land: {STRIP_WIDTH[LAND]} px is the widest valid land span on "
                    "the map (northern Eurasia). The strips borrow pixels from neighbouring provinces; no province "
                    "is removed, no state, coast or terrain changes. Unit, building and weather positions that stood "
                    "on a strip pixel moved into their own province; nothing else in those files changes.\n"
                    + self._effects_text(info))
            why = ("EXP-02-300/600/1200 all loaded. This pushes the same thin-strip test to the largest box the map "
                   "allows, to see whether any width limit exists at all.")
            steps = ["If the main menu appears: start a new game with any country and let it run for 2-3 days.",
                     f"Optional: look at sea province {S['host']} (strategic region '{info['sea_where']}', row "
                     f"{S['row']} from the top, far south) and land province {L['host']} (state file "
                     f"'{info['land_where']}'); a thin 1-pixel line running east from each is expected."]
            notes.append("Control: EXP-02-1200 (1,200 px strips, hosts with 12 and 27 neighbours) loaded without a "
                         "BOX line.")
            cannot = [CANNOT_02B["size"], CANNOT_02B["strip"]]
        else:
            size, kinds = sp
            parts = [info[KIND_NAME[k]] for k in kinds]
            who = " and ".join(f"{p['kind']} province {p['host']}" for p in parts)
            donors = " and ".join(f"{len(p['donors'])} {p['kind']}" for p in parts)
            fill = "; ".join(f"the {p['kind']} block is {p['fill']:.1%} host" for p in parts)
            verb = "each become" if len(parts) > 1 else "becomes"
            prop = (f"map/provinces.bmp: {who} {verb} a solid, filled square of {size} x {size} pixels (vanilla's "
                    "largest boxes are land 280 px and sea 179 px). The host takes over the pixels of the provinces "
                    f"inside the square: {donors} donor provinces. No province is removed: a donor that lay (almost) "
                    f"wholly inside the square keeps a small remnant of at least {REMNANT} pixels, so it stays on the "
                    f"map with its state, region and victory points. Filled: {fill} (the rest are those remnants, "
                    "lakes and provinces that must not move: railways, supply nodes, straits). Building, unit and "
                    "weather positions that stood on taken pixels moved into their own province's remnant; nothing "
                    "else in those files changes.\n" + self._effects_text(info))
            why = ("EXP-02 only tested thin 1-pixel strips. This tests whether a large province that is actually "
                   "filled loads, which is what open-ocean and off-map filler provinces would look like. It decides "
                   "BBOX_MAX (today land 250 / sea 180 px).")
            where = []
            if "land" in info:
                where.append(f"land province {info['land']['host']} (state file '{info['land_where']}')")
            if "sea" in info:
                where.append(f"sea province {info['sea']['host']} (strategic region '{info['sea_where']}')")
            steps = ["If the main menu appears: start a new game with any country and let it run for 2-3 days.",
                     f"Optional: look at {' and '.join(where)}: one big square with small enclaves (the donor "
                     "remnants, a few pixels each) in it is expected."]
            notes.insert(0, REJECTED_NOTE)
            notes.append("Side effect, on purpose: the donor remnants are enclaves inside the host, so their "
                         "neighbours changed (a remnant can only be reached through the host), and the states and "
                         "strategic regions listed above now have a piece cut off. The normal game already has 30 "
                         "non-contiguous states. Pathing near the blocks is not under test.")
            cannot = [CANNOT_02B["size"], CANNOT_02B["block"]]
        return texts.readme(build_id, self.title_for(build_id), prop=prop, why=why, launch=texts.LAUNCH_NORMAL,
                            steps=steps, send=send, expected=self.expected(build_id).text, cannot=[],
                            cannot_extra=cannot, user_dir=ctx.user, notes=notes)

    # -------------------------------------------------------------- check
    def check(self, ctx, build_id, out):
        v = ctx.vanilla
        sp = self.spec(build_id)
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
        if sp is None:       # positions on strip pixels are relocated, so the position mask is empty here
            probs += strip_problems(v, van, got, STRIP_WIDTH, np.zeros(van.shape, dtype=bool))
        else:
            probs += block_problems(v, van, got, sp[0], sp[1], protected_ids(v))
        for rel in sorted(POS_FILES):
            text = decode((out / rel).read_bytes()) if rel in present else None
            if text is not None and text == v.text(rel):
                probs.append(f"{rel} is present but identical to vanilla")
            probs += position_problems(v, van, got, rel, text)[:5]
        return probs


