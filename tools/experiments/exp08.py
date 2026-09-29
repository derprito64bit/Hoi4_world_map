"""EXP-08: canvas above the community area ceiling (5632x2560 and 6144x2560).

The vanilla map is padded with open ocean: 512 rows at the TOP (both variants)
and, for 6144x2560, 512 columns at the RIGHT. Top/right padding was chosen
because game coordinates count x from the left and z from the bottom, so every
existing position (buildings, unit stacks, weather, adjacency arrows, the menu
camera) stays valid without being shifted. The new area is filled with new sea
provinces (brick tiles <= 176 px, inside the 180-px sea limit); all layers are
padded consistently, never stretched:

* provinces.bmp, heightmap (89), terrain (15 = ocean), rivers (254 = water),
  cities (15, the vanilla sea value), world_normal (flat 128,128,255, half size),
  trees.bmp (padded by the same map fraction: 150 rows / 150 columns, index 0)
* map/terrain DDS tied to the map size (P00 log section 4): colormap (BGRA),
  colormap_water_0/1/2 and fow_rgb_waterspec_a (DXT5; vanilla blocks copied
  bit-for-bit, padding = one uniform block of the median open-ocean colour;
  fow mip chain rebuilt from the padded level 0)
* definition.csv (new sea rows; coastal flags recomputed: the vanilla top row is
  Arctic land in places, which now touches the new ocean), new strategic regions
  (weather copied from the adjacent vanilla sea region), their localisation,
  weatherpositions and unitstacks for the new seas, and the coastal building
  positions / unit-stack types for land that became coastal.
Region-centre guard (P00b-f4, ``regioncentre.py``): no vanilla province gains or loses
a pixel (the padding is new provinces only; with top padding alone, a 3x4-px new sea
straddling the wrap seam above the old top edge avoids the seam X-crossing and has a
region of its own), every vanilla region keeps its members, boxes, mean, rect and
divisors (the wrap status is NOT compared: see below), and every new region's mean lies
>= 1 px inside a member box (``regiongroup.grow_regions``).
Wrap status at 6144 px: no vanilla wrapping region reaches the right edge W-1 any more.
For 112 that does not matter (its mean lies inside a member box), but the six that take
the fallback (88, 95, 96, 97, 178, 180) leave the engine's wrap path that vanilla was seen
loading with. The model rates five of them safe on the plain rect
(closest: 88 at dy 1) and one a known risk: region 178 (fallback, dy 0) fails the guard,
and no padding layout can change that (its members and boxes are vanilla's). Overwatch
accepted it for the owner run (P00b-f4 r2): ``KNOWN_RISK`` allows exactly that region
with exactly its vanilla member-box signature in EXP-08-6144x2560, and the README tells
the owner what to send back if the game crashes.
Expected validator finding: ERROR AREA_TOO_LARGE (the property under test).
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy import ndimage

from . import texts
from .base import Expected, Experiment, check_descriptor, check_file_set
from .bmpio import read_bmp, write_bmp
from .common import KitError, decode, encode, fmt2, write_bytes
from .dds import (Dds, bgra_to_rgba, dxt5_decode, dxt5_mip_chain, dxt5_pad_blocks, dxt5_uniform_block,
                  full_mip_count, read_dds, rgba_to_bgra, write_dds)
from .mapdata import (LAND, SEA, Definition, block_ids, coast_points, coastal_flags, find_block, fix_x_crossings,
                      game_to_pixel, game_xz,
                      interior_points, new_colors, pid_from_rgb, rgb_from_pid, x_crossings)
from .positions import PER_COAST, join_lines, split_lines
from .regioncentre import guard_problems, region_centres
from .regiongroup import grow_regions
from .tiling import tile

VARIANTS = {"5632x2560": (5632, 2560), "6144x2560": (6144, 2560)}
CELL_W, CELL_H = 176, 171
COLOR_SEED = 80008
FILL = {"map/heightmap.bmp": 89, "map/terrain.bmp": 15, "map/rivers.bmp": 254, "map/cities.bmp": 15}
NORMAL_FLAT = (128, 128, 255)
TREES_FILL = 0
DDS_FILES = ["map/terrain/colormap_rgb_cityemissivemask_a.dds", "map/terrain/colormap_water_0.dds",
             "map/terrain/colormap_water_1.dds", "map/terrain/colormap_water_2.dds",
             "map/terrain/fow_rgb_waterspec_a.dds"]
LOC = "localisation/english/p00b_exp08_l_english.yml"
DEFAULT_WEATHER_REGION = 46          # Barents Sea, if a tile touches no vanilla sea
COAST_STACK_TYPES = (19, 20)
SEAM_PATCH = (3, 2)                  # rows x columns per side of the seam patch province (box >= 3 px each way)
REGION_MAX = 24                      # padding provinces per new region
CRASH_RVA = 0x15A4CDC                # hoi4.exe 1.19.3 region-centre idiv (EXP-03-24k dumps, P00b-f3)
# Region-centre guard failures accepted as documented known risks (overwatch decision P00b-f4 r2, option b):
# {build id: {region id: (member-box signature, reason)}}. Matched by the exact signature: any other failure,
# or any change to these members' boxes, still fails --check and diag03.
KNOWN_RISK = {
    "EXP-08-6144x2560": {
        178: ("cbe28192ad55b4ec",
              "vanilla West Polynesia wraps the seam in vanilla (fallback, dy 0, loads); at 6144 px it and the five "
              "other vanilla wrapping regions (88, 95, 96, 97, 180; rated safe, closest 88 at dy 1) no longer touch "
              "the right edge, and its members and boxes are vanilla's, so no padding layout can change it. The "
              "observed crash divisor is dx (here -748); dy 0 is flagged only conservatively. The owner "
              "run decides it: a crash at hoi4.exe+0x15A4CDC means the dy division is real, a crash elsewhere "
              "points at the canvas size (or another cause), loading means dy 0 on the fallback is harmless."),
    },
}


def pad_array(a: np.ndarray, top: int, right: int, fill) -> np.ndarray:
    """Pad rows at the top and columns at the right with a constant (scalar or per-channel)."""
    H, W = a.shape[:2]
    out = np.empty((H + top, W + right) + a.shape[2:], dtype=a.dtype)
    out[...] = np.asarray(fill, dtype=a.dtype)
    out[top:, :W] = a
    return out


def open_sea_mask(pid: np.ndarray, types: np.ndarray, dist: int = 20) -> np.ndarray:
    """Sea pixels at least ``dist`` px from any non-sea pixel (sampling area for 'open ocean' colours)."""
    sea = types[pid] == SEA
    return ndimage.distance_transform_edt(sea) >= dist


def median_colour(rgba: np.ndarray, mask_full: np.ndarray) -> tuple:
    """Median RGBA of the texture pixels whose map area is open sea (mask subsampled to the texture size)."""
    h, w = rgba.shape[:2]
    H, W = mask_full.shape
    m = mask_full[(np.arange(h) * H) // h][:, (np.arange(w) * W) // w]
    return tuple(int(v) for v in np.median(rgba[m], axis=0).round())


def pad_provinces(pid: np.ndarray, types: np.ndarray, top: int, right: int, n0: int):
    """Padded pid with new sea IDs n0.. in the new area; returns (pid, number of new IDs).

    Padding pixels belong only to new provinces: no vanilla province gains or loses a pixel
    (a vanilla box change moves its region's centre, e.g. region 88 via province 2287 in P00b-f3).
    Only top padding keeps the canvas width: then the old top row meets the padding at the wrap
    seam, where two different vanilla provinces below and two padding pixels above form an
    X-crossing unless the two padding pixels are one province. That province is SEAM_PATCH
    (rows x columns on each side of the seam), a small new sea straddling the seam; it is the
    last new ID and gets a strategic region of its own (``seam_straddlers``).
    """
    H, W = pid.shape
    H1, W1 = H + top, W + right
    newmask = np.ones((H1, W1), dtype=bool)
    newmask[top:, :W] = False
    lab, k = tile(newmask, CELL_W, CELL_H)
    out = np.where(lab >= 0, lab.astype(np.int64) + n0, 0)
    out[top:, :W] = pid
    out = out.astype(np.int32)
    patch = None
    if top and not right and pid[0, 0] != pid[0, W - 1]:
        patch = n0 + k
        rows, cols = SEAM_PATCH
        out[top - rows:top, :cols] = patch
        out[top - rows:top, W1 - cols:] = patch
        k += 1
        if np.bincount(out[:top].ravel(), minlength=patch + 1)[n0:patch].min() == 0:
            raise KitError("the seam patch swallowed a padding tile")
    # a padding pixel may only take the ID of another padding province; the seam patch never gives pixels away
    fix_x_crossings(out, lambda a, b: a >= n0 and b >= n0 and a != b and a != patch)
    return out, k


def seam_straddlers(pid: np.ndarray, ids) -> list:
    """IDs among ``ids`` with pixels in column 0 and in column W-1 (sorted)."""
    W = pid.shape[1]
    left, right_ = set(np.unique(pid[:, 0]).tolist()), set(np.unique(pid[:, W - 1]).tolist())
    return sorted(int(i) for i in ids if i in left and i in right_)


def wrapped_width(pid: np.ndarray, i: int) -> int:
    """Width of province ``i``'s box, measured across the wrap seam when that is shorter (like validate_map.py)."""
    W = pid.shape[1]
    cols = np.unique(np.nonzero(pid == i)[1])
    if len(cols) == 0:
        return 0
    gaps = np.diff(np.concatenate([cols, [cols[0] + W]]))
    return int(W - (gaps.max() - 1))


def vanilla_pixel_problems(pid: np.ndarray, vpid: np.ndarray, top: int, n0: int) -> list:
    """Rule "no vanilla province changes its pixel set": the vanilla part is unchanged and every padding
    pixel carries a new ID (vanilla at rows top.., columns 0..W-1 of the padded map)."""
    H, W = vpid.shape
    probs = []
    if not np.array_equal(pid[top:top + H, :W], vpid):
        probs.append("the vanilla part of provinces.bmp changed (a vanilla province lost or changed pixels)")
    pad = np.ones(pid.shape, dtype=bool)
    pad[top:top + H, :W] = False
    got = pid[pad & (pid < n0)]
    if got.size:
        probs.append(f"no vanilla province may gain pixels: {got.size} padding pixels carry vanilla IDs "
                     f"{sorted(set(got.tolist()))[:5]}")
    return probs


def layered_regions(v, new_texts: dict) -> tuple:
    """({region id: sorted province ids}, [new region ids]) for vanilla's regions plus new region files."""
    regions = defaultdict(list)
    for p, (rid, _) in v.province_region.items():
        regions[rid].append(p)
    new_ids = []
    for name, t in sorted(new_texts.items()):
        m = re.search(r"\bid\s*=\s*(\d+)", re.sub(r"#[^\n]*", "", t))
        if m is None:
            raise KitError(f"strategic region {name}: no id")
        rid = int(m.group(1))
        if rid in regions:
            raise KitError(f"strategic region {name}: id {rid} is already used")
        regions[rid] = block_ids(t, "provinces")
        new_ids.append(rid)
    return {r: sorted(regions[r]) for r in sorted(regions)}, sorted(new_ids)


def vanilla_centres(v) -> dict:
    """Region centres of the vanilla map (a map observed loading), cached on the Vanilla object."""
    if getattr(v, "_region_centres", None) is None:
        regions, _ = layered_regions(v, {})
        v._region_centres = region_centres(np.asarray(v.pid), regions)
    return v._region_centres


def _centre_path(c) -> tuple:
    # the wrap status (c.seam) is deliberately not compared: it follows the canvas width (six vanilla regions
    # stop wrapping at 6144 px); guard_failures judges each region under its new status
    return (c.n, c.mean, c.rect, c.fallback, c.fallback_strict, c.fallback_all, c.dx, c.dy, c.margin, c.signature)


def centre_problems(v, pid: np.ndarray, new_texts: dict, known: dict | None = None,
                    notes: list | None = None) -> list:
    """Region-centre guard for a padded map: 0 guard failures (vanilla twins count for wrapping regions),
    every vanilla region's members, boxes, mean, rect and divisors identical to vanilla's (its wrap status
    may change with the canvas width: at 6144 px six wrapping regions stop wrapping; the guard judges them),
    every new region's mean >= 1 px inside a member box. ``known``: this build's KNOWN_RISK entries (their
    notes go to ``notes``)."""
    try:
        regions, new_ids = layered_regions(v, new_texts)
        cs = region_centres(pid, regions)
    except KitError as e:
        return [f"region-centre guard: {e}"]
    van = vanilla_centres(v)
    probs = guard_problems(cs, van, clear_ids=new_ids, known=known, notes=notes)
    moved = [r for r in sorted(van) if r not in cs or _centre_path(cs[r]) != _centre_path(van[r])]
    if moved:
        probs.append(f"region-centre guard: {len(moved)} vanilla regions changed their centre calculation "
                     f"(members or boxes): {moved[:10]}")
    return probs


def pad_dds(tmpl: Dds, top: int, right: int, fill_rgba) -> bytes:
    """Pad a DDS level 0 (top rows, right columns) and rebuild the mip chain if the file has one."""
    w, h = tmpl.width, tmpl.height
    nw, nh = w + right, h + top
    if not tmpl.compressed:
        rgba = bgra_to_rgba(tmpl.levels[0], w, h)
        return write_dds(tmpl, nw, nh, [rgba_to_bgra(pad_array(rgba, top, right, fill_rgba))])
    block = dxt5_uniform_block(fill_rgba)
    lvl0 = dxt5_pad_blocks(tmpl.levels[0], w, h, top, right, block)
    if len(tmpl.levels) == 1:
        return write_dds(tmpl, nw, nh, [lvl0])
    count = full_mip_count(nw, nh)
    return write_dds(tmpl, nw, nh, dxt5_mip_chain(dxt5_decode(lvl0, nw, nh), lvl0, count))


def weather_block(region_text: str) -> str:
    o, c = find_block(region_text, "weather", 1)
    start = region_text.rfind("\n", 0, o) + 1
    return region_text[start:c + 1]


def region_file(rid: int, name: str, ids, weather: str, naval: str) -> str:
    body = " ".join(str(i) for i in ids)
    return (f"strategic_region={{\n\tid={rid}\n\tname=\"STRATEGICREGION_{rid}\"\n\tprovinces={{\n\t\t{body} \n\t}}\n"
            f"\tnaval_terrain={naval}\n{weather}\n}}\n")


class Exp08(Experiment):
    exp_id = "EXP-08"
    title = "canvas above the area ceiling"
    priority = 8

    def build_ids(self, ctx):
        return [f"EXP-08-{k}" for k in VARIANTS]

    def title_for(self, build_id):
        return f"canvas {build_id.split('-')[-1]} (ocean padding)"

    def expected(self, build_id):
        w, h = VARIANTS[build_id.split("-")[-1]]
        return Expected(errors={"AREA_TOO_LARGE"},
                        text=f"ERROR AREA_TOO_LARGE ({w}x{h} = {w * h:,} px > 13,238,272); that is the property "
                             "under test. Otherwise " + texts.BASELINE_WARNS + ".")

    def pads(self, v, build_id):
        W1, H1 = VARIANTS[build_id.split("-")[-1]]
        H, W = v.shape
        return H1 - H, W1 - W

    # ------------------------------------------------------------ build
    def make(self, v, build_id) -> dict:
        top, right = self.pads(v, build_id)
        vpid = np.asarray(v.pid)
        H, W = vpid.shape
        vdef = v.definition
        n0 = vdef.n
        types_v = v.types
        pid, k = pad_provinces(vpid, types_v, top, right, n0)
        n = n0 + k
        types = np.concatenate([types_v, np.full(k, SEA, dtype=np.int8)])
        H1, W1 = pid.shape
        files = {}
        # definition
        d = vdef.copy()
        cols = new_colors(vdef.colors(), k, COLOR_SEED)
        coast = coastal_flags(pid, types)
        for j in range(k):
            i = n0 + j
            d.rows.append([str(i), *map(str, cols[j]), "sea", "true" if coast[i] else "false", "ocean", "0"])
        newly = []
        for i in range(1, n0):
            if types[i] == LAND and coast[i] != (vdef.rows[i][5] == "true"):
                if not coast[i]:
                    raise KitError(f"province {i} would lose its coast")
                d.rows[i][5] = "true"
                newly.append(i)
        files["map/definition.csv"] = encode(d.format())
        files["map/provinces.bmp"] = write_bmp(v.provinces_bmp, rgb_from_pid(pid, d.colors()))
        # same-size rasters
        for rel, val in FILL.items():
            b = v.bmp(rel)
            files[rel] = write_bmp(b, pad_array(b.pixels, top, right, val))
        nb = v.bmp("map/world_normal.bmp")
        files["map/world_normal.bmp"] = write_bmp(nb, pad_array(nb.pixels, top // 2, right // 2, NORMAL_FLAT))
        tb = v.bmp("map/trees.bmp")
        tt, tr = top * tb.height // H, right * tb.width // W
        if tt * H != top * tb.height or tr * W != right * tb.width:
            raise KitError("trees.bmp padding is not a whole number of pixels")
        files["map/trees.bmp"] = write_bmp(tb, pad_array(tb.pixels, tt, tr, TREES_FILL))
        # DDS
        sea_open = open_sea_mask(vpid, types_v)
        for rel in DDS_FILES:
            t = read_dds(v.bytes(rel))
            f = t.width / W
            dt, dr = int(round(top * f)), int(round(right * f))
            rgba0 = dxt5_decode(t.levels[0], t.width, t.height) if t.compressed else bgra_to_rgba(t.levels[0], t.width, t.height)
            files[rel] = pad_dds(t, dt, dr, median_colour(rgba0, sea_open))
        # regions, weather positions, localisation
        centre = interior_points(pid, range(n0, n))
        groups = self.region_groups(pid, n0, n, types, v)
        wlines, wtr = split_lines(v.text("map/weatherpositions.txt"))
        loc = ["﻿l_english:"]
        rid0 = max(int(r) for r, _ in v.province_region.values()) + 1
        for g, (ids, src_file) in enumerate(groups):
            rid = rid0 + g
            src = v.region_files[src_file]
            m = re.search(r"naval_terrain\s*=\s*(\w+)", src)
            name = f"EXP-08 padding {g + 1}"
            files[f"map/strategicregions/{rid}-{name}.txt"] = encode(
                region_file(rid, name, ids, weather_block(src), m.group(1) if m else "water_deep_ocean"))
            loc.append(f' STRATEGICREGION_{rid}:0 "{name}"')
            r, c = centre[ids[len(ids) // 2]]
            x, z = game_xz(r, c, H1)
            wlines.append(f"{rid};{fmt2(x)};9.50;{fmt2(z)};big")
        files["map/weatherpositions.txt"] = encode(join_lines(wlines, wtr))
        files[LOC] = encode("\n".join(loc) + "\n")
        # unitstacks: new seas get the most common vanilla sea set; newly coastal land gets types 19/20
        ul, utr = split_lines(v.text("map/unitstacks.txt"))
        per = defaultdict(dict)
        for ln in ul:
            s = ln.split(";")
            per[int(s[0])][int(s[1])] = (s[5], s[6])
        sea_sets = Counter(tuple(sorted(per[p])) for p in per if types_v[p] == SEA)
        best = sea_sets.most_common(1)[0][0]
        tmpl_sea = per[min(p for p in per if types_v[p] == SEA and tuple(sorted(per[p])) == best)]
        coast_tmpl = per[min(p for p in per if types_v[p] == LAND and vdef.rows[p][5] == "true"
                             and set(COAST_STACK_TYPES) <= set(per[p]))]
        add = []
        cpts = coast_points(pid, types, newly, interior_points(pid, newly)) if newly else {}
        for i in range(n0, n):
            r, c = centre[i]
            x, z = game_xz(r, c, H1)
            for t in best:
                ro, off = tmpl_sea[t]
                add.append(f"{i};{t};{fmt2(x)};9.50;{fmt2(z)};{ro};{off}")
        for i in newly:
            if not per.get(i):
                continue
            r, c, _ = cpts[i]
            x, z = game_xz(r, c, H1)
            for t in COAST_STACK_TYPES:
                if t not in per[i]:
                    ro, off = coast_tmpl[t]
                    add.append(f"{i};{t};{fmt2(x)};9.50;{fmt2(z)};{ro};{off}")
        files["map/unitstacks.txt"] = encode(join_lines(ul + add, utr))
        # buildings: coastal set for land that became coastal
        bl, btr = split_lines(v.text("map/buildings.txt"))
        pstate = v.province_state
        badd = []
        for i in newly:
            r, c, sea_id = cpts[i]
            x, z = game_xz(r, c, H1)
            sid = pstate[i][0]
            for t in PER_COAST:
                extra = sea_id if t == "naval_base_spawn" else (i if t == "floating_harbor" else 0)
                badd.append(f"{sid};{t};{fmt2(x)};9.50;{fmt2(z)};0.00;{extra}")
        files["map/buildings.txt"] = encode(join_lines(bl + badd, btr))
        return {"files": files, "new": k, "newly_coastal": newly, "regions": len(groups), "top": top,
                "right": right, "seam_patch": seam_straddlers(pid, range(n0, n)),
                # vanilla wrapping regions on the fallback path (88, 95, 96, 97, 178, 180): with right padding none
                # of them reaches the new edge W-1 any more (112 wraps too, but its mean lies inside a member box)
                "wrap_lost": sorted(r for r, c in vanilla_centres(v).items() if c.unknown) if right else []}

    def region_groups(self, pid, n0, n, types, v):
        """Pad provinces grouped into compact regions of <= REGION_MAX whose mean lies >= 1 px inside a member
        box and which never reach both image edges (``regiongroup.grow_regions``); a seam-straddling patch is a
        region of its own. Weather source = the adjacent vanilla sea region (most shared border)."""
        H1, W1 = pid.shape
        straddle = seam_straddlers(pid, range(n0, n))
        groups = grow_regions(pid, [i for i in range(n0, n) if i not in straddle], max_members=REGION_MAX)
        groups = sorted(groups + [[i] for i in straddle])
        # vanilla neighbours of each pad province
        pw = np.concatenate([pid, pid[:, :1]], axis=1)
        a = np.concatenate([pw[:, :-1].ravel(), pid[:-1].ravel()])
        b = np.concatenate([pw[:, 1:].ravel(), pid[1:].ravel()])
        m = ((a >= n0) & (b < n0)) | ((b >= n0) & (a < n0))
        nbr = defaultdict(Counter)
        for p, q in zip(a[m].tolist(), b[m].tolist()):
            pad, van = (p, q) if p >= n0 else (q, p)
            if types[van] == SEA:
                nbr[pad][v.province_region[van][1]] += 1
        default = next(f for f in sorted(v.region_files) if f.startswith(f"{DEFAULT_WEATHER_REGION}-"))
        out = []
        for g in groups:
            c = Counter()
            for i in g:
                c.update(nbr.get(i, {}))
            src = sorted(c.items(), key=lambda t: (-t[1], t[0]))[0][0] if c else default
            out.append((sorted(g), src))
        return out

    def build(self, ctx, build_id, out: Path):
        res = self.make(ctx.vanilla, build_id)
        for rel, data in sorted(res["files"].items()):
            write_bytes(out, rel, data)
        return {k: v for k, v in res.items() if k != "files"}

    def readme(self, ctx, build_id, info):
        w, h = VARIANTS[build_id.split("-")[-1]]
        added = f"{info['top']} rows of open ocean at the top" + (
            f" and {info['right']} columns at the right" if info["right"] else "")
        patch = ", ".join(map(str, info.get("seam_patch") or []))
        canvas_ = (f"The map canvas is {w}x{h} pixels ({w * h / 1e6:.1f} million; vanilla 5632x2048 = 11.5 million, "
                   f"the community ceiling is 13.24 million). The normal world is unchanged; {added} are added, split "
                   f"into {info['new']} new sea provinces. Every map layer is padded to match (nothing is stretched).")
        crash = ["If the game crashes: open the newest folder in Documents/Paradox Interactive/Hearts of Iron IV/"
                 "crashes/ and copy two lines from exception.txt: the line that starts with 'Unhandled Exception' "
                 "and the first line of the stack below it (overwatch can also read the folder directly).",
                 "If it crashes: does Documents/Paradox Interactive/Hearts of Iron IV/logs/game.log contain a line "
                 "'Loaded N provinces' (yes/no; copy it if yes)?"]
        if patch:
            crash.append(f"Every error.log line that contains 'BOX' or '{patch}' (say 'none' if there is none).")
        wraps = ", ".join(map(str, info.get("wrap_lost") or []))
        return texts.readme(
            build_id, self.title_for(build_id),
            heading=("THE TWO THINGS THIS TEST CHANGES (compared with the normal game)" if patch else
                     "THE ONE THING THIS TEST CHANGES (compared with the normal game)"),
            prop=(f"1. {canvas_}\n2. Sea province {patch} is the first province in any of our tests that crosses the "
                  "left/right map edge (the wrap seam); the normal game has none. Provinces that span the seam are a "
                  "known failure mode ('TOO LARGE BOX'). It is needed here: see GOOD TO KNOW." if patch else canvas_),
            why="Tells us whether the engine accepts a map bigger than anything published (DEC-020: a bigger canvas "
                "is allowed only if this loads), and whether textures or fog of war get misaligned on a new size.",
            launch=texts.LAUNCH_NORMAL,
            steps=["If the main menu appears: start a new game with any country and pause.",
                   "Pan to all four map edges (far north above the Arctic, far south, far west, far east) and to "
                   "the old top edge of the vanilla map (the Arctic coast). Take a screenshot at each at medium zoom.",
                   "Look for: land textures or colours that do not line up with coastlines/borders, fog of war in "
                   "the wrong place, black or stretched areas, flickering. A straight colour line where the added "
                   "ocean starts is expected (the new ocean is one flat colour) and is not an engine problem.",
                   "Unpause and let a few days pass."],
            send=["Loaded: yes / no; loading time (seconds).",
                  "Screenshots of the edges; describe anything misaligned or stretched.",
                  "Did the game run normally for a few days (yes/no)?"] + crash,
            expected=self.expected(build_id).text, cannot=["EXP-08"], user_dir=ctx.user,
            notes=["Fog-of-war texture: the full-size level keeps the normal game's data exactly, but its smaller "
                   "zoom levels are recomputed by the kit for the whole map. Slight blockiness of fog/water shine at "
                   "far zoom, over the WHOLE map, would come from that, not from the canvas size; say where you see it.",
                   "No shader or constants.fxh change is included: P00 found no map-size constant there "
                   "(the engine supplies MAP_SIZE_X/Y).",
                   f"{len(info['newly_coastal'])} Arctic land provinces on the old top edge now touch the new ocean "
                   "and became coastal; they got port/coastal positions like every other coast."]
            + ([f"Sea province {patch} is a tiny new sea (3 rows x 4 columns) "
                "that crosses the left/right map edge just above the old top edge: two different vanilla seas meet "
                "there at the edge, and without it four provinces would meet at one corner (not allowed), or a "
                "vanilla sea would have to grow into the new ocean (that would move its strategic region's centre, "
                "the EXP-03-24k crash mechanism). It has a strategic region of its own. A 'TOO LARGE BOX' or "
                "similar line for this province in error.log would come from it crossing the edge, not from the "
                f"canvas size: report it. If the game crashes, the crash may come from province {patch} rather "
                "than from the map size; the crash lines asked for above help tell the two apart."] if patch else [])
            + ([f"Known risk in this build: the Pacific strategic regions {wraps} used to wrap around the "
                "left/right map edge (the game may compute a wrapping region's centre differently); with the extra "
                "columns at the right none of them wraps any more. The kit's offline check rates "
                f"{len(info.get('wrap_lost') or []) - len(KNOWN_RISK[build_id])} of them safe and one, region "
                f"{', '.join(map(str, KNOWN_RISK[build_id]))} (West Polynesia), a known risk: the game may divide "
                "by zero while computing that region's centre. A "
                f"crash at hoi4.exe+0x{CRASH_RVA:X} (that address appears in the exception line) is this "
                "region-centre problem, NOT the map size. A crash at any other address points at the map size or "
                "something else. If it loads, this risk is harmless. Every outcome is useful: just send the lines "
                "asked for above."] if KNOWN_RISK.get(build_id) else []))

    # ------------------------------------------------------------ check
    def check_added(self, v, pid, types, newly, n0, n, added, region_files, H1) -> list:
        """The appended lines must be exactly: one weather line per new region; the commonest vanilla sea
        stack set for every padding sea plus the missing coastal types 19/20 for newly coastal land; and
        every coastal building type once for every newly coastal land province."""
        probs = []
        W1 = pid.shape[1]
        rids = sorted(int(p.name.split("-")[0]) for p in region_files)
        got_w = sorted(int(ln.split(";")[0]) for ln in added["map/weatherpositions.txt"])
        if got_w != rids:
            probs.append(f"weatherpositions.txt: added lines for regions {got_w[:8]}, expected one per new region {rids[:8]}")
        per = defaultdict(set)
        for ln in split_lines(v.text("map/unitstacks.txt"))[0]:
            s_ = ln.split(";")
            per[int(s_[0])].add(int(s_[1]))
        best = set(Counter(tuple(sorted(per[p])) for p in per if v.types[p] == SEA).most_common(1)[0][0])
        want_u = Counter()
        for i in range(n0, n):
            for t in best:
                want_u[(i, t)] += 1
        for i in newly:
            if per.get(i):
                for t in COAST_STACK_TYPES:
                    if t not in per[i]:
                        want_u[(i, t)] += 1
        got_u = Counter((int(ln.split(";")[0]), int(ln.split(";")[1])) for ln in added["map/unitstacks.txt"])
        if got_u != want_u:
            extra, missing = got_u - want_u, want_u - got_u
            probs.append(f"unitstacks.txt: unexpected added lines {sorted(extra)[:5]}, missing {sorted(missing)[:5]}")
        pstate = v.province_state
        want_b = Counter((i, t) for i in newly for t in PER_COAST)
        got_b = Counter()
        for ln in added["map/buildings.txt"]:
            s_ = ln.split(";")
            try:
                c, r = game_to_pixel(float(s_[2]), float(s_[4]), H1)
                p = int(pid[r, c % W1])
                ok = (s_[1] in PER_COAST and p in newly and int(s_[0]) == pstate[p][0]
                      and (s_[1] != "naval_base_spawn" or int(s_[6]) >= n0)
                      and (s_[1] != "floating_harbor" or int(s_[6]) == p))
            except (ValueError, IndexError, KeyError):
                ok = False
            if not ok:
                probs.append(f"buildings.txt: unexpected added line {ln}")
                break
            got_b[(p, s_[1])] += 1
        if got_b != want_b:
            probs.append(f"buildings.txt: coastal lines of newly coastal provinces are not exactly one per type "
                         f"(missing {sorted(want_b - got_b)[:5]}, extra {sorted(got_b - want_b)[:5]})")
        return probs

    def check(self, ctx, build_id, out):
        v = ctx.vanilla
        top, right = self.pads(v, build_id)
        W1, H1 = VARIANTS[build_id.split("-")[-1]]
        H, W = v.shape
        n0 = v.definition.n
        probs = check_descriptor(self, build_id, out)
        try:
            d = Definition.parse(decode((out / "map/definition.csv").read_bytes()))
            pb = read_bmp((out / "map/provinces.bmp").read_bytes())
            pid = pid_from_rgb(pb.pixels, d.colors())
        except (OSError, KitError) as e:
            return probs + [f"cannot read output: {e}"]
        if pid.shape != (H1, W1):
            return probs + [f"provinces.bmp is {pid.shape[1]}x{pid.shape[0]}"]
        pad = np.ones(pid.shape, dtype=bool)
        pad[top:, :W] = False
        probs += vanilla_pixel_problems(pid, np.asarray(v.pid), top, n0)
        vd = v.definition
        types = d.types()
        coast = coastal_flags(pid, types)
        for i in range(1, d.n):
            r = d.rows[i]
            if i < n0:
                if r[:5] != vd.rows[i][:5] or r[6:] != vd.rows[i][6:]:
                    probs.append(f"definition row {i} changed beyond the coastal flag")
                    break
                if r[5] != vd.rows[i][5] and not (r[4] == "land" and coast[i] and r[5] == "true"):
                    probs.append(f"definition row {i}: coastal flag changed without reason")
                    break
            elif r[4:] != ["sea", "true" if coast[i] else "false", "ocean", "0"]:
                probs.append(f"definition row {i} is not a correct padding sea")
                break
        if len(x_crossings(pid)[0]):
            probs.append("X-crossings present")
        from .mapdata import bboxes
        bb = bboxes(pid, d.n)
        wide = np.asarray(bb[1] - bb[0] + 1)
        for i in seam_straddlers(pid, range(n0, d.n)):
            wide[i] = wrapped_width(pid, i)            # the seam patch: measured across the seam
        sides = np.maximum(wide, bb[3] - bb[2] + 1)[n0:]
        if (sides > 180).any():
            probs.append("a padding province exceeds 180 px")
        for rel, val in FILL.items():
            got = read_bmp((out / rel).read_bytes())
            van = v.bmp(rel)
            if got.pixels.shape != (H1, W1) or not np.array_equal(got.pixels[top:, :W], van.pixels) \
                    or (got.pixels[pad] != val).any() or got.palette != van.palette or got.dib_size != van.dib_size:
                probs.append(f"{rel}: not vanilla + constant padding")
        got = read_bmp((out / "map/world_normal.bmp").read_bytes())
        van = v.bmp("map/world_normal.bmp")
        if got.pixels.shape[:2] != (H1 // 2, W1 // 2) or not np.array_equal(got.pixels[top // 2:, :W // 2], van.pixels):
            probs.append("world_normal.bmp: not vanilla + flat padding at half size")
        got = read_bmp((out / "map/trees.bmp").read_bytes())
        van = v.bmp("map/trees.bmp")
        tt, tr = top * van.height // H, right * van.width // W
        if got.pixels.shape != (van.height + tt, van.width + tr) or \
                not np.array_equal(got.pixels[tt:, :van.width], van.pixels) or got.palette != van.palette:
            probs.append("trees.bmp: not vanilla + padding in proportion")
        for rel in DDS_FILES:
            t = read_dds(v.bytes(rel))
            g = read_dds((out / rel).read_bytes())
            f = t.width / W
            dt, dr = int(round(top * f)), int(round(right * f))
            if (g.width, g.height) != (t.width + dr, t.height + dt) or g.fourcc != t.fourcc:
                probs.append(f"{rel}: wrong size or format")
                continue
            if t.compressed:
                bw = t.width // 4
                gl = np.frombuffer(g.levels[0], np.uint8).reshape(g.height // 4, g.width // 4, 16)
                tl = np.frombuffer(t.levels[0], np.uint8).reshape(t.height // 4, bw, 16)
                if not np.array_equal(gl[dt // 4:, :bw], tl):
                    probs.append(f"{rel}: vanilla blocks changed")
                if len(t.levels) > 1 and len(g.levels) != full_mip_count(g.width, g.height):
                    probs.append(f"{rel}: incomplete mip chain")
            else:
                a = bgra_to_rgba(g.levels[0], g.width, g.height)
                if not np.array_equal(a[dt:, :t.width], bgra_to_rgba(t.levels[0], t.width, t.height)):
                    probs.append(f"{rel}: vanilla pixels changed")
            hdr_t, hdr_g = bytearray(t.header), bytearray(g.header)
            for off in (12, 16, 20, 28):
                hdr_t[off:off + 4] = hdr_g[off:off + 4] = b"\0\0\0\0"
            if hdr_t != hdr_g:
                probs.append(f"{rel}: header flags/format differ from vanilla")
        # regions: every padding province exactly once, only new region files
        region_files = sorted(p for p in (out / "map/strategicregions").glob("*.txt"))
        seen = Counter()
        for p in region_files:
            if p.name in v.region_files:
                probs.append(f"vanilla region {p.name} overridden")
            from .mapdata import block_ids
            seen.update(block_ids(decode(p.read_bytes()), "provinces"))
        if set(seen) != set(range(n0, d.n)) or any(c != 1 for c in seen.values()):
            probs.append("padding provinces are not each in exactly one new region")
        # region-centre guard (P00b-f4): vanilla regions keep their centre path, new regions never fall back
        probs += centre_problems(v, pid, {p.name: decode(p.read_bytes()) for p in region_files},
                                 known=KNOWN_RISK.get(build_id), notes=getattr(self, "check_notes", None))
        # appended-only text files, and exactly the expected appended lines
        added = {}
        for rel in ("map/weatherpositions.txt", "map/unitstacks.txt", "map/buildings.txt"):
            van_l = split_lines(v.text(rel))[0]
            got_l = split_lines(decode((out / rel).read_bytes()))[0]
            if got_l[:len(van_l)] != van_l:
                probs.append(f"{rel}: vanilla lines changed (only appending is allowed)")
            added[rel] = got_l[len(van_l):]
        newly = {i for i in range(1, n0) if d.rows[i][5] != vd.rows[i][5]}
        probs += self.check_added(v, pid, types, newly, n0, d.n, added, region_files, H1)
        expected = {"map/definition.csv", "map/provinces.bmp", "map/world_normal.bmp", "map/trees.bmp",
                    "map/weatherpositions.txt", "map/unitstacks.txt", "map/buildings.txt", LOC} | set(FILL) | set(DDS_FILES)
        expected |= {p.relative_to(out).as_posix() for p in region_files}
        probs += check_file_set(out, expected)
        return probs
