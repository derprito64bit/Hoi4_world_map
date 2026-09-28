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
"""
from __future__ import annotations

import heapq
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
from scipy import ndimage

from . import texts
from .base import Expected, Experiment, check_descriptor, check_file_set
from .bmpio import read_bmp, write_bmp
from .common import KitError, decode, encode, fmt2, write_bytes
from .mapdata import (LAND, SEA, Definition, adjacency_ids, adjacency_links, adjacency_pairs, append_ids, areas, coast_points, coastal_flags,
                      fix_x_crossings, game_xz, height_at, interior_points, new_colors, pid_from_rgb, rgb_from_pid,
                      x_crossings)
from .positions import PER_COAST, PER_LAND, PER_PROVINCE, join_lines, position_pixels, split_lines

TARGETS = {"16k": 16000, "20k": 20000, "24k": 24000, "30k": 30000}
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
        return [f"EXP-03-{k}" for k in TARGETS]

    def key(self, build_id):
        return build_id.split("-")[-1]

    def title_for(self, build_id):
        k = self.key(build_id)
        t = f"{TARGETS[k]:,} provinces"
        return t + " + 6/7/8-px provinces (EXP-04)" if k == SMALL_VARIANT else t

    def expected(self, build_id):
        if self.key(build_id) == SMALL_VARIANT:
            return Expected(errors={"PROVINCE_TOO_SMALL"},
                            text="ERROR PROVINCE_TOO_SMALL for exactly the 6-px and 7-px test provinces (the 8-px one "
                                 "passes the 8-px floor); that is EXP-04. Otherwise " + texts.BASELINE_WARNS + ".")
        return Expected(text="No new finding: " + texts.BASELINE_WARNS + ".")

    # -------------------------------------------------------------- build
    def make(self, v, build_id):
        target = TARGETS[self.key(build_id)]
        small = SMALL_SIZES if self.key(build_id) == SMALL_VARIANT else ()
        van_pid = np.asarray(v.pid)
        types = v.types
        vdef = v.definition
        n0 = vdef.n
        H, W = van_pid.shape
        extra = target - (n0 - 1) - len(small)
        if extra <= 0:
            raise KitError("target below the vanilla province count")
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
        pid, root = subdivide(van_pid, types, extra, np.arange(n0), keep_pixel, coastal_needed, frozen=frozen)
        smalls = []
        if small:
            split_members = {i for i in range(n0, len(root))}
            pid, root, smalls = carve_small(pid, root, types, small, split_members)
        return pid, root, smalls

    def build(self, ctx, build_id, out: Path):
        v = ctx.vanilla
        pid, root, smalls = self.make(v, build_id)
        files = self.dependent_files(v, pid, root, smalls)
        for rel, data in files.items():
            write_bytes(out, rel, data)
        where = {i: v.province_state[int(root[i])][1].rsplit(".", 1)[0] for i, _, _, _ in smalls}
        return {"target": TARGETS[self.key(build_id)], "smalls": [(i, s) for i, _, s, _ in smalls],
                "where": where, "new": int(len(root) - v.definition.n)}

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

    # -------------------------------------------------------------- check
    def check(self, ctx, build_id, out):
        v = ctx.vanilla
        key = self.key(build_id)
        target = TARGETS[key]
        vdef = v.definition
        n0 = vdef.n
        probs = check_descriptor(self, build_id, out)
        try:
            d = Definition.parse(decode((out / "map/definition.csv").read_bytes()))
            pid = pid_from_rgb(read_bmp((out / "map/provinces.bmp").read_bytes()).pixels, d.colors())
        except (OSError, KitError) as e:
            return probs + [f"cannot read output: {e}"]
        n = d.n
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
