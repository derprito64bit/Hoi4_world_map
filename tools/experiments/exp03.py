"""EXP-03 (+EXP-04): 16k / 20k / 24k / 30k provinces by subdividing vanilla land provinces.

The one property: the province count. Vanilla land provinces are cut into
compact, connected pieces (deterministic k-means on pixel coordinates, then a
connectivity repair). Each piece ("child") inherits its parent's state,
strategic region, terrain and continent; coastal flags are recomputed for the
whole map. Dependent files are updated so everything stays consistent:

* definition.csv   new rows appended (IDs contiguous), coastal column recomputed
* history/states   children appended to the parent's ``provinces = { }``
* strategicregions children appended to the parent's region
* buildings.txt    per-province lines (bunker, supply_node, special_project,
                   and the coastal set) regenerated for every member of a split
                   family; per-state lines untouched
* unitstacks.txt   the parent's position types regenerated for every member
* railways.txt     where a rail step no longer touches, the shortest path through
                   the split family is inserted
adjacencies.csv, supply_nodes.txt and weatherpositions.txt stay vanilla (IDs
kept, the parent keeps its ID on the piece holding its port / centre). Provinces
named in adjacencies.csv (strait ends and Through seas, canal land, impassable
borders) are never split, so every strait keeps its vanilla contacts (r1 split
province 761 in the 30k variant and lost its contact with strait sea 9092).

EXP-04 rides in the 20k variant: three extra provinces of exactly 6, 7 and 8 px
are carved out of the interior of three split pieces (IDs N-2, N-1, N).

P00b-f3 (the 24k crash, see regioncentre.py and diag03.py): the engine
divides by zero while computing a strategic region's centre when the mean of its
provinces' box centres lies outside every member box and is vertically aligned
with the region rectangle's centre. EXP-03-24k hits that in region 191 (Northern
Norway) by chance; the four original variants are kept byte-identical. Two
bisect variants were added:

* EXP-03-24k-fix  the 24k plan with a region-centre guard: a split parent of an
                  unsafe region is left unsplit and the plan is re-run (same count)
* EXP-03-div0     positive control: vanilla plus the pieces of ONE land province,
                  chosen so that exactly one region divides by zero; expected to
                  crash at the same code address. It LOADED in game (2026-09-29).

P00b-f5 (the div0 surprise; regioncentre.py explains it with 2-px-grid engine boxes,
under which div0's region 193 has divisor +1). Two probes:

* EXP-03-191only  locality: vanilla plus ONLY the 24k cuts of parents inside region 191
                  (same pieces, same pixels; new IDs renumbered contiguously after the
                  vanilla ones, in 24k ID order), dependent files made consistent as above.
                  Region 191's member boxes are identical to 24k's (pinned signature).
* EXP-03-div0b    vanilla plus the pieces of ONE land province, chosen so that one region
                  divides by zero under the old conventions AND under the grid model.
"""
from __future__ import annotations

import hashlib
import heapq
import json
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
from scipy import ndimage

from . import texts
from .base import Expected, Experiment, check_descriptor, check_file_set
from .bmpio import read_bmp, write_bmp
from .common import KitError, decode, encode, fmt2, sha256_tree, write_bytes
from .mapdata import (LAND, SEA, Definition, adjacency_ids, adjacency_links, adjacency_pairs, append_ids, areas, coast_points, coastal_flags,
                      fix_x_crossings, game_xz, height_at, interior_points, new_colors, pid_from_rgb, rgb_from_pid,
                      x_crossings)
from .positions import PER_COAST, PER_LAND, PER_PROVINCE, join_lines, position_pixels, split_lines
from .regioncentre import (DUMP_MEAN, DUMP_RECT, DUMP_REGION, guard_failures, pixel_boxes, region_centre,
                           region_centres)

TARGETS = {"16k": 16000, "20k": 20000, "24k": 24000, "30k": 30000}
FIX_VARIANT = "24k-fix"                 # 24,000 provinces with the region-centre guard
TRAP_VARIANT = "div0"                   # positive control: vanilla + one split province -> region centre / 0
LOCAL_VARIANT = "191only"               # P00b-f5: vanilla + only the 24k cuts inside region 191
LOCAL_SOURCE = "24k"
LOCAL_REGION = DUMP_REGION              # 191 Northern Norway
# member-box signature of region 191 in EXP-03-24k (RegionCentre.signature); 191only must reproduce it
LOCAL_SIGNATURE = "9607ba7cd8a9375c"
TRAP2_VARIANT = "div0b"                 # P00b-f5: one split province, divisor 0 under the old AND the grid model
TRAPS = (TRAP_VARIANT, TRAP2_VARIANT)
PROBES = (FIX_VARIANT, TRAP_VARIANT, LOCAL_VARIANT, TRAP2_VARIANT)   # owner sheets from readme_bisect
VARIANTS = {**TARGETS, FIX_VARIANT: TARGETS["24k"], TRAP_VARIANT: None, LOCAL_VARIANT: None, TRAP2_VARIANT: None}
# EXP-03-24k is kept byte-identical as the record of the in-game crash (2026-09-29, dump: region 191
# Northern Norway), so --check requires it to stay unsafe. The bisect (2026-09-29): 24k-fix loaded and div0
# loaded too. P00b-f5 added the 2-px-grid model (regioncentre.py): 191 stays unsafe in 24k and in 191only;
# div0's region 193 stays flagged by the old rule although it loaded (the guard is the conservative union).
KNOWN_UNSAFE = {"24k": [191], LOCAL_VARIANT: [191]}
# Builds seen loading in game (2026-09-28/29), pinned by mod_tree_sha256() of the bytes that were run:
# region-centre findings there are evidence, never a --check failure. None of them has one under the
# conservative model (P00b-f3 r3). A rebuild with different bytes gets no exemption.
OBSERVED_LOADING = {"16k": "6aa7b5b0347f1e84827eb99f6184900c86ee920549fdbeec75a8e0e824e33691",
                    "20k": "f6a0806fb8caf30b1440ce6f9171fc30e4527aba3e2564d1ab176a3e06c499a6",
                    "30k": "d0d39a8b4683babb70de75e8c457d1564f98c5cf78494be4f9285c13a88b2785"}
CRASH_RVA = 0x15A4CDC                   # hoi4.exe 1.19.3.0.c01a, strategicregiontemplate.cpp region centre
TRAP_KS = (2, 3, 4)
MIN_CHILD = 40          # px; well above the 8-px engine floor and near vanilla's p5 (68)
SMALL_SIZES = (6, 7, 8)
SMALL_VARIANT = "20k"
COLOR_SEED = 30003
COAST_TYPES = {19, 20}  # unitstacks types only coastal land provinces carry in vanilla 1.19.3
FOUR = [[0, 1, 0], [1, 1, 1], [0, 1, 0]]


# ------------------------------------------------------------------ splitting
def kmeans_labels(ys: np.ndarray, xs: np.ndarray, k: int, iters: int = 8) -> np.ndarray:
    """Deterministic k-means of pixel coordinates (farthest-point init, Lloyd)."""
    pts = np.stack([ys, xs], 1).astype(np.float64)
    c = pts.mean(0)
    first = int(((pts - c) ** 2).sum(1).argmin())
    centers = [pts[first]]
    d = ((pts - pts[first]) ** 2).sum(1)
    for _ in range(1, k):
        j = int(d.argmax())
        centers.append(pts[j])
        d = np.minimum(d, ((pts - pts[j]) ** 2).sum(1))
    C = np.array(centers)
    lab = np.zeros(len(pts), dtype=np.int64)
    for _ in range(iters):
        dist = ((pts[:, None, :] - C[None, :, :]) ** 2).sum(2)
        lab = dist.argmin(1)
        for j in range(k):
            m = lab == j
            if m.any():
                C[j] = pts[m].mean(0)
    return lab


def _merge_into_neighbour(labels: np.ndarray, sel: np.ndarray, own: int) -> bool:
    """Give the pixels ``sel`` the most common different label around them; False if none."""
    ring = ndimage.binary_dilation(sel, structure=FOUR) & ~sel
    cand = labels[ring]
    cand = cand[(cand >= 0) & (cand != own)]
    if cand.size == 0:
        return False
    labels[sel] = int(np.bincount(cand).argmax())
    return True


def split_mask(mask: np.ndarray, k: int, min_px: int = MIN_CHILD) -> np.ndarray:
    """Split a connected bool mask into <= k connected pieces; labels 0..m-1 (row-major order), -1 outside."""
    ys, xs = np.nonzero(mask)
    labels = np.full(mask.shape, -1, dtype=np.int64)
    labels[ys, xs] = kmeans_labels(ys, xs, k) if k > 1 else 0
    for _ in range(50):                      # connectivity + minimum size repair
        changed = False
        for lab in sorted(set(labels[labels >= 0].tolist())):
            m = labels == lab
            comp, n = ndimage.label(m, structure=FOUR)
            if n > 1:
                sizes = np.bincount(comp.ravel())[1:]
                keep = int(sizes.argmax()) + 1
                for c in range(1, n + 1):
                    if c != keep and _merge_into_neighbour(labels, comp == c, lab):
                        changed = True
            elif m.sum() < min_px and _merge_into_neighbour(labels, m, lab):
                changed = True
        if not changed:
            break
    # relabel by first pixel in row-major order
    flat = labels.ravel()
    order, seen = [], set()
    for v in flat[flat >= 0].tolist():
        if v not in seen:
            seen.add(v)
            order.append(v)
    remap = np.full(max(order) + 1, -1, dtype=np.int64)
    remap[order] = np.arange(len(order))
    out = labels.copy()
    out[labels >= 0] = remap[labels[labels >= 0]]
    return out


def plan_pieces(area: np.ndarray, eligible, extra: int, min_px: int = MIN_CHILD) -> dict:
    """{id: pieces} adding exactly ``extra`` pieces, always splitting the largest average piece first."""
    heap = [(-float(area[i]), int(i), 1) for i in sorted(eligible) if area[i] >= 2 * min_px]
    heapq.heapify(heap)
    k = {}
    added = 0
    while added < extra and heap:
        neg, i, n = heapq.heappop(heap)
        a = float(area[i])
        if a / (n + 1) < min_px:
            continue
        k[i] = n + 1
        added += 1
        heapq.heappush(heap, (-a / (n + 1), i, n + 1))
    if added < extra:
        raise KitError(f"cannot add {extra} pieces with pieces >= {min_px} px (only {added})")
    return k


def subdivide(pid: np.ndarray, types: np.ndarray, extra: int, root_of: np.ndarray, keep_pixel: dict,
              coastal_needed: set, min_px: int = MIN_CHILD, frozen=frozenset()):
    """Add exactly ``extra`` land provinces by splitting connected land provinces.

    Returns (new pid, root_of) where root_of[id] = vanilla ancestor. The piece
    that keeps an existing ID is the one holding ``keep_pixel[id]`` (a coastal
    piece if the ID is in ``coastal_needed``). New IDs follow in (id, piece) order.
    """
    pid = pid.copy()
    H, W = pid.shape
    next_id = len(root_of)
    root = list(root_of.tolist())
    sea = types[pid] == SEA
    for _ in range(10):                      # passes until the exact count is reached
        todo = extra - (next_id - len(root_of))
        if todo == 0:
            break
        n = next_id
        ty = np.array([types[root[i]] if i < len(root) else -1 for i in range(n)])
        area = areas(pid, n)
        objs = ndimage.find_objects(pid + 1)      # pid+1 so id 0 is label 1
        eligible = []
        for i in range(1, n):
            if ty[i] != LAND or area[i] < 2 * min_px or objs[i] is None or i in frozen:
                continue
            sl = objs[i]
            m = pid[sl] == i
            if ndimage.label(m, structure=FOUR)[1] == 1:
                eligible.append(i)
        plan = plan_pieces(area, eligible, todo, min_px)
        for i in sorted(plan):
            sl = objs[i]
            r0, c0 = sl[0].start, sl[1].start
            m = pid[sl] == i
            lab = split_mask(m, plan[i], min_px)
            npieces = int(lab.max()) + 1
            if npieces < 2:
                continue
            # coastal pieces: touching sea within a 1-px ring (wrap ignored; nothing touches both edges)
            ys0, ys1 = max(0, r0 - 1), min(H, sl[0].stop + 1)
            xs0, xs1 = max(0, c0 - 1), min(W, sl[1].stop + 1)
            big = np.full((ys1 - ys0, xs1 - xs0), -1, dtype=np.int64)
            big[r0 - ys0:r0 - ys0 + lab.shape[0], c0 - xs0:c0 - xs0 + lab.shape[1]] = lab
            s = sea[ys0:ys1, xs0:xs1]
            coastal_piece = set()
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                sh = np.roll(s, (dy, dx), axis=(0, 1))
                coastal_piece |= set(np.unique(big[(big >= 0) & sh]).tolist())
            kr, kc = keep_pixel.get(i, (None, None))
            keep = None
            if kr is not None and sl[0].start <= kr < sl[0].stop and sl[1].start <= kc < sl[1].stop:
                keep = int(lab[kr - r0, kc - c0]) if lab[kr - r0, kc - c0] >= 0 else None
            if i in coastal_needed and (keep is None or keep not in coastal_piece):
                cps = sorted(coastal_piece)
                keep = max(cps, key=lambda p: (int((lab == p).sum()), -p)) if cps else keep
            if keep is None:
                keep = int(np.bincount(lab[lab >= 0]).argmax())
            ids = {}
            for p in range(npieces):
                if p == keep:
                    ids[p] = i
                else:
                    ids[p] = next_id
                    root.append(root[i])
                    next_id += 1
            sub = pid[sl]
            for p, nid in ids.items():
                sub[lab == p] = nid
            if next_id - len(root_of) >= extra:
                break
    if next_id - len(root_of) != extra:
        raise KitError(f"subdivision produced {next_id - len(root_of)} new provinces, wanted {extra}")
    root = np.array(root, dtype=np.int64)
    fix_x_crossings(pid, lambda a, b: a != b and root[a] == root[b] and types[root[a]] == LAND)
    return pid, root


def carve_small(pid: np.ndarray, root: np.ndarray, types: np.ndarray, sizes, hosts_from: set, forbid_near=None):
    """Carve blobs of the given pixel counts out of the interior of big split pieces.

    Returns (pid, root, [(new id, host id, size, (row, col))]).
    """
    pid = pid.copy()
    root = list(root.tolist())
    n = len(root)
    area = areas(pid, n)
    coast = coastal_flags(pid, np.array([types[r] for r in root]))
    border = np.zeros(pid.shape, dtype=bool)
    border[1:] |= pid[1:] != pid[:-1]
    border[:-1] |= pid[:-1] != pid[1:]
    border[:, 1:] |= pid[:, 1:] != pid[:, :-1]
    border[:, :-1] |= pid[:, :-1] != pid[:, 1:]
    dist = ndimage.distance_transform_edt(~border)
    cand = sorted((i for i in hosts_from if not coast[i] and area[i] >= 300), key=lambda i: (-area[i], i))
    shapes = {6: [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)],
              7: [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0)],
              8: [(0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (1, 1), (1, 2), (1, 3)]}
    out, used_states = [], set()
    for size in sizes:
        for host in cand:
            if root[host] in used_states:
                continue
            ys, xs = np.nonzero((pid == host) & (dist >= 6))
            if not len(ys):
                continue
            order = np.lexsort((xs, ys))
            r, c = int(ys[order[len(order) // 2]]), int(xs[order[len(order) // 2]])
            cells = [(r + dy, c + dx) for dy, dx in shapes[size]]
            ring = {(y + a, x + b) for y, x in cells for a, b in ((-1, 0), (1, 0), (0, -1), (0, 1))} - set(cells)
            if all(pid[p] == host for p in cells) and all(pid[p] == host for p in ring):
                nid = len(root)
                root.append(root[host])
                for p in cells:
                    pid[p] = nid
                out.append((nid, host, size, (r, c)))
                used_states.add(root[host])
                cand.remove(host)
                break
        else:
            raise KitError(f"no host found for a {size}-px province")
    return pid, np.array(root, dtype=np.int64), out


# ------------------------------------------------------------------ region centres (P00b-f3)
def region_members(root: np.ndarray, region_of: np.ndarray) -> dict:
    """{region id: [province ids]} where every piece inherits its vanilla ancestor's region."""
    out = defaultdict(list)
    for i, r in enumerate(root.tolist()):
        rid = int(region_of[r]) if i else -1
        if rid >= 0:
            out[rid].append(i)
    return dict(out)


def region_lookup(v, n0: int) -> np.ndarray:
    """Array vanilla id -> strategic region id (-1 = none)."""
    out = np.full(n0, -1, dtype=np.int64)
    for p, (rid, _) in v.province_region.items():
        if 0 < p < n0:
            out[p] = rid
    return out


def mod_tree_sha256(out: Path) -> str:
    """sha256 over {path: sha256} of a build folder, README.txt excluded (it holds the machine's user dir)."""
    files = {rel: h for rel, h in sha256_tree(out).items() if rel != "README.txt"}
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def model_values(c) -> dict:
    """The region-centre model's numbers for one region (README / build meta)."""
    return {"members": c.n, "mean": list(c.mean), "rect": list(c.rect), "dx": c.dx, "dy": c.dy,
            "fallback_all": c.fallback_all, "mean_g2": list(c.mean_g2), "rect_g2": list(c.rect_g2),
            "fallback_g2": c.fallback_g2, "dx_g2": c.dx_g2, "unsafe_old": c.unsafe_old, "crash_g2": c.crash_g2,
            "signature": c.signature}


def centres_of(pid: np.ndarray, root: np.ndarray, region_of: np.ndarray) -> dict:
    return region_centres(pid, region_members(root, region_of))


def guard_failures_of(pid: np.ndarray, root: np.ndarray, region_of: np.ndarray, observed: dict | None = None) -> list:
    """Guard failures: conservatively unsafe regions, plus wrapping (unknown) regions that take the
    fallback and have no identical twin in ``observed`` (centres of a map seen loading, e.g. vanilla)."""
    return guard_failures(centres_of(pid, root, region_of), observed)


def vanilla_centres(van_pid: np.ndarray, region_of: np.ndarray) -> dict:
    return centres_of(van_pid, np.arange(len(region_of)), region_of)


def guarded_subdivide(van_pid, types, extra, keep_pixel, coastal_needed, frozen, region_of, max_rounds: int = 8):
    """subdivide() that re-plans until no strategic region fails the region-centre guard.

    Per failing region one of its split parents (fewest pieces, then lowest ID) is
    frozen (left whole) and the plan is re-run with the same ``extra``; returns
    (pid, root, [(region, frozen parent), ...], [parents cut into more pieces than
    in the unguarded plan]). Unknown (wrapping) regions only pass if identical to vanilla.
    """
    n0 = len(types)
    observed = vanilla_centres(van_pid, region_of)
    fz = set(frozen)
    guard = []
    first = None
    for _ in range(max_rounds):
        pid, root = subdivide(van_pid, types, extra, np.arange(n0), keep_pixel, coastal_needed, frozen=fz)
        kids = np.bincount(root[n0:], minlength=n0)
        if first is None:
            first = kids
        bad = guard_failures_of(pid, root, region_of, observed)
        if not bad:
            return pid, root, guard, [int(p) for p in np.nonzero(kids > first)[0]]
        for rid in bad:
            parents = sorted((p for p in range(1, n0) if kids[p] and region_of[p] == rid), key=lambda p: (kids[p], p))
            if not parents:
                raise KitError(f"region {rid} fails the region-centre guard without any split province")
            fz.add(parents[0])
            guard.append((int(rid), int(parents[0])))
    raise KitError(f"region-centre guard did not converge in {max_rounds} rounds")


def _piece_boxes(lab: np.ndarray, r0: int, c0: int, H: int):
    """Pixel boxes (xmin, xmax, ymin, ymax; y from the bottom) of the pieces 0..m-1 of a split_mask() result."""
    out = []
    for q in range(int(lab.max()) + 1):
        ys, xs = np.nonzero(lab == q)
        out.append((c0 + int(xs.min()), c0 + int(xs.max()), H - 1 - (r0 + int(ys.max())), H - 1 - (r0 + int(ys.min()))))
    return out


def _is_trap(c) -> bool:
    """The observed crash under every box convention: fallback even with the widest box, dx == 0, no wrap."""
    return c.fallback_all and c.dx == 0 and not c.seam


def _is_trap_both(c) -> bool:
    """div0b (P00b-f5): the old condition (``_is_trap``) AND the grid model's predicted crash."""
    return _is_trap(c) and c.crash_g2


def _takes_fallback(c) -> bool:
    return c.fallback


def _takes_any_fallback(c) -> bool:
    return c.fallback or c.fallback_g2


def trap_candidates(van_pid, types, region_of, frozen, min_px: int = MIN_CHILD, pred=_is_trap,
                    include=_takes_fallback):
    """Yield (region, province, pieces) whose split alone makes ``pred`` true for its region (model only).

    Vanilla regions for which ``include`` holds are searched, by |dx| then ID; wrapping regions are skipped.
    The defaults are the P00b-f3 div0 search (kept so that EXP-03-div0 stays byte-identical).
    """
    H, W = van_pid.shape
    n0 = len(types)
    root = np.arange(n0)
    regions = region_members(root, region_of)
    boxes = pixel_boxes(van_pid, n0)
    cs = region_centres(van_pid, regions)
    order = sorted((c for c in cs.values() if include(c) and not c.seam), key=lambda c: (abs(c.dx), c.region))
    objs = ndimage.find_objects(van_pid + 1)
    area = areas(van_pid, n0)
    for c in order:
        ids = regions[c.region]
        for p in sorted(ids):
            sl = objs[p]
            if types[p] != LAND or p in frozen or sl is None or area[p] < 2 * min_px:
                continue
            m = van_pid[sl] == p
            if ndimage.label(m, structure=FOUR)[1] != 1:
                continue
            for k in TRAP_KS:
                if area[p] / k < min_px:
                    break
                lab = split_mask(m, k, min_px)
                if int(lab.max()) + 1 != k:
                    continue
                pb = _piece_boxes(lab, sl[0].start, sl[1].start, H)
                ext = [np.concatenate([a, np.array([b[j] for b in pb[1:]], dtype=np.int64)]) for j, a in enumerate(boxes)]
                for j in range(4):
                    ext[j][p] = pb[0][j]
                mem = list(ids) + list(range(n0, n0 + k - 1))
                if pred(region_centre(c.region, mem, tuple(ext), W)):
                    yield int(c.region), int(p), k


def trap_split(van_pid, types, region_of, keep_pixel, coastal_needed, frozen, min_px: int = MIN_CHILD,
               pred=_is_trap, include=_takes_fallback):
    """(pid, root, (region, province, pieces)) for the first model candidate that survives the full pipeline."""
    n0 = len(types)
    observed = vanilla_centres(van_pid, region_of)
    for rid, p, k in trap_candidates(van_pid, types, region_of, frozen, min_px, pred, include):
        fz = set(range(1, n0)) - {p}
        pid, root = subdivide(van_pid, types, k - 1, np.arange(n0), keep_pixel, coastal_needed, min_px, frozen=fz)
        cs = centres_of(pid, root, region_of)
        if guard_failures(cs, observed) == [rid] and pred(cs[rid]):
            return pid, root, (rid, p, k)
    raise KitError("no single-province split recreates the region-centre division by zero")


def local_split(van_pid: np.ndarray, pid_src: np.ndarray, root_src: np.ndarray, region_of: np.ndarray, region: int):
    """(pid, root, parents): vanilla plus only those pieces of a subdivided map whose parent is in ``region``.

    ``pid_src`` / ``root_src`` are a subdivide() result on ``van_pid``. Inside the parents' vanilla
    footprint the pixels are copied from ``pid_src`` unchanged; everywhere else the map stays vanilla.
    The pieces that do not keep the parent's ID are renumbered contiguously from ``len(region_of)``
    in their source-ID order.
    """
    n0 = len(region_of)
    kids = np.array([i for i in range(n0, len(root_src)) if region_of[int(root_src[i])] == region], dtype=np.int64)
    parents = sorted({int(root_src[i]) for i in kids})
    if not parents:
        raise KitError(f"region {region}: the source map has no split province there")
    remap = np.arange(len(root_src), dtype=np.int64)
    remap[kids] = np.arange(n0, n0 + len(kids))
    m = np.isin(van_pid, parents)
    if not np.array_equal(m, np.isin(root_src[pid_src], parents)):
        raise KitError("the source map is not a refinement of vanilla inside the parents' footprint")
    pid = van_pid.copy()
    pid[m] = remap[pid_src[m]].astype(pid.dtype)
    root = np.concatenate([np.arange(n0, dtype=np.int64), root_src[kids].astype(np.int64)])
    return pid, root, parents


# ------------------------------------------------------------------ dependent files
def update_railways(text: str, pid_pairs: set, root: np.ndarray) -> tuple:
    """Insert family paths where consecutive rail provinces no longer touch. Returns (text, inserted count)."""
    fam = defaultdict(list)
    for i, r in enumerate(root.tolist()):
        fam[r].append(i)
    nb = defaultdict(set)
    for a, b in pid_pairs:
        nb[a].add(b)
        nb[b].add(a)
    lines, trailing = split_lines(text)
    out, inserted = [], 0
    for ln in lines:
        s = ln.split()
        if len(s) < 3:
            out.append(ln)
            continue
        lvl, ps = s[0], [int(x) for x in s[2:]]
        chain = [ps[0]]
        for a, b in zip(ps, ps[1:]):
            if b in nb[a]:
                chain.append(b)
                continue
            allowed = set(fam[int(root[a])]) | set(fam[int(root[b])])
            prev, q = {a: None}, deque([a])
            while q:
                u = q.popleft()
                if u == b:
                    break
                for w in sorted(nb[u]):
                    if w in allowed and w not in prev:
                        prev[w] = u
                        q.append(w)
            if b not in prev:
                raise KitError(f"railway step {a}->{b} cannot be reconnected through its split family")
            path, u = [], b
            while u is not None:
                path.append(u)
                u = prev[u]
            path = path[::-1]
            inserted += len(path) - 2
            chain.extend(path[1:])
        trail = " " if ln.endswith(" ") else ""
        out.append(" ".join([lvl, str(len(chain))] + [str(x) for x in chain]) + trail)
    return join_lines(out, trailing), inserted


def unitstack_template(lines, types, coastal) -> dict:
    """{type: (rotation, offset)} from the first vanilla coastal land province (fallback values)."""
    by = defaultdict(dict)
    for ln in lines:
        s = ln.split(";")
        if len(s) >= 7:
            by[int(s[0])][int(s[1])] = (s[5], s[6])
    for p in sorted(by):
        if types[p] == LAND and coastal[p] and COAST_TYPES <= set(by[p]):
            return by[p]
    raise KitError("no coastal land province with unitstacks found")


class Exp03(Experiment):
    exp_id = "EXP-03"
    title = "province count"
    priority = 3

    def build_ids(self, ctx):
        return [f"EXP-03-{k}" for k in VARIANTS]

    def key(self, build_id):
        return build_id[len("EXP-03-"):]

    def title_for(self, build_id):
        k = self.key(build_id)
        if k == TRAP_VARIANT:
            return "vanilla + one split province, region-centre division by zero (expected CRASH)"
        if k == LOCAL_VARIANT:
            return "vanilla + only the 24k cuts in region 191 Northern Norway (locality probe, expected CRASH)"
        if k == TRAP2_VARIANT:
            return "vanilla + one split province, division by zero under both box models (expected CRASH)"
        t = f"{VARIANTS[k]:,} provinces"
        if k == FIX_VARIANT:
            return t + ", region-centre guard"
        return t + " + 6/7/8-px provinces (EXP-04)" if k == SMALL_VARIANT else t

    def expected(self, build_id):
        if self.key(build_id) == SMALL_VARIANT:
            return Expected(errors={"PROVINCE_TOO_SMALL"},
                            text="ERROR PROVINCE_TOO_SMALL for exactly the 6-px and 7-px test provinces (the 8-px one "
                                 "passes the 8-px floor); that is EXP-04. Otherwise " + texts.BASELINE_WARNS + ".")
        return Expected(text="No new finding: " + texts.BASELINE_WARNS + ".")

    # -------------------------------------------------------------- build
    def make(self, v, build_id):
        """(pid, root, smalls, info) for one variant; info holds the guard / trap decisions."""
        key = self.key(build_id)
        small = SMALL_SIZES if key == SMALL_VARIANT else ()
        van_pid = np.asarray(v.pid)
        types = v.types
        vdef = v.definition
        n0 = vdef.n
        H, W = van_pid.shape
        bl, btr = split_lines(v.text("map/buildings.txt"))
        bpix = position_pixels(bl, 2, 4, H, W)
        keep_pixel = {}
        for ln, px in zip(bl, bpix):
            s = ln.split(";")
            if px is not None and len(s) > 1 and s[1] == "naval_base_spawn":
                p = int(van_pid[px])
                keep_pixel.setdefault(p, px)
        centre = interior_points(van_pid)
        for p, rc in centre.items():
            keep_pixel.setdefault(p, rc)
        coastal_needed = {i for i in range(1, n0) if types[i] == LAND and vdef.rows[i][5] == "true"}
        frozen = adjacency_ids(v.text("map/adjacencies.csv"))
        info = {}
        if key in TRAPS:
            region_of = region_lookup(v, n0)
            opts = {} if key == TRAP_VARIANT else {"pred": _is_trap_both, "include": _takes_any_fallback}
            pid, root, (rid, p, k) = trap_split(van_pid, types, region_of, keep_pixel, coastal_needed, frozen, **opts)
            info["trap"] = {"region": rid, "province": p, "pieces": k,
                            "region_file": v.province_region[p][1], "state_file": v.province_state[p][1],
                            "model": model_values(centres_of(pid, root, region_of)[rid])}
            return pid, root, [], info
        if key == LOCAL_VARIANT:
            src, root_src, _, _ = self.make(v, f"EXP-03-{LOCAL_SOURCE}")
            region_of = region_lookup(v, n0)
            pid, root, parents = local_split(van_pid, src, root_src, region_of, LOCAL_REGION)
            info["local"] = {"region": LOCAL_REGION, "region_file": v.province_region[parents[0]][1],
                             "parents": parents, "pieces": int(len(root) - n0),
                             "states": sorted({v.province_state[p][1] for p in parents}),
                             "model": model_values(centres_of(pid, root, region_of)[LOCAL_REGION])}
            return pid, root, [], info
        extra = VARIANTS[key] - (n0 - 1) - len(small)
        if extra <= 0:
            raise KitError("target below the vanilla province count")
        if key == FIX_VARIANT:
            pid, root, guard, moved = guarded_subdivide(van_pid, types, extra, keep_pixel, coastal_needed, frozen,
                                                        region_lookup(v, n0))
            info["guard"] = [{"region": r, "unsplit": p, "region_file": v.province_region[p][1]} for r, p in guard]
            info["cut_instead"] = [{"province": p, "state_file": v.province_state[p][1]} for p in moved]
        else:
            pid, root = subdivide(van_pid, types, extra, np.arange(n0), keep_pixel, coastal_needed, frozen=frozen)
        smalls = []
        if small:
            split_members = {i for i in range(n0, len(root))}
            pid, root, smalls = carve_small(pid, root, types, small, split_members)
        return pid, root, smalls, info

    def build(self, ctx, build_id, out: Path):
        v = ctx.vanilla
        pid, root, smalls, info = self.make(v, build_id)
        files = self.dependent_files(v, pid, root, smalls)
        for rel, data in files.items():
            write_bytes(out, rel, data)
        where = {i: v.province_state[int(root[i])][1].rsplit(".", 1)[0] for i, _, _, _ in smalls}
        return {"target": int(len(root) - 1), "smalls": [(i, s) for i, _, s, _ in smalls],
                "where": where, "new": int(len(root) - v.definition.n), **info}

    def dependent_files(self, v, pid, root, smalls) -> dict:
        vdef = v.definition
        n0, n = vdef.n, len(root)
        H, W = pid.shape
        types_v = v.types
        types = np.array([types_v[r] for r in root.tolist()], dtype=np.int8)
        types[0] = -1
        # definition.csv
        d = vdef.copy()
        cols = new_colors(vdef.colors(), n - n0, COLOR_SEED)
        for j, i in enumerate(range(n0, n)):
            pr = vdef.rows[int(root[i])]
            d.rows.append([str(i), str(cols[j][0]), str(cols[j][1]), str(cols[j][2]), "land", "false", pr[6], pr[7]])
        coast = coastal_flags(pid, types)
        for i in range(1, n):
            if types[i] == LAND:
                d.rows[i][5] = "true" if coast[i] else "false"
        colors = d.colors()
        files = {"map/provinces.bmp": write_bmp(v.provinces_bmp, rgb_from_pid(pid, colors), keep_tail=True),
                 "map/definition.csv": encode(d.format())}
        # families
        fam = defaultdict(list)
        for i in range(n0, n):
            fam[int(root[i])].append(i)
        parents = sorted(fam)
        members = sorted(set(parents) | set(range(n0, n)))
        # states and regions
        pstate, pregion = v.province_state, v.province_region
        add_state, add_region = defaultdict(list), defaultdict(list)
        for i in range(n0, n):
            add_state[pstate[int(root[i])][1]].append(i)
            add_region[pregion[int(root[i])][1]].append(i)
        for f in sorted(add_state):
            files["history/states/" + f] = encode(append_ids(v.state_files[f], "provinces", add_state[f]))
        for f in sorted(add_region):
            files["map/strategicregions/" + f] = encode(append_ids(v.region_files[f], "provinces", add_region[f]))
        # positions
        hm = v.heightmap
        centre = interior_points(pid, members)
        cpts = coast_points(pid, types, [m for m in members if coast[m]], centre)
        van_pid = np.asarray(v.pid)
        fam_area = np.zeros(n0, dtype=bool)
        fam_area[parents] = True
        in_fam = fam_area[van_pid]
        # buildings.txt
        bl, btr = split_lines(v.text("map/buildings.txt"))
        bpix = position_pixels(bl, 2, 4, H, W)
        keep, rot = [], {}
        for ln, px in zip(bl, bpix):
            s = ln.split(";")
            if px is not None and len(s) >= 7 and s[1] in PER_PROVINCE and in_fam[px]:
                par = int(van_pid[px])
                if int(s[0]) == pstate[par][0]:
                    rot.setdefault((par, s[1]), s[5])
                    continue
            keep.append(ln)
        new_b = []
        for m in members:
            sid = pstate[int(root[m])][0]
            r, c = centre[m]
            x, z = game_xz(r, c, H)
            for t in PER_LAND:
                new_b.append(f"{sid};{t};{fmt2(x)};{fmt2(height_at(hm, r, c))};{fmt2(z)};"
                             f"{rot.get((int(root[m]), t), '0.00')};0")
            if coast[m]:
                cr, cc, sea_id = cpts[m]
                x, z = game_xz(cr, cc, H)
                for t in PER_COAST:
                    extra_col = sea_id if t == "naval_base_spawn" else (m if t == "floating_harbor" else 0)
                    new_b.append(f"{sid};{t};{fmt2(x)};{fmt2(height_at(hm, cr, cc))};{fmt2(z)};"
                                 f"{rot.get((int(root[m]), t), '0.00')};{extra_col}")
        files["map/buildings.txt"] = encode(join_lines(keep + new_b, btr))
        # unitstacks.txt
        ul, utr = split_lines(v.text("map/unitstacks.txt"))
        tmpl = unitstack_template(ul, types_v, vdef.coastal())
        par_set = set(parents)
        pstacks = defaultdict(dict)
        keep_u = []
        for ln in ul:
            s = ln.split(";")
            p = int(s[0])
            if p in par_set:
                pstacks[p][int(s[1])] = (s[5], s[6])
            else:
                keep_u.append(ln)
        new_u = []
        for m in members:
            base = pstacks.get(int(root[m]), {})
            tset = (set(base) - COAST_TYPES) | (COAST_TYPES if coast[m] else set())
            if not base:
                tset = set()
            r, c = centre[m]
            x, z = game_xz(r, c, H)
            y = fmt2(height_at(hm, r, c))
            for t in sorted(tset):
                ro, off = base.get(t, tmpl.get(t, ("0.00", "0.00")))
                new_u.append(f"{m};{t};{fmt2(x)};{y};{fmt2(z)};{ro};{off}")
        files["map/unitstacks.txt"] = encode(join_lines(keep_u + new_u, utr))
        # railways.txt
        pairs = {tuple(p) for p in adjacency_pairs(pid).tolist()} | adjacency_links(v.text("map/adjacencies.csv"))
        rail, _ = update_railways(v.text("map/railways.txt"), pairs, root)
        if rail != v.text("map/railways.txt"):
            files["map/railways.txt"] = encode(rail)
        return files

    # -------------------------------------------------------------- README
    def readme(self, ctx, build_id, info):
        if self.key(build_id) in (LOCAL_VARIANT, TRAP2_VARIANT):
            return self.readme_probe(ctx, build_id, info)
        if self.key(build_id) in PROBES:
            return self.readme_bisect(ctx, build_id, info)
        target = info["target"]
        steps = ["When the main menu appears, note the loading time. Start a new game (1936) with any country, "
                 "unpause and let 7 in-game days pass at speed 3, then pause.",
                 "Note: Did it crash? Roughly how smooth was it (fine / slow / very slow)?"]
        send = ["Loaded: yes / no. Loading time from Play to the main menu (seconds).",
                "Game started and 7 days passed: yes / no / crashed (when?).",
                "Your PC's RAM and graphics card, if you know them (the limit may depend on them)."]
        cannot = ["EXP-03"]
        notes = [f"This variant has {target:,} provinces (vanilla 13,413); the extra ones are pieces of vanilla "
                 "land provinces, so borders look busier. States, owners and everything else are unchanged.",
                 "Test the variants in order 16k, 20k, 24k, 30k and stop at the first one that fails.",
                 "Provinces at the ends of straits, canals and blocked borders are never cut, so crossings such as "
                 "the Danish straits or Lake Ontario work as in the normal game."]
        if info.get("smalls"):
            ids = ", ".join(f"{i} ({s} px, state file '{info['where'][i]}')" for i, s in info["smalls"])
            nums = ", ".join(str(i) for i, _ in info["smalls"])
            steps.append(f"Optional, while the game runs (needs -debug to see numbers): find the tiny provinces {ids} "
                         "inside their states and try to hover and click one.")
            send.append(f"EXP-04: open the error log with Notepad, search (Ctrl+F) for {nums} and copy every line "
                        "that mentions them. Could you hover/click a tiny province (yes / no / not tried)?")
            cannot.append("EXP-04")
            notes.append(f"EXP-04 test provinces: {ids}. The game's own setting says provinces under 8 px only "
                         "produce a log line; this checks that.")
        return texts.readme(
            build_id, self.title_for(build_id),
            prop=f"The number of provinces: {target:,} instead of 13,413. Vanilla land provinces are cut into "
                 "smaller pieces; every piece stays in its original state and strategic region with the same "
                 "terrain. Only the files that list provinces are updated to match.",
            why="Decides PROVINCE_BUDGET: how many provinces our world map may have before the game refuses to "
                "load, crashes or becomes too slow.",
            launch=texts.LAUNCH_NORMAL, steps=steps, send=send,
            expected=self.expected(build_id).text, cannot=cannot, user_dir=ctx.user, notes=notes)

    def readme_bisect(self, ctx, build_id, info):
        """Owner sheet for the two P00b-f3 variants (24k-fix must load, div0 must crash)."""
        ud = str(ctx.user).replace("\\", "/") if ctx.user else "$HOI4_USER_DIR"
        crash_send = (f"If it crashed: the newest folder in {ud}/crashes/ -> open exception.txt with Notepad and copy "
                      "the lines from 'Unhandled Exception' down to line 3 of the Stack Trace. Also say whether "
                      "game.log (in the same folder's logs/ or in logs/) contains 'Loaded' followed by a number of "
                      "provinces.")
        launch = ("Start the game from the launcher (Play) WITHOUT -debug. Note whether the main menu appears or the "
                  "game closes/crashes while loading. One try is enough; do not retry with -debug.")
        notes = ["Background: EXP-03-24k crashed while loading (divide by zero) although 30k loaded. The crash dump "
                 "shows the game computing the centre of one strategic region (Northern Norway) and dividing by "
                 "zero; see tools/experiments/regioncentre.py. These two builds test that explanation from both "
                 "sides.",
                 "Run order: EXP-03-24k-fix first, then EXP-03-div0. Report both results even if the first one "
                 "is not what we expect."]
        if self.key(build_id) == FIX_VARIANT:
            g = ", ".join(f"{x['unsplit']} (region file '{x['region_file']}')" for x in info.get("guard", []))
            c = ", ".join(f"{x['province']} (state file '{x['state_file']}')" for x in info.get("cut_instead", []))
            prop = (f"The number of provinces: {info['target']:,}, exactly like EXP-03-24k, but the province cuts were "
                    "planned with a guard so that no strategic region hits the centre division by zero. Compared "
                    f"with EXP-03-24k only this changes: vanilla provinces {g or '-'} stay whole, and instead "
                    f"vanilla provinces {c or '-'} get one more cut. The new pieces are numbered differently.")
            why = ("If this loads, the 24k crash was the region-centre division and not the province count: the "
                   "province budget is then limited by performance only (30k loads).")
            steps = ["If the main menu appears: start a new game (1936) with any country, unpause and let 7 in-game "
                     "days pass at speed 3, then pause. Note: did it crash? How smooth was it?"]
            send = ["Loaded to the main menu: yes / no. Loading time from Play to the main menu (seconds).",
                    "Game started and 7 days passed: yes / no / crashed (when?).", crash_send]
            expected_result = "EXPECTED IN GAME: loads and runs like EXP-03-30k."
        else:
            t = info["trap"]
            prop = (f"Vanilla map plus ONE extra change: vanilla land province {t['province']} (state file "
                    f"'{t['state_file']}') is cut into {t['pieces']} pieces. The cut is chosen so that the game's "
                    f"centre calculation for strategic region {t['region']} ('{t['region_file']}') divides by zero, "
                    "the same way EXP-03-24k did in Northern Norway.")
            why = ("A deliberate crash test (positive control). If this crashes at the same place as EXP-03-24k, the "
                   "cause is confirmed and the real map generator can simply avoid it.")
            steps = ["EXPECTED: the game closes or shows a crash window while loading, before the main menu. That "
                     "is the intended result. If the main menu appears instead, quit the game (no need to start a "
                     "campaign)."]
            send = ["Crashed while loading: yes / no (main menu appeared).", crash_send]
            expected_result = (f"EXPECTED IN GAME: crash while loading with EXCEPTION_INT_DIVIDE_BY_ZERO at the same "
                               f"address as EXP-03-24k (hoi4.exe offset 0x{CRASH_RVA:X}; 0x7FF6129C4CDC in the "
                               "2026-09-29 dumps).")
        return texts.readme(
            build_id, self.title_for(build_id), prop=prop, why=why, launch=launch, steps=steps, send=send,
            expected=self.expected(build_id).text, cannot=["EXP-03"], user_dir=ctx.user,
            notes=[expected_result] + notes,
            cannot_extra=["Whether other, unrelated engine limits exist between 24k and 30k provinces: this pair only "
                          "tests the region-centre explanation."])

    def readme_probe(self, ctx, build_id, info):
        """Owner sheet for the two P00b-f5 probes (191only, div0b); both are expected to crash."""
        ud = str(ctx.user).replace("\\", "/") if ctx.user else "$HOI4_USER_DIR"
        crash_send = (f"If it crashed: the newest folder in {ud}/crashes/ -> open exception.txt with Notepad and copy "
                      "the lines from 'Unhandled Exception' down to line 3 of the Stack Trace. Keep that crash folder "
                      "(the minidump.dmp in it is read offline). Also say whether game.log contains 'Loaded' "
                      "followed by a number of provinces.")
        launch = ("Start the game from the launcher (Play) WITHOUT -debug. Note whether the main menu appears or the "
                  "game closes/crashes while loading. One try is enough; do not retry with -debug.")
        steps = ["EXPECTED: the game closes or shows a crash window while loading, before the main menu. If the main "
                 "menu appears instead, quit the game (no need to start a campaign). Both outcomes are useful."]
        send = ["Crashed while loading: yes / no (main menu appeared).", crash_send]

        def values(m, label):
            return (f"Model values for {label}: {m['members']} provinces; old box model: mean point {tuple(m['mean'])}, "
                    f"region rectangle {tuple(m['rect'])}, divisor {m['dx']}; 2-px grid model: mean point "
                    f"{tuple(m['mean_g2'])}, rectangle {tuple(m['rect_g2'])}, divisor {m['dx_g2']}; the mean lies in "
                    f"no member box under either model: {m['fallback_all'] and m['fallback_g2']}.")
        notes = ["Background: EXP-03-24k crashed (divide by zero in the centre calculation of strategic region 191, "
                 "Northern Norway). EXP-03-div0 was built to hit the same division in region 193 and LOADED, so our "
                 "first model was incomplete. Reading the crash dump again suggests that the game stores province "
                 "boxes on a 2-pixel grid (one province box left in the dump is 1 px wider than its pixels; the "
                 "grid rule fits every number in the dump, but it is a fit, not proven). With that correction the "
                 "model reproduces the 24k crash and says div0 should load (its divisor becomes +1). These two "
                 "builds test the corrected model.",
                 "Run order: EXP-03-191only first, then EXP-03-div0b. Report both results even if the first one is "
                 "not what we expect."]
        if self.key(build_id) == LOCAL_VARIANT:
            t = info["local"]
            ps = ", ".join(str(p) for p in t["parents"])
            first = ctx.vanilla.definition.n                     # vanilla IDs are 1..n-1
            last = first + t["pieces"] - 1
            prop = (f"Vanilla map plus ONLY the province cuts that EXP-03-24k made inside strategic region "
                    f"{t['region']} ('{t['region_file']}'): vanilla land provinces {ps} (state files "
                    f"{', '.join(repr(s) for s in t['states'])}) are cut into exactly the same pieces, pixel for pixel, "
                    f"as in EXP-03-24k. That adds {t['pieces']} provinces, numbered {first}-{last} (in 24k they had "
                    "higher numbers). Every other province, state and region is the normal game; the files that list "
                    "provinces are updated to match.")
            why = ("Locality test. If this crashes at the same place as EXP-03-24k, the trigger lies in region 191's "
                   "own shapes. If it loads, the 24k crash also needs something else from the 24k map (for example "
                   "the total province count or the number range of the IDs).")
            expected_result = (f"EXPECTED IN GAME: crash while loading with EXCEPTION_INT_DIVIDE_BY_ZERO at the same "
                               f"address as EXP-03-24k (hoi4.exe offset 0x{CRASH_RVA:X}; 0x7FF6129C4CDC in the "
                               "2026-09-29 dumps) - but the address can differ if Windows loads hoi4.exe elsewhere; "
                               "the offset is what counts.")
            notes = [expected_result, values(t["model"], f"region {t['region']} in this build (the same as in "
                                                         "EXP-03-24k and in both 24k crash dumps)")] + notes
        else:
            t = info["trap"]
            prop = (f"Vanilla map plus ONE extra change: vanilla land province {t['province']} (state file "
                    f"'{t['state_file']}') is cut into {t['pieces']} pieces. The cut is chosen so that the game's "
                    f"centre calculation for strategic region {t['region']} ('{t['region_file']}') divides by zero "
                    "under the first model AND under the corrected 2-pixel-grid model. (EXP-03-div0 cut a different "
                    "province of region 193: divisor 0 under the first model, +1 under the corrected one; it loaded.)")
            why = ("Tests the corrected model. If this crashes at the same place as EXP-03-24k, the 2-pixel-grid model "
                   "explains all three results (24k crash, div0 load, this crash). If it loads, a divisor of 0 is "
                   "still not enough for the crash and the model remains unconfirmed.")
            expected_result = (f"EXPECTED IN GAME: crash while loading with EXCEPTION_INT_DIVIDE_BY_ZERO at hoi4.exe "
                               f"offset 0x{CRASH_RVA:X} (0x7FF6129C4CDC in the 2026-09-29 dumps).")
            notes = [expected_result, values(t["model"], f"region {t['region']} in this build")] + notes
        return texts.readme(
            build_id, self.title_for(build_id), prop=prop, why=why, launch=launch, steps=steps, send=send,
            expected=self.expected(build_id).text, cannot=["EXP-03"], user_dir=ctx.user, notes=notes,
            cannot_extra=["Why the game stores province boxes on a 2-pixel grid (fitted to one crash dump; the code "
                          "that fills the boxes was not found), and how regions that wrap around the map edge are "
                          "handled: these probes use regions that do not wrap."])

    # -------------------------------------------------------------- check
    def check(self, ctx, build_id, out):
        v = ctx.vanilla
        key = self.key(build_id)
        vdef = v.definition
        n0 = vdef.n
        target = VARIANTS[key]
        probs = check_descriptor(self, build_id, out)
        try:
            d = Definition.parse(decode((out / "map/definition.csv").read_bytes()))
            pid = pid_from_rgb(read_bmp((out / "map/provinces.bmp").read_bytes()).pixels, d.colors())
        except (OSError, KitError) as e:
            return probs + [f"cannot read output: {e}"]
        n = d.n
        if target is None:                                 # div0/div0b: vanilla + 1..3 pieces of one province
            target = n - 1
            if key in TRAPS and not n0 < n <= n0 + max(TRAP_KS) - 1:
                probs.append(f"{n - 1} provinces, expected vanilla + 1..{max(TRAP_KS) - 1}")
            if key == LOCAL_VARIANT and not n0 < n:
                probs.append(f"{n - 1} provinces, expected more than vanilla")
        if n - 1 != target:
            probs.append(f"{n - 1} provinces, expected {target}")
        van = np.asarray(v.pid)
        # refinement: every output province lies inside exactly one vanilla province
        key64 = pid.astype(np.int64) * (1 << 20) + van
        uk = np.unique(key64)
        pids, vids = uk >> 20, uk & ((1 << 20) - 1)
        if len(np.unique(pids)) != len(pids):
            probs.append("some output province spans several vanilla provinces")
        root = np.zeros(n, dtype=np.int64)
        root[pids] = vids
        if (root[1:n0] != np.arange(1, n0)).any():
            probs.append("a vanilla ID moved to a different place")
        types_v = v.types
        types = np.array([types_v[r] for r in root], dtype=np.int8)
        if (types[n0:] != LAND).any():
            probs.append("a new province is not a piece of a land province")
        # strategic-region centre (P00b-f3, conservative model): only the recorded / intended regions may fail
        # the guard (unsafe, or wrapping + fallback without an identical vanilla twin)
        region_of = region_lookup(v, n0)
        cs = centres_of(pid, root, region_of)
        fails = guard_failures(cs, vanilla_centres(van, region_of))
        if key in TRAPS:
            parents = sorted(set(root[n0:].tolist()))
            want_fails = sorted({int(region_of[p]) for p in parents})
            if len(parents) != 1:
                probs.append(f"{key}: new pieces come from {len(parents)} provinces, expected exactly one")
            elif not all(cs[r].fallback_all and cs[r].dx == 0 for r in want_fails):
                probs.append(f"{key}: region {want_fails} is not the observed dx == 0 case under every convention")
            elif key == TRAP2_VARIANT and not all(cs[r].crash_g2 for r in want_fails):
                probs.append(f"{key}: region {want_fails} does not divide by zero under the grid model")
        elif key == LOCAL_VARIANT:
            parents = sorted(set(root[n0:].tolist()))
            want_fails = KNOWN_UNSAFE[key]
            if sorted({int(region_of[p]) for p in parents}) != [LOCAL_REGION]:
                probs.append(f"{key}: split provinces outside region {LOCAL_REGION}")
            c = cs.get(LOCAL_REGION)
            if c is None or c.signature != LOCAL_SIGNATURE:
                probs.append(f"{key}: region {LOCAL_REGION}'s member boxes differ from EXP-03-{LOCAL_SOURCE}")
            elif not (c.mean == c.mean_g2 == DUMP_MEAN and c.rect == c.rect_g2 == DUMP_RECT and c.dx == 0
                      and c.fallback_all and c.crash_g2):
                probs.append(f"{key}: region {LOCAL_REGION} does not reproduce the dump numbers")
        else:
            want_fails = KNOWN_UNSAFE.get(key, [])
        seen_loading = OBSERVED_LOADING.get(key) == mod_tree_sha256(out)     # these exact bytes loaded in game
        if fails != want_fails and not seen_loading:
            probs.append(f"regions failing the region-centre guard: {fails}, expected {want_fails}")
        # definition rows
        for i in range(1, n):
            r, pr = d.rows[i], vdef.rows[int(root[i])]
            if i < n0 and (r[:5] != pr[:5] or r[6:] != pr[6:]):
                probs.append(f"definition row {i} changed beyond the coastal column")
                break
            if i >= n0 and (r[4] != "land" or r[6:8] != pr[6:8]):
                probs.append(f"definition row {i}: type/terrain/continent not inherited from {root[i]}")
                break
        coast = coastal_flags(pid, types)
        bad = [i for i in range(1, n) if types[i] == LAND and (d.rows[i][5] == "true") != coast[i]]
        if bad:
            probs.append(f"coastal flags not recomputed for {bad[:10]}")
        a = areas(pid, n)
        small = sorted(int(x) for x in np.nonzero(a[1:] < 8)[0] + 1)
        want_small = [target - 2, target - 1] if key == SMALL_VARIANT else []
        if small != want_small:
            probs.append(f"provinces under 8 px: {small}, expected {want_small}")
        if key == SMALL_VARIANT and [int(a[i]) for i in (target - 2, target - 1, target)] != list(SMALL_SIZES):
            probs.append("EXP-04 provinces are not exactly 6, 7 and 8 px")
        if len(x_crossings(pid)[0]):
            probs.append("X-crossings present")
        # provinces named in adjacencies.csv (straits, canals, impassable borders) keep their vanilla pixels,
        # so every strait keeps its From/To-Through contact
        adj = np.array(sorted(adjacency_ids(v.text("map/adjacencies.csv"))), dtype=np.int64)
        m = np.isin(van, adj)
        if not np.array_equal(np.isin(pid, adj), m) or (pid[m] != van[m]).any():
            probs.append("a province named in adjacencies.csv changed shape")
        # states / regions: children appended to the parent's file, nothing else
        pstate, pregion = v.province_state, v.province_region
        exp_state, exp_region = defaultdict(list), defaultdict(list)
        for i in range(n0, n):
            exp_state[pstate[int(root[i])][1]].append(i)
            exp_region[pregion[int(root[i])][1]].append(i)
        expected_files = {"map/provinces.bmp", "map/definition.csv", "map/buildings.txt", "map/unitstacks.txt"}
        for folder, src, exp in (("history/states/", v.state_files, exp_state),
                                 ("map/strategicregions/", v.region_files, exp_region)):
            for f, ids in exp.items():
                expected_files.add(folder + f)
                p = out / (folder + f)
                if not p.is_file() or decode(p.read_bytes()) != append_ids(src[f], "provinces", ids):
                    probs.append(f"{folder}{f}: not exactly vanilla + children {ids[:5]}")
        # railways
        rp = out / "map/railways.txt"
        if rp.is_file():
            expected_files.add("map/railways.txt")
            vr = split_lines(v.text("map/railways.txt"))[0]
            gr = split_lines(decode(rp.read_bytes()))[0]
            pairs = {tuple(p) for p in adjacency_pairs(pid).tolist()} | adjacency_links(v.text("map/adjacencies.csv"))
            if len(vr) != len(gr):
                probs.append("railways.txt line count changed")
            for a_, b_ in zip(vr, gr):
                va, ga = [int(x) for x in a_.split()], [int(x) for x in b_.split()]
                if va[0] != ga[0] or ga[1] != len(ga) - 2:
                    probs.append("railways.txt level/count mismatch")
                    break
                if [x for x in ga[2:] if x < n0] != va[2:]:
                    probs.append(f"railways.txt: line changed beyond inserted pieces: {a_[:40]}")
                    break
                if any((min(p, q), max(p, q)) not in pairs for p, q in zip(ga[2:], ga[3:])):
                    probs.append(f"railways.txt: non-adjacent step remains in {b_[:40]}")
                    break
        # buildings: per-province lines -> exactly one of each per land province (members regenerated)
        H, W = pid.shape
        bl = split_lines(decode((out / "map/buildings.txt").read_bytes()))[0]
        vl = split_lines(v.text("map/buildings.txt"))[0]
        vs = set(vl)
        fam_parents = set(int(root[i]) for i in range(n0, n))
        members = fam_parents | set(range(n0, n))
        count = defaultdict(int)
        for ln, px in zip(bl, position_pixels(bl, 2, 4, H, W)):
            s = ln.split(";")
            if ln not in vs:
                if s[1] not in PER_PROVINCE:
                    probs.append(f"buildings.txt: new non-provincial line {ln}")
                    break
                p = int(pid[px])
                if p not in members or int(s[0]) != pstate[int(root[p])][0]:
                    probs.append(f"buildings.txt: new line outside a split family: {ln}")
                    break
                if s[1] == "naval_base_spawn" and types[int(s[6])] != SEA:
                    probs.append("buildings.txt: naval_base_spawn without a sea province")
                    break
                count[(p, s[1])] += 1
        for m in members:
            for t in PER_LAND + (PER_COAST if coast[m] else ()):
                if count[(m, t)] != 1:
                    probs.append(f"buildings.txt: province {m} has {count[(m, t)]} '{t}' lines")
                    break
        # unitstacks: unaffected provinces keep their vanilla lines
        ul = split_lines(decode((out / "map/unitstacks.txt").read_bytes()))[0]
        vu = split_lines(v.text("map/unitstacks.txt"))[0]
        keep_v = [ln for ln in vu if int(ln.split(";")[0]) not in fam_parents]
        got_keep = [ln for ln in ul if int(ln.split(";")[0]) not in members]
        if keep_v != got_keep:
            probs.append("unitstacks.txt: lines of unaffected provinces changed")
        probs += check_file_set(out, expected_files)
        return probs
