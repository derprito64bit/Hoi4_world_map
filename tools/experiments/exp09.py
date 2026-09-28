"""EXP-09: edge-look prototype on the project canvas 5120x2304 (synthetic world, see synth.py).

One mod per variant of the P00c manifest (``assets/gfx/FX/experiments/EXP-09/
variants.json``; contract in docs/logs/P00b.md section 1). Every variant carries
the same synthetic map: the Equal Earth off-globe area as lake provinces with
heightmap 89 and the ocean colormap tone. Variant extras:
* defines: each listed .lua copied to ``common/defines/<its basename>`` (zz_* sorts
  after vanilla 00_*/01_*);
* shader patches: the vanilla file named in each entry is read from the game
  install, patched with ``patchspec.apply_patch`` (anchors unique at apply time,
  list order) and written to the same relative path.
If the manifest is absent, only the baseline (EXP-09a) is built.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from . import texts
from .base import Expected, Experiment, check_descriptor, check_file_set
from .bmpio import read_bmp, write_bmp
from .common import KitError, decode, ee_project, encode, fmt2, safe_join, write_bytes
from .dds import (bgra_to_rgba, dxt5_decode, dxt5_encode, dxt5_mip_chain, dxt5_uniform_block, full_mip_count,
                  read_dds, rgba_to_bgra, write_dds)
from .exp08 import median_colour, open_sea_mask, region_file, weather_block
from .mapdata import (LAKE, LAND, SEA, Definition, block_ids, coast_points, coastal_flags, game_xz, interior_points,
                      new_colors, pid_from_rgb, rgb_from_pid, x_crossings)
from .patchspec import BASELINE_ONLY, load_manifest, patched_files
from .positions import PER_COAST, PER_LAND, PER_PROVINCE, join_lines, split_lines
from .synth import Params, layout

W, H = 5120, 2304
LON0, LAT_MIN, LAT_MAX = 10.9, -60.0, 90.0
LAND_H, WATER_H = 100, 89
T_LAND, T_WATER = 0, 15
R_LAND, R_WATER = 255, 254
CITIES = 15
COLOR_SEED = 90009
WEATHER_SRC = "112-"                    # Far South Pacific: weather for the new sea and filler regions
REGION_CHUNK = 40
LOC = "localisation/english/p00b_exp09_l_english.yml"
COAST_STACK = (19, 20)
# (state id, lon, lat, align, description) - landmark states at their real projected positions
ANCHORS = [(822, -169.65, 66.08, "right", "Chukotka at Cape Dezhnev (upper right, on the curved edge)"),
           (463, -168.09, 65.64, "left", "Alaska at Cape Prince of Wales (upper left, on the curved edge)"),
           (101, -33.4, 82.5, "center", "Greenland in the far north (top edge, left of centre)"),
           (953, -67.27, -55.98, "center", "Tierra del Fuego at Cape Horn (bottom edge, left of centre)")]
DDS = {"colormap": "map/terrain/colormap_rgb_cityemissivemask_a.dds",
       "water": ["map/terrain/colormap_water_0.dds", "map/terrain/colormap_water_1.dds",
                 "map/terrain/colormap_water_2.dds"],
       "fow": "map/terrain/fow_rgb_waterspec_a.dds"}


BASE_FILES = ["map/definition.csv", "map/provinces.bmp", "map/heightmap.bmp", "map/terrain.bmp", "map/rivers.bmp",
              "map/cities.bmp", "map/world_normal.bmp", "map/trees.bmp", DDS["colormap"], *DDS["water"], DDS["fow"],
              "map/adjacencies.csv", "map/buildings.txt", "map/unitstacks.txt", "map/weatherpositions.txt",
              "map/railways.txt", LOC]


def canvas():
    ee = ee_project()
    return ee.Canvas(W, H, LON0, LAT_MIN, LAT_MAX)


class Exp09(Experiment):
    exp_id = "EXP-09"
    title = "edge look on the Equal Earth canvas (synthetic world)"
    priority = 9

    def __init__(self):
        self._base = None

    # ------------------------------------------------------------ variants
    def variants(self, ctx):
        m = load_manifest(ctx.repo_root)
        return m if m is not None else [BASELINE_ONLY]

    def build_ids(self, ctx):
        return [f"EXP-09{v.id}" for v in self.variants(ctx)]

    def variant(self, ctx, build_id):
        vid = build_id[len("EXP-09"):]
        for v in self.variants(ctx):
            if v.id == vid:
                return v
        raise KitError(f"EXP-09 has no variant {vid!r}")

    def title_for(self, build_id):
        return f"edge look, variant {build_id[len('EXP-09'):]}"

    def expected(self, build_id):
        return Expected(warns={"DEF_SEA_CONTINENT", "STATE_CATEGORY_DUP"},
                        text="0 ERROR. WARN only DEF_SEA_CONTINENT (vanilla's sea province 5257 keeps its continent) "
                             "and STATE_CATEGORY_DUP (4 vanilla state files). No BBOX_LARGE, STATE_NONCONTIGUOUS or "
                             "river warnings, because the synthetic geometry has none of vanilla's quirks.")

    # ------------------------------------------------------------ the synthetic map (shared by all variants)
    def units_and_anchors(self, v, cv):
        t = v.types
        pstate, pregion = v.province_state, v.province_region
        states = defaultdict(list)
        for p, (sid, _) in pstate.items():
            states[sid].append(p)
        anchor_ids = {a[0] for a in ANCHORS}
        order = sorted(states, key=lambda s: (min(pregion[p][0] for p in states[s]), s))
        units = []
        for sid in order:
            if sid in anchor_ids:
                continue
            ps = sorted(states[sid])
            units.append((sid, [p for p in ps if t[p] == LAND] + [p for p in ps if t[p] == LAKE]))
        loose = sorted(p for p in range(1, len(t)) if t[p] == LAKE and p not in pstate)
        if loose:
            units.append((None, loose))
        anchors = []
        for sid, lon, lat, align, _ in ANCHORS:
            col, row = cv.to_pixel(lon, lat)
            ps = sorted(states[sid])
            anchors.append((sid, [p for p in ps if t[p] == LAND] + [p for p in ps if t[p] == LAKE],
                            int(row), int(col), align))
        seas = sorted((p for p in range(1, len(t)) if t[p] == SEA), key=lambda p: (pregion[p][0], p))
        return units, anchors, seas

    def base(self, ctx):
        """{rel path: bytes} of the synthetic map (cached per process)."""
        if self._base is not None:
            return self._base
        v = ctx.vanilla
        cv = canvas()
        globe = cv.globe_mask()
        units, anchors, seas = self.units_and_anchors(v, cv)
        vdef = v.definition
        n0 = vdef.n
        lay = layout(globe, units, anchors, seas, n0, Params())
        pid = lay.pid
        n = int(pid.max()) + 1
        types = np.concatenate([v.types, np.full(n - n0, SEA, dtype=np.int8)])
        types[lay.off_ids] = LAKE
        files = {}
        # definition
        d = vdef.copy()
        cols = new_colors(vdef.colors(), n - n0, COLOR_SEED)
        coast = coastal_flags(pid, types)
        off = set(lay.off_ids)
        for j, i in enumerate(range(n0, n)):
            if i in off:
                d.rows.append([str(i), *map(str, cols[j]), "lake", "false", "lakes", "0"])
            else:
                d.rows.append([str(i), *map(str, cols[j]), "sea", "true" if coast[i] else "false", "ocean", "0"])
        for i in range(1, n0):
            if types[i] in (LAND, SEA):
                d.rows[i][5] = "true" if coast[i] else "false"
        files["map/definition.csv"] = encode(d.format())
        files["map/provinces.bmp"] = write_bmp(v.provinces_bmp, rgb_from_pid(pid, d.colors()))
        land = types[pid] == LAND
        for rel, lv, wv in (("map/heightmap.bmp", LAND_H, WATER_H), ("map/terrain.bmp", T_LAND, T_WATER),
                            ("map/rivers.bmp", R_LAND, R_WATER), ("map/cities.bmp", CITIES, CITIES)):
            b = v.bmp(rel)
            files[rel] = write_bmp(b, np.where(land, lv, wv).astype(np.uint8))
        nb = v.bmp("map/world_normal.bmp")
        flat = np.empty((H // 2, W // 2, 3), dtype=np.uint8)
        flat[:] = (128, 128, 255)
        files["map/world_normal.bmp"] = write_bmp(nb, flat)
        tb = v.bmp("map/trees.bmp")
        files["map/trees.bmp"] = write_bmp(tb, np.zeros_like(tb.pixels))
        # textures: ocean tone everywhere on water (off-globe included), plains tone on land
        vpid = np.asarray(v.pid)
        sea_open = open_sea_mask(vpid, v.types)
        vland = v.types[vpid] == LAND
        half_land = land[::2, ::2]
        t = read_dds(v.bytes(DDS["colormap"]))
        rgba = bgra_to_rgba(t.levels[0], t.width, t.height)
        ocean, plains = median_colour(rgba, sea_open), median_colour(rgba, vland)
        img = np.where(half_land[:, :, None], np.array(plains, np.uint8), np.array(ocean, np.uint8))
        files[DDS["colormap"]] = write_dds(t, W // 2, H // 2, [rgba_to_bgra(img)])
        self.tones = {"colormap_ocean": ocean, "colormap_land": plains}
        for k, rel in enumerate(DDS["water"]):
            t = read_dds(v.bytes(rel))
            tone = median_colour(dxt5_decode(t.levels[0], t.width, t.height), sea_open)
            w, h = W // (2 << k), H // (2 << k)
            files[rel] = write_dds(t, w, h, [dxt5_uniform_block(tone) * ((w // 4) * (h // 4))])
        t = read_dds(v.bytes(DDS["fow"]))
        fr = dxt5_decode(t.levels[0], t.width, t.height)
        fs, fl = median_colour(fr, sea_open), median_colour(fr, vland)
        fimg = np.where(half_land[:, :, None], np.array(fl, np.uint8), np.array(fs, np.uint8))
        lvl0 = dxt5_encode(fimg)
        files[DDS["fow"]] = write_dds(t, W // 2, H // 2, dxt5_mip_chain(dxt5_decode(lvl0, W // 2, H // 2), lvl0,
                                                                          full_mip_count(W // 2, H // 2)))
        # adjacencies: header + terminator (+ vanilla's trailing comment lines); geometry-bound rows dropped
        al = v.text("map/adjacencies.csv").split("\n")
        term = next(k for k, ln in enumerate(al) if ln.startswith("-1;-1;"))
        files["map/adjacencies.csv"] = encode("\n".join([al[0]] + al[term:]))
        # regions for the new provinces
        files.update(self.new_regions(v, pid, lay, types))
        centre = interior_points(pid)
        files.update(self.positions(v, pid, types, coast, lay, centre))
        # railways: every run of consecutive land bars
        rails = []
        for ids in lay.lines:
            run = []
            for i in ids + [None]:
                if i is not None and types[i] == LAND:
                    run.append(i)
                    continue
                if len(run) >= 2:
                    rails.append("1 %d %s " % (len(run), " ".join(map(str, run))))
                run = []
        files["map/railways.txt"] = encode("\n".join(rails) + "\n")
        self._base = files
        self.layout_info = {"sea_new": len(lay.sea_new), "off": len(lay.off_ids), "provinces": n - 1,
                            "anchors": lay.anchors, "off_ids": (lay.off_ids[0], lay.off_ids[-1])}
        return files

    def new_regions(self, v, pid, lay, types) -> dict:
        src_name = next(f for f in sorted(v.region_files) if f.startswith(WEATHER_SRC))
        weather = weather_block(v.region_files[src_name])
        rid = max(r for r, _ in v.province_region.values()) + 1
        files, loc = {}, ["﻿l_english:"]
        for k in range(0, len(lay.sea_new), REGION_CHUNK):
            ids = lay.sea_new[k:k + REGION_CHUNK]
            name = f"EXP-09 extra sea {k // REGION_CHUNK + 1}"
            files[f"map/strategicregions/{rid}-{name}.txt"] = encode(region_file(rid, name, ids, weather, "water_deep_ocean"))
            loc.append(f' STRATEGICREGION_{rid}:0 "{name}"')
            rid += 1
        ys, xs = np.nonzero(np.isin(pid, lay.off_ids))
        ids_at = pid[ys, xs]
        n = int(pid.max()) + 1
        cnt = np.bincount(ids_at, minlength=n)
        cy = np.bincount(ids_at, weights=ys, minlength=n) / np.maximum(cnt, 1)
        cx = np.bincount(ids_at, weights=xs, minlength=n) / np.maximum(cnt, 1)
        quads = defaultdict(list)
        for i in lay.off_ids:
            quads[("N" if cy[i] < H / 2 else "S") + ("W" if cx[i] < W / 2 else "E")].append(i)
        for q in ("NW", "NE", "SW", "SE"):
            if not quads[q]:
                continue
            name = f"EXP-09 off-globe {q}"
            body = region_file(rid, name, quads[q], weather, "none").replace("\tnaval_terrain=none\n", "")
            files[f"map/strategicregions/{rid}-{name}.txt"] = encode(body)
            loc.append(f' STRATEGICREGION_{rid}:0 "{name}"')
            rid += 1
        files[LOC] = encode("\n".join(loc) + "\n")
        return files

    def positions(self, v, pid, types, coast, lay, centre) -> dict:
        files = {}
        n0 = v.definition.n
        pstate = v.province_state
        state_land = defaultdict(list)
        for p, (sid, _) in sorted(pstate.items()):
            if types[p] == LAND:
                state_land[sid].append(p)
        land_ids = sorted(p for p in range(1, n0) if types[p] == LAND)
        cpts = coast_points(pid, types, land_ids, centre)

        def xz(i, pt=None):
            r, c = pt if pt else centre[i]
            return game_xz(r, c, H)

        # buildings.txt: per-state lines keep vanilla's count/rotation per state, spread over its bars
        bl, btr = split_lines(v.text("map/buildings.txt"))
        out, k_of = [], Counter()
        for ln in bl:
            s = ln.split(";")
            if len(s) < 7 or s[1] in PER_PROVINCE:
                continue
            sid = int(s[0])
            bars = state_land.get(sid)
            if not bars:
                continue
            i = bars[k_of[sid] % len(bars)]
            k_of[sid] += 1
            x, z = xz(i)
            out.append(f"{sid};{s[1]};{fmt2(x)};{LAND_H / 10:.2f};{fmt2(z)};{s[5]};{s[6]}")
        for i in land_ids:
            sid = pstate[i][0]
            x, z = xz(i)
            for t in PER_LAND:
                out.append(f"{sid};{t};{fmt2(x)};{LAND_H / 10:.2f};{fmt2(z)};0.00;0")
            if coast[i]:
                r, c, sea_id = cpts[i]
                x, z = xz(i, (r, c))
                for t in PER_COAST:
                    extra = sea_id if t == "naval_base_spawn" else (i if t == "floating_harbor" else 0)
                    out.append(f"{sid};{t};{fmt2(x)};9.50;{fmt2(z)};0.00;{extra}")
        files["map/buildings.txt"] = encode(join_lines(out, btr))
        # unitstacks.txt: vanilla type sets (+ coastal types), new seas get the commonest sea set
        ul, utr = split_lines(v.text("map/unitstacks.txt"))
        per = defaultdict(dict)
        for ln in ul:
            s = ln.split(";")
            per[int(s[0])][int(s[1])] = (s[5], s[6])
        vt = v.types
        sea_sets = Counter(tuple(sorted(per[p])) for p in per if vt[p] == SEA)
        best = sea_sets.most_common(1)[0][0]
        tmpl_sea = per[min(p for p in per if vt[p] == SEA and tuple(sorted(per[p])) == best)]
        coast_tmpl = per[min(p for p in per if vt[p] == LAND and set(COAST_STACK) <= set(per[p]))]
        us = []
        for i in sorted(per):
            tset = dict(per[i])
            if types[i] == LAND and coast[i]:
                for t in COAST_STACK:
                    tset.setdefault(t, coast_tmpl[t])
            x, z = xz(i)
            y = f"{LAND_H / 10:.2f}" if types[i] == LAND else "9.50"
            for t in sorted(tset):
                us.append(f"{i};{t};{fmt2(x)};{y};{fmt2(z)};{tset[t][0]};{tset[t][1]}")
        for i in lay.sea_new:
            x, z = xz(i)
            for t in best:
                us.append(f"{i};{t};{fmt2(x)};9.50;{fmt2(z)};{tmpl_sea[t][0]};{tmpl_sea[t][1]}")
        files["map/unitstacks.txt"] = encode(join_lines(us, utr))
        # weatherpositions.txt: vanilla count and sizes per region, spread over the region's provinces
        wl, wtr = split_lines(v.text("map/weatherpositions.txt"))
        members = defaultdict(list)
        for p, (rid, _) in v.province_region.items():
            members[rid].append(p)
        wout, k_of = [], Counter()
        for ln in wl:
            s = ln.split(";")
            rid = int(s[0])
            ps = sorted(members.get(rid, []))
            if not ps:
                wout.append(ln)          # empty vanilla region: keep its line as is
                continue
            i = ps[(k_of[rid] * 7) % len(ps)]
            k_of[rid] += 1
            x, z = xz(i)
            wout.append(f"{rid};{fmt2(x)};9.50;{fmt2(z)};{s[4]}")
        files["map/weatherpositions.txt"] = encode(join_lines(wout, wtr))
        return files

    # ------------------------------------------------------------ build / readme / check
    def variant_files(self, ctx, build_id) -> dict:
        var = self.variant(ctx, build_id)
        files = {}
        for src in var.defines:
            p = safe_join(ctx.repo_root, src)
            files["common/defines/" + Path(src).name] = p.read_bytes()
        if var.shader_patches:
            files.update(patched_files(ctx.repo_root, ctx.game, var.shader_patches))
        return files

    def build(self, ctx, build_id, out: Path):
        files = dict(self.base(ctx))
        files.update(self.weather_for_new_regions(files))
        files.update(self.variant_files(ctx, build_id))
        for rel, data in sorted(files.items()):
            write_bytes(out, rel, data)
        return dict(self.layout_info, variant=build_id[len("EXP-09"):],
                    manifest=load_manifest(ctx.repo_root) is not None)

    def weather_for_new_regions(self, files) -> dict:
        """weatherpositions.txt + one line per new region (at the middle province's centre)."""
        wl, tr = split_lines(decode(files["map/weatherpositions.txt"]))
        d = Definition.parse(decode(files["map/definition.csv"]))
        pid = pid_from_rgb(read_bmp(files["map/provinces.bmp"]).pixels, d.colors())
        new = sorted((k, v) for k, v in files.items() if k.startswith("map/strategicregions/"))
        mids = {}
        for rel, data in new:
            ids = block_ids(decode(data), "provinces")
            mids[int(rel.split("/")[-1].split("-")[0])] = ids[len(ids) // 2]
        cen = interior_points(pid, sorted(mids.values()))
        for rid in sorted(mids):
            r, c = cen[mids[rid]]
            x, z = game_xz(r, c, H)
            wl.append(f"{rid};{fmt2(x)};9.50;{fmt2(z)};big")
        return {"map/weatherpositions.txt": encode(join_lines(wl, tr))}

    def readme(self, ctx, build_id, info):
        var = self.variant(ctx, build_id)
        anchors = "; ".join(a[4] for a in ANCHORS)
        man = "" if info.get("manifest") else " (built WITHOUT the P00c manifest: baseline only)"
        steps = [
            "Start a new game (1936) with any country (e.g. the United States) and pause. Use the default "
            "(political) map mode.",
            "This is NOT the real world: see 'GOOD TO KNOW'. Use these places for the screenshots: "
            f"{anchors}. The 'seam' is the left/right map edge at the equator (the middle of the height of "
            "the map, where the ocean runs off the left edge and comes back on the right).",
            "Screenshot 1: centred on the seam at the equator, fully zoomed out (scroll out until it stops).",
            "Screenshot 2: same place, medium zoom (about half-way). Screenshot 3: same place, close zoom.",
            "Screenshot 4: drag the camera as far north as it goes over the Greenland landmark, medium zoom. "
            "Screenshot 5: as far south as it goes over the Cape Horn landmark, medium zoom.",
            "Screenshot 6 (winter; the 1936 start date, 1 January, is fine): fully zoomed in "
            "at the Chukotka landmark (Cape Dezhnev, right edge) and at the Alaska landmark (Cape Prince of "
            "Wales, left edge), one shot on each side of the seam, including the water just beyond the curved "
            "edge. In variants d and e a ragged ice edge a few pixels outside the curve is expected.",
            "Screenshot 7: zoom in and out fast, then pan fast across the seam; note flicker or popping.",
            "Hover a tile beyond the curved edge: it should be a lake province; hover/click near the curve and "
            "check the right province is selected.",
        ]
        return texts.readme(
            build_id, self.title_for(build_id) + man,
            heading="WHAT THIS TEST IS (a synthetic test world, not the normal map)",
            prop="The whole map is a synthetic test world on our 5120x2304 Equal Earth canvas (see GOOD TO KNOW). "
                 "Everything outside the curved Equal Earth outline is filled with lake provinces that have the "
                 "ocean's height (heightmap 89) and the ocean's colour tone. All variants "
                 f"({', '.join(x.id for x in self.variants(ctx))}) share this map. "
                 f"What variant {var.id} adds ({var.label}): {var.changes}",
            why="Decides how the empty corners outside our curved Equal Earth map should look (DEC-021): the "
                "filler provinces alone (a), camera limits (b, c) and colour-only shader tweaks (d, e). "
                "Compare the variants with each other using the same screenshots.",
            launch=texts.LAUNCH_DEBUG, steps=steps,
            send=["Screenshots 1-7 named '<variant>-<number>' (e.g. EXP-09c-4).",
                  "Which variant looks best at each zoom, and why (one line is enough).",
                  "error.log / system.log lines mentioning 'pdxwater', 'shader' or 'defines' (d and e must not add "
                  "shader errors).",
                  "Did hover/click near the curved edge pick the right province (yes/no)?"],
            expected=self.expected(build_id).text, cannot=["EXP-09"], user_dir=ctx.user,
            notes=["This map is synthetic, made only for this look test: every province, state and country of "
                   "the normal game still exists (so the game loads and plays), but land is drawn as rows of small "
                   "bars in the middle of the map, surrounded by ocean. Only four landmark states sit at their real "
                   "places: " + anchors + ".",
                   f"The area outside the curved outline is {info['off']} lake provinces coloured like ocean "
                   f"(provinces {info['off_ids'][0]}..{info['off_ids'][1]}); ships cannot enter them.",
                   "Use the same save/date and screen resolution for every variant (say which resolution)."])

    def check(self, ctx, build_id, out):
        v = ctx.vanilla
        probs = check_descriptor(self, build_id, out)
        try:
            d = Definition.parse(decode((out / "map/definition.csv").read_bytes()))
            pid = pid_from_rgb(read_bmp((out / "map/provinces.bmp").read_bytes()).pixels, d.colors())
        except (OSError, KitError) as e:
            return probs + [f"cannot read output: {e}"]
        if pid.shape != (H, W):
            return probs + [f"canvas is {pid.shape[1]}x{pid.shape[0]}, expected {W}x{H}"]
        vd = v.definition
        n0 = vd.n
        types = d.types()
        for i in range(1, n0):
            if d.rows[i][:5] != vd.rows[i][:5] or d.rows[i][6:] != vd.rows[i][6:]:
                probs.append(f"vanilla definition row {i} changed beyond the coastal flag")
                break
        globe = canvas().globe_mask()
        off = np.zeros(d.n, dtype=bool)
        for i in range(n0, d.n):
            off[i] = d.rows[i][4] == "lake"
            if d.rows[i][4] not in ("lake", "sea"):
                probs.append(f"new province {i} is neither filler lake nor sea")
                break
        mism = np.nonzero(~off[pid] != globe)
        # allowed: at most 4 off-globe pixels on the right edge, at the lens tips next to the seam, given to sea
        if len(mism[0]) > 4 or (mism[1] != W - 1).any() or globe[mism].any() or \
                (types[pid[mism]] != SEA).any() or (~off[pid[mism[0], 0]]).any():
            probs.append(f"off-globe pixels and filler lake provinces do not coincide ({len(mism[0])} px)")
        a = np.bincount(pid.ravel(), minlength=d.n)
        if (a[1:] < 8).any():
            probs.append("provinces under 8 px")
        if len(x_crossings(pid)[0]):
            probs.append("X-crossings present")
        coast = coastal_flags(pid, types)
        if any((d.rows[i][5] == "true") != coast[i] for i in range(1, d.n) if types[i] in (LAND, SEA)):
            probs.append("coastal flags not recomputed")
        land = types[pid] == LAND
        hm = read_bmp((out / "map/heightmap.bmp").read_bytes()).pixels
        if not np.array_equal(hm, np.where(land, LAND_H, WATER_H)):
            probs.append("heightmap is not 89 on all water (incl. off-globe) and 100 on land")
        tr = read_bmp((out / "map/terrain.bmp").read_bytes())
        if tr.palette != v.bmp("map/terrain.bmp").palette or (tr.pixels[~globe] != T_WATER).any():
            probs.append("terrain.bmp: vanilla palette / ocean index 15 off-globe not respected")
        g = read_dds((out / DDS["colormap"]).read_bytes())
        rgba = bgra_to_rgba(g.levels[0], g.width, g.height)
        half_off = ~globe[::2, ::2]
        half_water = ~land[::2, ::2]
        tone = rgba[half_water & globe[::2, ::2]]
        if (g.width, g.height) != (W // 2, H // 2) or len(np.unique(rgba[half_off].reshape(-1, 4), axis=0)) != 1 \
                or not (rgba[half_off][0] == tone[0]).all():
            probs.append("colormap: off-globe is not the single ocean tone used for on-globe sea")
        for k, rel in enumerate(DDS["water"]):
            gd = read_dds((out / rel).read_bytes())
            if (gd.width, gd.height) != (W // (2 << k), H // (2 << k)):
                probs.append(f"{rel}: wrong size")
        gf = read_dds((out / DDS["fow"]).read_bytes())
        if (gf.width, gf.height) != (W // 2, H // 2) or len(gf.levels) != full_mip_count(W // 2, H // 2):
            probs.append("fow texture: wrong size or mip chain")
        # regions: vanilla files untouched, new files hold every new province exactly once
        seen = Counter()
        for p in sorted((out / "map/strategicregions").glob("*.txt")):
            if p.name in v.region_files:
                probs.append(f"vanilla region {p.name} overridden")
            seen.update(block_ids(decode(p.read_bytes()), "provinces"))
        if set(seen) != set(range(n0, d.n)) or any(c != 1 for c in seen.values()):
            probs.append("new provinces are not each in exactly one new region")
        # variant extras
        want = self.variant_files(ctx, build_id)
        for rel, data in want.items():
            p = out / rel
            if not p.is_file() or p.read_bytes() != data:
                probs.append(f"{rel}: not the manifest source / patched vanilla file")
        expected = set(BASE_FILES) | set(want) | {p.relative_to(out).as_posix()
                                                  for p in (out / "map/strategicregions").glob("*.txt")}
        probs += check_file_set(out, expected)
        return probs
