#!/usr/bin/env python3
"""Offline validator for a Hearts of Iron IV map mod.

Checks the invariants documented in ../references/validation.md against a mod
(or vanilla) directory. Every check is deterministic and reads files only.

Usage:
    python validate_map.py <mod_root> [--vanilla <game_root>] [--json report.json]
                           [--bbox-limit 250 --bbox-limit-sea 180] [--min-pixels 9]
                           [--no-engine-rules]
    Honours replace_path entries in <mod_root>/descriptor.mod.

<mod_root> must contain map/ and, optionally, history/states/ and
common/state_category/. Files missing from <mod_root> are read from --vanilla
when given (mirrors how the game merges a mod over the base game, ignoring
replace_path).

Engine rules (P00e, found in game with hoi4.exe 1.19.3; evidence in docs/logs/P00b.md
sections 17-23 and tools/experiments/regioncentre.py / naval.py). Checks 1-3 are skipped
with --no-engine-rules (default: on):
  1. ERROR REGION_CENTRE_DIV0      a strategic region whose centre calculation divides by
                                   zero (INT_DIVIDE_BY_ZERO crash at start; 6/6 in game).
                                   The engine averages the members' box centres (boxes on a
                                   2-px grid, y from the bottom); if that mean lies in no
                                   member box it divides by mean.x - rect centre x (rect =
                                   union of member boxes). Conservative guard: the 2-px grid
                                   model OR the older pixel-box model, inclusive and open
                                   bounds, and dy == 0 as caution.
     WARN  REGION_CENTRE_UNKNOWN   a region whose members touch x=0 and x=W-1 (it wraps) and
                                   whose mean lies in no member box: outside the model
                                   (vanilla has 6 and loads). INFO instead when --vanilla has
                                   a region with identical member boxes (signature).
  2. ERROR SEA_REGION_FRACTIONED   a naval strategic region whose sea members are not one
                                   piece by 4-neighbour pixel contact (wrap included, lakes,
                                   land and adjacencies.csv links do not count); fatal
                                   MAP_ERROR. Lists the provinces outside the piece holding
                                   the region's lowest sea province ID (engine convention).
  3. ERROR PROVINCE_CROSSES_SEAM   a province with pixels in column 0 and column W-1: the
                                   engine measures its box without wrap (full width, TOO
                                   LARGE BOX; EXP-08-5632 province 13511).
  4. ERROR PROVINCE_TOO_SMALL      now fires for <= 8 px (default --min-pixels 9; the
                                   engine logs provinces of <= 8 px, EXP-04).
  5. WARN  BBOX_ENGINE_RISK        a province whose raw (unwrapped) pixel box is >= 600 px
                                   wide or >= 174 px high (largest observed-clean sizes;
                                   TOO LARGE BOX seen at 1200 wide / 300 high). BBOX_LARGE
                                   (the --bbox-limit heuristic) is unchanged.
  6. WARN  ADJ_SEAM_LINK           an adjacencies.csv row whose From/To pixel centroids lie
                                   on opposite sides of the wrap seam (one within 5 % of x=0,
                                   the other within 5 % of x=W): 'sea' rows crash at start,
                                   empty-type rows are measured unwrapped (EXP-01-SEAM).

Exit code: 0 = no ERROR findings, 1 = at least one ERROR, 2 = could not run.
Requires: numpy, pillow  (pip install numpy pillow)
"""
import argparse
import collections
import hashlib
import json
import os
import re
import struct
import sys

try:
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover
    print("validate_map.py needs numpy and pillow: pip install numpy pillow", file=sys.stderr)
    sys.exit(2)

Image.MAX_IMAGE_PIXELS = None

MAX_AREA = 13_238_272          # community-reported engine ceiling on W*H (Tier 3, see sources.md)
RIVER_INDICES = set(range(0, 12)) | {254, 255}
LAND_TERRAINS_DEFAULT = {"plains", "forest", "hills", "mountain", "desert", "marsh", "jungle", "urban", "unknown"}
SEA_TERRAINS_DEFAULT = {"ocean", "water_fjords", "water_shallow_sea", "water_deep_ocean"}
LAKE_TERRAINS_DEFAULT = {"lakes"}
ENGINE_GRID = 2                # engine province boxes snap to a 2-px grid (EXP-03-24k dump, P00b-f5)
ENGINE_BOX_W = 600             # BBOX_ENGINE_RISK: raw box width >= this (clean seen: a 600-px strip)
ENGINE_BOX_H = 174             # BBOX_ENGINE_RISK: raw box height >= this (clean seen: 173, vanilla 4455)
SEAM_BAND = 0.05               # ADJ_SEAM_LINK: fraction of W on each side of the wrap seam


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, code, msg, **data):
        self.items.append({"level": level, "code": code, "msg": msg, **data})

    def err(self, code, msg, **d):
        self.add("ERROR", code, msg, **d)

    def warn(self, code, msg, **d):
        self.add("WARN", code, msg, **d)

    def info(self, code, msg, **d):
        self.add("INFO", code, msg, **d)

    def count(self, level):
        return sum(1 for i in self.items if i["level"] == level)


def find(root, vanilla, rel):
    for base in (root, vanilla):
        if base:
            p = os.path.join(base, rel)
            if os.path.exists(p):
                return p
    return None


REPLACE_PATHS = set()


def load_replace_paths(root):
    """replace_path entries of <root>/descriptor.mod: the game ignores vanilla files in those folders."""
    p = os.path.join(root, "descriptor.mod")
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig", errors="replace") as fh:
            for m in re.finditer(r'^\s*replace_path\s*=\s*"([^"]+)"', fh.read(), re.M):
                REPLACE_PATHS.add(m.group(1).strip("/"))


def list_dir(root, vanilla, rel):
    """Mod files override vanilla files with the same name; folders named in the mod's
    replace_path entries ignore vanilla entirely (game behaviour)."""
    out = {}
    bases = (root,) if rel.strip("/") in REPLACE_PATHS else (vanilla, root)
    for base in bases:
        if base and os.path.isdir(os.path.join(base, rel)):
            for f in os.listdir(os.path.join(base, rel)):
                if f.endswith(".txt"):
                    out[f] = os.path.join(base, rel, f)
    return sorted(out.values())


def read_text(path):
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        return re.sub(r"#[^\n]*", "", fh.read())


def brace_block(text, key):
    m = re.search(r"\b" + key + r"\s*=\s*\{", text)
    if not m:
        return None
    i, depth = m.end(), 1
    while i < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[m.end():i - 1]


def bmp_header(path):
    with open(path, "rb") as fh:
        b = fh.read(54)
    if b[:2] != b"BM":
        return None
    return {
        "dib": struct.unpack("<I", b[14:18])[0],
        "w": struct.unpack("<i", b[18:22])[0],
        "h": struct.unpack("<i", b[22:26])[0],
        "bpp": struct.unpack("<H", b[28:30])[0],
        "compression": struct.unpack("<I", b[30:34])[0],
    }


def neighbours_4(mask):
    o = np.zeros_like(mask)
    o[1:] |= mask[:-1]
    o[:-1] |= mask[1:]
    o[:, 1:] |= mask[:, :-1]
    o[:, :-1] |= mask[:, 1:]
    o[:, 0] |= mask[:, -1]   # horizontal wrap
    o[:, -1] |= mask[:, 0]
    return o


# ------------------------------------------------------------- engine rules (P00e)
def _trunc_div(a, b):
    """Integer division truncating towards zero (C semantics, as the engine's idiv)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def bottom_up_boxes(xmin, xmax, ymin, ymax, H):
    """Pixel boxes (inclusive) per province ID with y counted from the bottom row, as the engine stores them."""
    present = np.asarray(xmax) >= 0
    yb0 = np.where(present, H - 1 - np.asarray(ymax), 0)
    yb1 = np.where(present, H - 1 - np.asarray(ymin), -1)
    return (np.asarray(xmin, dtype=np.int64), np.asarray(xmax, dtype=np.int64),
            yb0.astype(np.int64), yb1.astype(np.int64))


def region_centre(members, boxes, W, grid=ENGINE_GRID):
    """Conservative model of the engine's strategic-region centre (hoi4.exe 1.19.3, RVA 0x15A4770 /
    0x15A5C20 / 0x15A4C20), ported from tools/experiments/regioncentre.py (P00b-f5 r2; 6/6 in game).

    ``boxes`` = bottom_up_boxes() arrays; ``members`` = the region's province IDs that have pixels.
    The engine takes the truncating mean M of the members' box centres; if M lies in no member box it
    divides by M.x - (rect x0 + rect w / 2), rect = the union of the member boxes. Two box models are
    evaluated and the guard is their union: the 2-px grid model (x0 = 2*(xmin//2), x0+w = 2*(xmax//2+1),
    the same in y; inclusive OR open member test) and the older pixel-box model (w = span + 1, rect =
    union + 1; open lower bound for the dx test, inclusive for the dy test). dy == 0 is flagged only as
    caution (no dy division was found on this path). Regions whose members touch x=0 and x=W-1 wrap and
    are not covered: they are ``unknown`` when M misses the member boxes. Returns None for no members.
    """
    if not len(members):
        return None
    ids = np.asarray(sorted(int(i) for i in members), dtype=np.int64)
    x0, x1, y0, y1 = (b[ids] for b in boxes)
    n = len(ids)
    # older model: pixel boxes, centre x0 + (span + 1) / 2
    mx = _trunc_div(int((x0 + (x1 - x0 + 1) // 2).sum()), n)
    my = _trunc_div(int((y0 + (y1 - y0 + 1) // 2).sum()), n)
    fallback = not bool(((x0 <= mx) & (mx <= x1) & (y0 <= my) & (my <= y1)).any())
    fallback_strict = not bool(((x0 < mx) & (mx <= x1) & (y0 < my) & (my <= y1)).any())
    rx0, ry0 = int(x0.min()), int(y0.min())
    rw, rh = int(x1.max()) - rx0 + 2, int(y1.max()) - ry0 + 2
    dx, dy = mx - (rx0 + rw // 2), my - (ry0 + rh // 2)
    # 2-px grid model (fits the EXP-03-24k dump exactly; confirmed by 191only / div0b / div0c / div0)
    bx, by = (x0 // grid) * grid, (y0 // grid) * grid
    bw, bh = (x1 // grid + 1) * grid - bx, (y1 // grid + 1) * grid - by
    gx = _trunc_div(int((bx + bw // 2).sum()), n)
    gy = _trunc_div(int((by + bh // 2).sum()), n)
    g_fb = not bool(((bx <= gx) & (gx <= bx + bw) & (by <= gy) & (gy <= by + bh)).any())
    g_fb_open = not bool(((bx < gx) & (gx < bx + bw) & (by < gy) & (gy < by + bh)).any())
    grx0, gry0 = int(bx.min()), int(by.min())
    grw, grh = int((bx + bw).max()) - grx0, int((by + bh).max()) - gry0
    gdx, gdy = gx - (grx0 + grw // 2), gy - (gry0 + grh // 2)
    seam = bool((x0 == 0).any() and (x1 == W - 1).any())
    sig = hashlib.sha256(np.stack([x0, x1, y0, y1], 1).astype("<i8").tobytes()).hexdigest()[:16]
    clauses = []
    if not seam:
        if (g_fb or g_fb_open) and gdx == 0:
            clauses.append("grid model: mean in no member box" + ("" if g_fb else " (open bounds)")
                           + " and grid dx == 0 (the rule confirmed in game)")
        if fallback_strict and dx == 0:
            clauses.append("pixel-box model: mean in no member box (open lower bound) and dx == 0")
        if fallback and dy == 0:
            clauses.append("pixel-box model: mean in no member box and dy == 0 (caution)")
    return {"n": n, "mean": (mx, my), "rect": (rx0, ry0, rw, rh), "dx": dx, "dy": dy,
            "mean_grid": (gx, gy), "rect_grid": (grx0, gry0, grw, grh), "dx_grid": gdx, "dy_grid": gdy,
            "fallback": fallback, "fallback_strict": fallback_strict, "fallback_grid": g_fb,
            "fallback_grid_open": g_fb_open, "seam": seam, "signature": sig, "clauses": clauses,
            "unsafe": bool(clauses), "unknown": seam and (fallback_strict or g_fb or g_fb_open)}


def fractioned_naval(regions, typ, adj):
    """{region id: (lowest sea ID, [separated sea IDs])} for naval strategic regions (regions holding a sea
    province) whose sea members are not one piece by 4-neighbour pixel contact (``adj``, wrap included).
    Land and lake members and adjacencies.csv links do not count. The engine keeps the piece holding the
    region's lowest sea ID and lists the rest (P00b-f7: reproduces every logged MAP_ERROR; vanilla 0/98)."""
    out = {}
    for rid in sorted(regions):
        ms = sorted({q for q in regions[rid] if typ.get(q) == "sea"})
        if len(ms) < 2:
            continue
        want, seen, st = set(ms), {ms[0]}, [ms[0]]
        while st:
            q = st.pop()
            for r_ in adj.get(q, ()):
                if r_ in want and r_ not in seen:
                    seen.add(r_); st.append(r_)
        if len(seen) < len(want):
            out[rid] = (ms[0], sorted(want - seen))
    return out


def province_map(prov_path, def_path):
    """(pid, N): province ID per pixel (-1 = undefined colour) and the definition.csv row count."""
    col2id, n = {}, 0
    with open(def_path, encoding="latin-1") as fh:
        for line in fh:
            p_ = line.strip().split(";")
            try:
                i, key = int(p_[0]), (int(p_[1]) << 16) | (int(p_[2]) << 8) | int(p_[3])
            except (ValueError, IndexError):
                continue
            n += 1
            if i and key not in col2id:
                col2id[key] = i
    im = np.asarray(Image.open(prov_path).convert("RGB"))
    key = (im[..., 0].astype(np.int32) << 16) | (im[..., 1].astype(np.int32) << 8) | im[..., 2]
    uniq, inv = np.unique(key, return_inverse=True)
    lut = np.array([col2id.get(int(c), -1) for c in uniq], dtype=np.int32)
    return lut[inv].reshape(key.shape), max(n, max(col2id.values(), default=0) + 1)


def region_files(root, vanilla):
    """{region id: (file name, [province ids])} of the strategic-region files the game reads."""
    out = {}
    for f in list_dir(root, vanilla, "map/strategicregions"):
        t = read_text(f)
        m = re.search(r"\bid\s*=\s*(\d+)", t)
        if m:
            out[int(m.group(1))] = (os.path.basename(f), [int(v) for v in (brace_block(t, "provinces") or "").split()])
    return out


def vanilla_region_signatures(vanilla, pid=None, n=None):
    """{(W, H, member-box signature): vanilla region id} of the vanilla strategic regions."""
    if pid is None:
        pid, n = province_map(os.path.join(vanilla, "map/provinces.bmp"), os.path.join(vanilla, "map/definition.csv"))
    H, W = pid.shape
    flat = pid.ravel()
    ok = flat >= 0
    ys, xs = np.divmod(np.nonzero(ok)[0], W)
    fp = flat[ok]
    xmin = np.full(n, W); xmax = np.full(n, -1); ymin = np.full(n, H); ymax = np.full(n, -1)
    np.minimum.at(xmin, fp, xs); np.maximum.at(xmax, fp, xs)
    np.minimum.at(ymin, fp, ys); np.maximum.at(ymax, fp, ys)
    boxes = bottom_up_boxes(xmin, xmax, ymin, ymax, H)
    out = {}
    for rid, (_, pv) in sorted(region_files(vanilla, None).items()):
        c = region_centre([q for q in pv if 0 < q < n and xmax[q] >= 0], boxes, W)
        if c is not None:
            out.setdefault((W, H, c["signature"]), rid)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mod_root")
    ap.add_argument("--vanilla")
    ap.add_argument("--json")
    ap.add_argument("--bbox-limit", type=int, default=0,
                    help="max land/lake province bounding-box side in px (0 = W/8, a conservative heuristic)")
    ap.add_argument("--bbox-limit-sea", type=int, default=0,
                    help="max sea province bounding-box side in px (0 = same as --bbox-limit)")
    ap.add_argument("--min-pixels", type=int, default=9,
                    help="PROVINCE_TOO_SMALL fires below this (default 9: the engine logs provinces of <= 8 px)")
    ap.add_argument("--no-engine-rules", action="store_true",
                    help="skip REGION_CENTRE_DIV0/UNKNOWN, SEA_REGION_FRACTIONED and PROVINCE_CROSSES_SEAM (speed)")
    ap.add_argument("--max-per-code", type=int, default=5, help="console lines printed per finding code")
    args = ap.parse_args()
    root, van = args.mod_root, args.vanilla
    load_replace_paths(root)
    R = Report()

    # ------------------------------------------------------------------ bitmaps
    prov_path = find(root, van, "map/provinces.bmp")
    def_path = find(root, van, "map/definition.csv")
    if not prov_path or not def_path:
        print("map/provinces.bmp and map/definition.csv are required", file=sys.stderr)
        return 2
    hp = bmp_header(prov_path)
    W, H = hp["w"], abs(hp["h"])
    R.info("DIMENSIONS", f"provinces.bmp {W}x{H}, area {W*H}")
    if REPLACE_PATHS:
        R.info("REPLACE_PATHS", f"{len(REPLACE_PATHS)} replace_path folders from descriptor.mod honoured")
    if hp["bpp"] != 24:
        R.err("PROVINCES_BPP", f"provinces.bmp must be 24-bit RGB, found {hp['bpp']}-bit")
    if W % 256 or H % 256:
        R.err("DIM_NOT_256", f"width and height must be multiples of 256 (got {W}x{H})")
    if W * H > MAX_AREA:
        R.err("AREA_TOO_LARGE", f"W*H={W*H} exceeds community-reported ceiling {MAX_AREA}")

    same_size = {"terrain.bmp": 8, "rivers.bmp": 8, "heightmap.bmp": 8}
    for name, bpp in same_size.items():
        p = find(root, van, "map/" + name)
        if not p:
            R.err("MISSING_FILE", f"map/{name} missing")
            continue
        h = bmp_header(p)
        if (h["w"], abs(h["h"])) != (W, H):
            R.err("SIZE_MISMATCH", f"{name} is {h['w']}x{abs(h['h'])}, must equal provinces.bmp {W}x{H}")
        if h["bpp"] != bpp:
            R.err("BPP", f"{name} must be {bpp}-bit, found {h['bpp']}")
        if h["compression"] != 0:
            R.err("BMP_COMPRESSED", f"{name} must be uncompressed (BI_RGB)")
    p = find(root, van, "map/world_normal.bmp")
    if p:
        h = bmp_header(p)
        if (h["w"], abs(h["h"])) != (W // 2, H // 2):
            R.warn("NORMAL_SIZE", f"world_normal.bmp is {h['w']}x{abs(h['h'])}; vanilla uses half the province map ({W//2}x{H//2})")
        if h["bpp"] not in (24, 32):
            R.err("BPP", f"world_normal.bmp must be 24- or 32-bit, found {h['bpp']} (vanilla 1.14: 24; a 1.19.3 mod ships 32)")
    else:
        R.err("MISSING_FILE", "map/world_normal.bmp missing")

    # ---------------------------------------------------------- definition.csv
    rows = []
    with open(def_path, encoding="latin-1") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            p_ = line.split(";")
            if len(p_) < 8:
                R.err("DEF_COLUMNS", f"definition.csv line {ln} has {len(p_)} columns, need 8", line=ln)
                continue
            try:
                rows.append((int(p_[0]), int(p_[1]), int(p_[2]), int(p_[3]), p_[4], p_[5], p_[6], int(p_[7]), ln))
            except ValueError:
                R.err("DEF_PARSE", f"definition.csv line {ln} unparsable: {line}", line=ln)
    ids = [r[0] for r in rows]
    if ids != list(range(len(ids))):
        R.err("DEF_IDS", "province IDs must start at 0 and be sequential with no gaps or duplicates")
    if rows and rows[0][:5] != (0, 0, 0, 0, "land"):
        R.err("DEF_ROW0", "row 0 must be the dummy '0;0;0;0;land;false;unknown;0'")
    typ, coastal, terrain, cont = {}, {}, {}, {}
    col2id = {}
    terr_known = LAND_TERRAINS_DEFAULT | SEA_TERRAINS_DEFAULT | LAKE_TERRAINS_DEFAULT
    tpath = find(root, van, "common/terrain/00_terrain.txt")
    if tpath:
        cats = brace_block(read_text(tpath), "categories")
        if cats:  # top-level entries of categories = { } are indented by exactly one tab in vanilla
            found = set(re.findall(r"^\t([a-z_]+)\s*=\s*\{", cats, re.M))
            if found:
                terr_known = found
    for (i, r_, g, b, t, c, ter, co, ln) in rows:
        key = (r_ << 16) | (g << 8) | b
        if i and key in col2id:
            R.err("DEF_DUP_COLOR", f"province {i} reuses colour of province {col2id[key]}", province=i)
        if i:
            col2id[key] = i
        if t not in ("land", "sea", "lake"):
            R.err("DEF_TYPE", f"province {i} has type '{t}'", province=i)
        if c not in ("true", "false"):
            R.err("DEF_COASTAL", f"province {i} coastal flag '{c}' not true/false", province=i)
        if i and ter not in terr_known:
            R.err("DEF_TERRAIN", f"province {i} terrain '{ter}' is not a terrain category", province=i)
        if i and t == "sea" and co != 0:
            R.warn("DEF_SEA_CONTINENT", f"sea province {i} has continent {co} (should be 0)", province=i)
        if i and t == "land" and co == 0:
            R.err("DEF_LAND_CONTINENT", f"land province {i} has continent 0", province=i)
        typ[i], coastal[i], terrain[i], cont[i] = t, c == "true", ter, co
    cpath = find(root, van, "map/continent.txt")
    if cpath:
        ncont = len(re.findall(r"[a-z_]+", brace_block(read_text(cpath), "continents") or ""))
        bad = [i for i in cont if cont[i] > ncont]
        if bad:
            R.err("DEF_CONTINENT_RANGE", f"{len(bad)} provinces use a continent index > {ncont}", sample=bad[:10])
    N = len(rows)
    R.info("PROVINCE_COUNTS", "type counts", **collections.Counter(typ[i] for i in typ if i))

    # ------------------------------------------------------ provinces.bmp scan
    im = np.asarray(Image.open(prov_path).convert("RGB"))
    key = (im[..., 0].astype(np.int32) << 16) | (im[..., 1].astype(np.int32) << 8) | im[..., 2]
    uniq, inv = np.unique(key, return_inverse=True)
    lut = np.array([col2id.get(int(c), -1) for c in uniq], dtype=np.int32)
    pid = lut[inv].reshape(H, W)
    undefined = [f"{int(c) >> 16},{(int(c) >> 8) & 255},{int(c) & 255}" for c, v in zip(uniq, lut) if v < 0]
    if undefined:
        R.err("BMP_UNDEFINED_COLOR", f"{len(undefined)} colours in provinces.bmp have no definition.csv row", sample=undefined[:10])
    area = np.bincount(pid[pid >= 0].ravel(), minlength=N)
    absent = [i for i in range(1, N) if area[i] == 0]
    if absent:
        R.err("DEF_NO_PIXELS", f"{len(absent)} defined provinces have no pixels", sample=absent[:20])
    small = [(i, int(area[i])) for i in range(1, N) if 0 < area[i] < args.min_pixels]
    if small:
        R.err("PROVINCE_TOO_SMALL", f"{len(small)} provinces have < {args.min_pixels} px", sample=small[:20])

    # X-crossings (four distinct provinces around one 2x2 corner), including the wrap seam
    pw = np.concatenate([pid, pid[:, :1]], axis=1)
    a, b, c, d = pw[:-1, :-1], pw[:-1, 1:], pw[1:, :-1], pw[1:, 1:]
    x = (a != b) & (a != c) & (a != d) & (b != c) & (b != d) & (c != d)
    ys, xs = np.nonzero(x)
    if len(ys):
        R.err("X_CROSSING", f"{len(ys)} X-crossings (4 provinces meet at a point)",
              sample=[(int(xx), int(yy)) for yy, xx in list(zip(ys, xs))[:20]])

    # bounding boxes (wrap-aware: take the smaller of direct and wrapped horizontal span)
    limit = args.bbox_limit or W // 8
    limit_sea = args.bbox_limit_sea or limit
    yy, xx = np.indices(pid.shape)
    flat = pid.ravel()
    ok = flat >= 0
    fx, fy, fp = xx.ravel()[ok], yy.ravel()[ok], flat[ok]
    xmin = np.full(N, W); xmax = np.full(N, -1); ymin = np.full(N, H); ymax = np.full(N, -1)
    np.minimum.at(xmin, fp, fx); np.maximum.at(xmax, fp, fx)
    np.minimum.at(ymin, fp, fy); np.maximum.at(ymax, fp, fy)
    colsets = None
    big = []
    for i in range(1, N):
        if area[i] == 0:
            continue
        span_x = xmax[i] - xmin[i] + 1
        if span_x > W // 2:  # probably straddles the seam; measure the wrapped span
            if colsets is None:
                colsets = {}
            cols = np.unique(fx[fp == i])
            gaps = np.diff(np.r_[cols, cols[0] + W])
            span_x = W - gaps.max() + 1
        span = max(span_x, ymax[i] - ymin[i] + 1)
        if span > (limit_sea if typ.get(i) == "sea" else limit):
            big.append((i, int(span), typ.get(i)))
    if big:
        R.warn("BBOX_LARGE", f"{len(big)} provinces exceed the bounding-box limit (land/lake {limit} px, sea {limit_sea} px; risk of 'TOO LARGE BOX')", sample=big[:20])

    # engine box sizes (P00e): the engine measures the raw box (no wrap); TOO LARGE BOX seen at 1200 wide / 300 high
    raw_w, raw_h = xmax - xmin + 1, ymax - ymin + 1
    risky = [(i, int(raw_w[i]), int(raw_h[i]), typ.get(i)) for i in range(1, N)
             if area[i] and (raw_w[i] >= ENGINE_BOX_W or raw_h[i] >= ENGINE_BOX_H)]
    if risky:
        R.warn("BBOX_ENGINE_RISK", f"{len(risky)} provinces have a pixel box >= {ENGINE_BOX_W} px wide or >= {ENGINE_BOX_H} px high (larger than any seen loading cleanly; TOO LARGE BOX seen at 1200 wide / 300 high)", sample=risky[:20])
    if not args.no_engine_rules:
        both_edges = sorted((set(np.unique(pid[:, 0]).tolist()) & set(np.unique(pid[:, -1]).tolist())) - {-1})
        if both_edges:
            seam_rows = {i: int(((pid[:, 0] == i) & (pid[:, -1] == i)).sum()) for i in both_edges}
            R.err("PROVINCE_CROSSES_SEAM", f"{len(both_edges)} provinces have pixels in both column 0 and column {W - 1}: the engine measures their box without wrap (full width, TOO LARGE BOX)",
                  sample=[(i, typ.get(i), seam_rows[i]) for i in both_edges[:20]])
    # pixel centroid x per province (ADJ_SEAM_LINK)
    cent_x = np.bincount(fp, weights=fx, minlength=N) / np.maximum(area, 1)

    # coastal flag consistency (4-neighbourhood, wrap-aware)
    land_ids = np.array([i for i in typ if i and typ[i] == "land"])
    sea_ids = np.array([i for i in typ if i and typ[i] == "sea"])
    land = np.isin(pid, land_ids)
    sea = np.isin(pid, sea_ids)
    touch_land = set(np.unique(pid[land & neighbours_4(sea)]).tolist())
    flagged = {i for i in typ if typ[i] == "land" and coastal[i]}
    if flagged - touch_land:
        R.err("COASTAL_FALSE_POSITIVE", f"{len(flagged - touch_land)} land provinces flagged coastal but touch no sea", sample=sorted(flagged - touch_land)[:20])
    if touch_land - flagged:
        R.err("COASTAL_FALSE_NEGATIVE", f"{len(touch_land - flagged)} land provinces touch sea but coastal=false", sample=sorted(touch_land - flagged)[:20])

    # adjacency graph (4-neighbour + wrap)
    adj = collections.defaultdict(set)
    h_pairs = np.stack([pw[:, :-1].ravel(), pw[:, 1:].ravel()], 1)
    v_pairs = np.stack([pid[:-1].ravel(), pid[1:].ravel()], 1)
    pairs = np.unique(np.concatenate([h_pairs, v_pairs]), axis=0)
    for u, v in pairs:
        if u != v and u >= 0 and v >= 0:
            adj[int(u)].add(int(v)); adj[int(v)].add(int(u))

    # ----------------------------------------------------------- adjacencies.csv
    extra = collections.defaultdict(set)
    apath = find(root, van, "map/adjacencies.csv")
    if apath:
        lines = [l.rstrip("\r\n") for l in open(apath, encoding="latin-1") if l.strip() and not l.lstrip().startswith("#")]
        if not lines or not lines[0].lower().startswith("from;to;type;through"):
            R.err("ADJ_HEADER", "adjacencies.csv must start with the header row From;To;Type;Through;start_x;start_y;stop_x;stop_y;adjacency_rule_name;Comment")
        if not lines or not lines[-1].startswith("-1;-1;"):
            R.err("ADJ_TERMINATOR", "adjacencies.csv must end with the '-1;-1;;-1;-1;-1;-1;-1;-1' line")
        rules = set()
        rpath = find(root, van, "map/adjacency_rules.txt")
        if rpath:
            rules = set(re.findall(r'name\s*=\s*"?([A-Za-z0-9_]+)', read_text(rpath)))
        for n, l in enumerate(lines[1:], 2):
            if not l.strip() or l.lstrip().startswith("#"):
                continue  # blank and comment lines are accepted by the game (seen in a 1.19.3 mod)
            s = l.split(";")
            if s[0] == "-1":
                continue
            try:
                f_, t_, kind, thr = int(s[0]), int(s[1]), s[2], int(s[3])
            except (ValueError, IndexError):
                R.err("ADJ_PARSE", f"adjacencies.csv line {n} unparsable", line=n)
                continue
            for q in (f_, t_):
                if q not in typ:
                    R.err("ADJ_BAD_PROVINCE", f"adjacencies.csv line {n}: province {q} undefined", line=n)
            if kind not in ("", "land", "sea", "impassable", "river", "large_river", "lake", "canal"):
                R.warn("ADJ_TYPE", f"adjacencies.csv line {n}: unusual type '{kind}'", line=n)
            if kind == "sea":
                ends = (typ.get(f_), typ.get(t_))
                if ends == ("land", "land") and typ.get(thr) == "lake":
                    R.warn("ADJ_THROUGH_LAKE", f"adjacencies.csv line {n}: strait through a lake province {thr} (seen in a 1.19.3 mod; verify intent)", line=n)
                elif ends == ("land", "land") and typ.get(thr) != "sea":
                    R.err("ADJ_THROUGH", f"adjacencies.csv line {n}: land-land strait needs a sea 'Through' province (got {thr})", line=n)
                elif ends == ("sea", "sea") and typ.get(thr) != "land":
                    R.err("ADJ_THROUGH", f"adjacencies.csv line {n}: sea-sea canal needs a land 'Through' province (got {thr})", line=n)
                elif ends not in (("land", "land"), ("sea", "sea")):
                    R.warn("ADJ_SEA_MIXED", f"adjacencies.csv line {n}: sea adjacency between {ends} has no vanilla precedent", line=n)
            if all(0 < q < N and area[q] for q in (f_, t_)):
                cf, ct = float(cent_x[f_]), float(cent_x[t_])
                band = SEAM_BAND * W
                if min(cf, ct) < band and max(cf, ct) >= W - band:
                    R.warn("ADJ_SEAM_LINK", f"adjacencies.csv line {n}: {f_} -> {t_} ({kind or 'empty type'}) links opposite sides of the wrap seam (centroid x {cf:.0f} / {ct:.0f} of {W}); 'sea' rows across the seam crash at start, empty-type rows are measured unwrapped", line=n)
            if len(s) > 8 and s[8] and rules and s[8] not in rules:
                R.err("ADJ_RULE", f"adjacencies.csv line {n}: rule '{s[8]}' not in adjacency_rules.txt", line=n)
            if kind != "impassable":
                extra[f_].add(t_); extra[t_].add(f_)
    else:
        R.err("MISSING_FILE", "map/adjacencies.csv missing")

    # ------------------------------------------------------- strategic regions
    p2r = collections.defaultdict(list)
    regions = {}
    region_file = {}
    for f in list_dir(root, van, "map/strategicregions"):
        t = read_text(f)
        m = re.search(r"\bid\s*=\s*(\d+)", t)
        if not m:
            R.err("SR_NO_ID", f"{os.path.basename(f)} has no id"); continue
        rid = int(m.group(1))
        if rid in regions:
            R.err("SR_DUP_ID", f"strategic region id {rid} defined twice ({os.path.basename(f)})")
        pv = [int(v) for v in (brace_block(t, "provinces") or "").split()]
        regions[rid] = pv
        region_file[rid] = os.path.basename(f)
        if not re.search(r"\bweather\s*=\s*\{", t):
            R.warn("SR_NO_WEATHER", f"strategic region {rid} has no weather block")
        for q in pv:
            p2r[q].append(rid)
    if regions:
        miss = [i for i in range(1, N) if i not in p2r]
        if miss:
            R.err("SR_MISSING_PROVINCE", f"{len(miss)} provinces are in no strategic region", sample=miss[:20])
        dup = [q for q, v in p2r.items() if len(v) > 1]
        if dup:
            R.err("SR_DUP_PROVINCE", f"{len(dup)} provinces are in more than one strategic region", sample=dup[:20])
        undefined_p = [q for q in p2r if q not in typ]
        if undefined_p:
            R.err("SR_BAD_PROVINCE", f"{len(undefined_p)} strategic-region provinces are undefined", sample=undefined_p[:20])

    # ------------------------------------------- engine rules: region centre, naval contiguity (P00e)
    if regions and not args.no_engine_rules:
        boxes = bottom_up_boxes(xmin, xmax, ymin, ymax, H)
        van_sigs = None
        for rid in sorted(regions):
            c = region_centre([q for q in regions[rid] if 0 < q < N and area[q]], boxes, W)
            if c is None:
                continue
            facts = {k: c[k] for k in ("n", "mean", "rect", "dx", "dy", "mean_grid", "rect_grid", "dx_grid", "dy_grid")}
            where = f"strategic region {rid} ({region_file[rid]})"
            nums = (f"n {c['n']}, mean {c['mean']}, rect {c['rect']}, dx {c['dx']}, dy {c['dy']}; grid model mean "
                    f"{c['mean_grid']}, rect {c['rect_grid']}, dx {c['dx_grid']}, dy {c['dy_grid']}")
            if c["unsafe"]:
                R.err("REGION_CENTRE_DIV0", f"{where}: the engine's region-centre calculation divides by zero (crash at start): {'; '.join(c['clauses'])}; {nums}",
                      region=rid, file=region_file[rid], clauses=c["clauses"], **facts)
            elif c["unknown"]:
                twin = None
                if van:
                    if van_sigs is None:
                        same = (os.path.normpath(prov_path) == os.path.normpath(os.path.join(van, "map/provinces.bmp"))
                                and os.path.normpath(def_path) == os.path.normpath(os.path.join(van, "map/definition.csv")))
                        try:
                            van_sigs = vanilla_region_signatures(van, *((pid, N) if same else (None, None)))
                        except (OSError, ValueError):
                            van_sigs = {}   # no readable vanilla map: no twin, the WARN stands (conservative)
                    twin = van_sigs.get((W, H, c["signature"]))
                msg = (f"{where} wraps the seam (members touch x=0 and x={W - 1}) and its mean lies in no member box: "
                       f"the engine's fallback for wrapping regions is not modelled; {nums}")
                if twin is not None:
                    R.info("REGION_CENTRE_UNKNOWN", msg + f"; member boxes identical to vanilla region {twin}, which loads",
                           region=rid, file=region_file[rid], signature=c["signature"], vanilla_twin=twin, **facts)
                else:
                    R.warn("REGION_CENTRE_UNKNOWN", msg, region=rid, file=region_file[rid], signature=c["signature"], **facts)
        for rid, (lo, sep) in fractioned_naval(regions, typ, adj).items():
            R.err("SEA_REGION_FRACTIONED", f"naval strategic region {rid} ({region_file[rid]}) is fractioned (fatal MAP_ERROR): {len(sep)} sea provinces are separated from the piece holding its lowest sea province {lo}: {sep[:20]}{' ...' if len(sep) > 20 else ''}",
                  region=rid, file=region_file[rid], kept=lo, separated=sep)

    # ------------------------------------------------------------------ states
    cats = set()
    for f in list_dir(root, van, "common/state_category"):
        cats |= set(re.findall(r"^\s*([a-z_]+)\s*=\s*\{", brace_block(read_text(f), "state_categories") or "", re.M))
    states, p2s = {}, collections.defaultdict(list)
    for f in list_dir(root, van, "history/states"):
        t = read_text(f)
        body = brace_block(t, "state")
        if body is None:
            R.err("STATE_PARSE", f"{os.path.basename(f)}: no state = {{ }} block"); continue
        m = re.search(r"\bid\s*=\s*(\d+)", body)
        sid = int(m.group(1)) if m else None
        if sid is None:
            R.err("STATE_NO_ID", f"{os.path.basename(f)} has no id"); continue
        if sid in states:
            R.err("STATE_DUP_ID", f"state id {sid} defined twice ({os.path.basename(f)})")
        pv = [int(v) for v in (brace_block(body, "provinces") or "").split()]
        cat_all = re.findall(r"\bstate_category\s*=\s*\"?([a-z_]+)", body)
        if len(cat_all) > 1:
            R.warn("STATE_CATEGORY_DUP", f"state {sid}: state_category set {len(cat_all)} times ({', '.join(cat_all)}); which one wins is undefined", state=sid)
        cat = cat_all[0] if cat_all else None
        if cats and cat not in cats:
            R.err("STATE_CATEGORY", f"state {sid}: unknown state_category '{cat}'", state=sid)
        if not re.search(r"\bmanpower\s*=", body):
            R.err("STATE_NO_MANPOWER", f"state {sid}: manpower missing", state=sid)
        hist = brace_block(body, "history") or ""
        if not re.search(r"\bowner\s*=", hist):
            R.warn("STATE_NO_OWNER", f"state {sid}: no owner in history", state=sid)
        for vp in re.findall(r"victory_points\s*=\s*\{\s*(\d+)\s+[\d.]+\s*\}", hist):
            if int(vp) not in pv:
                R.err("STATE_VP_OUTSIDE", f"state {sid}: victory point province {vp} not in state", state=sid)
        bld = brace_block(hist, "buildings") or ""
        for prov, inner in re.findall(r"\b(\d+)\s*=\s*\{([^}]*)\}", bld):
            prov = int(prov)
            if prov not in pv:
                R.err("STATE_BUILDING_OUTSIDE", f"state {sid}: provincial buildings on province {prov} not in state", state=sid)
            if "naval_base" in inner and not coastal.get(prov, False):
                R.err("STATE_NAVAL_NOT_COASTAL", f"state {sid}: naval_base on non-coastal province {prov}", state=sid)
        states[sid] = {"provinces": pv, "category": cat, "file": os.path.basename(f)}
        for q in pv:
            p2s[q].append(sid)
    if states:
        ids_ = sorted(states)
        if ids_ != list(range(1, len(ids_) + 1)):
            R.err("STATE_IDS", f"state ids must be 1..{len(ids_)} with no gaps (max is {ids_[-1]})")
        lands = [i for i in typ if i and typ[i] == "land"]
        orphan = [q for q in lands if q not in p2s]
        if orphan:
            R.err("STATE_ORPHAN_LAND", f"{len(orphan)} land provinces are in no state", sample=orphan[:20])
        dup = [q for q, v in p2s.items() if len(v) > 1]
        if dup:
            R.err("STATE_DUP_PROVINCE", f"{len(dup)} provinces are in more than one state", sample=dup[:20])
        seas = [q for q in p2s if typ.get(q) == "sea"]
        if seas:
            R.err("STATE_SEA_PROVINCE", f"{len(seas)} sea provinces are inside states", sample=seas[:20])
        if regions:
            cross = [s for s, v in states.items() if len({p2r[q][0] for q in v["provinces"] if p2r.get(q)}) > 1]
            if cross:
                R.err("STATE_CROSSES_REGION", f"{len(cross)} states span more than one strategic region", sample=cross[:20])
        empty = [s for s, v in states.items() if not v["provinces"]]
        if empty:
            R.err("STATE_EMPTY", f"{len(empty)} states have no provinces", sample=empty[:20])
        noncontig = []
        for s, v in states.items():
            ps = [q for q in v["provinces"] if typ.get(q) == "land"]
            if not ps:
                continue
            want, seen, st = set(ps), {ps[0]}, [ps[0]]
            while st:
                q = st.pop()
                for r_ in adj[q] | extra[q]:
                    if r_ in want and r_ not in seen:
                        seen.add(r_); st.append(r_)
            if len(seen) < len(want):
                noncontig.append(s)
        if noncontig:
            R.warn("STATE_NONCONTIGUOUS", f"{len(noncontig)} states are not land-contiguous (fine for archipelagos, suspicious otherwise)", sample=noncontig[:20])

    # ------------------------------------------------------ supply & railways
    rpath = find(root, van, "map/railways.txt")
    if rpath:
        for n, l in enumerate(open(rpath), 1):
            s = l.split()
            if not s:
                continue
            v = [int(z) for z in s]
            lvl, cnt, ps = v[0], v[1], v[2:]
            if cnt != len(ps):
                R.err("RAIL_COUNT", f"railways.txt line {n}: count {cnt} != {len(ps)} provinces", line=n)
            for q in ps:
                if typ.get(q) != "land":
                    R.err("RAIL_NOT_LAND", f"railways.txt line {n}: province {q} is not land", line=n)
                elif states and q not in p2s:
                    R.err("RAIL_NO_STATE", f"railways.txt line {n}: province {q} not in any state", line=n)
            for u, w in zip(ps, ps[1:]):
                if w not in adj[u] and w not in extra[u]:
                    R.err("RAIL_GAP", f"railways.txt line {n}: {u}->{w} are not adjacent", line=n)
    spath = find(root, van, "map/supply_nodes.txt")
    if spath:
        for n, l in enumerate(open(spath), 1):
            s = l.split()
            if len(s) < 2:
                continue
            q = int(s[1])
            if typ.get(q) != "land":
                R.err("SUPPLY_NOT_LAND", f"supply_nodes.txt line {n}: province {q} is not land", line=n)
            elif states and q not in p2s:
                R.err("SUPPLY_NO_STATE", f"supply_nodes.txt line {n}: province {q} not in any state", line=n)

    # --------------------------------------------------------------- buildings
    bpath = find(root, van, "map/buildings.txt")
    if bpath and states:
        bad_state, bad_sea = set(), 0
        for l in open(bpath, encoding="latin-1"):
            s = l.strip().split(";")
            if len(s) < 7:
                continue
            try:
                sid = int(s[0])
            except ValueError:
                continue
            if sid not in states:
                bad_state.add(sid)
            # 1.19.x writes naval_base_spawn; naval_base is the older name (1.14.1 baseline)
            if s[1] in ("naval_base_spawn", "naval_base"):
                try:
                    sp = int(float(s[6]))
                except ValueError:
                    sp = None
                if typ.get(sp) != "sea":
                    bad_sea += 1
        if bad_state:
            R.err("BUILDINGS_BAD_STATE", f"buildings.txt references {len(bad_state)} undefined states", sample=sorted(bad_state)[:20])
        if bad_sea:
            R.err("BUILDINGS_NAVAL_SEA", f"{bad_sea} naval_base_spawn lines lack a sea province in column 7")

    # ------------------------------------------------------------------ rivers
    rv = find(root, van, "map/rivers.bmp")
    if rv:
        rim = Image.open(rv)
        if rim.mode != "P":
            R.err("RIVERS_MODE", f"rivers.bmp must be 8-bit indexed (mode P), got {rim.mode}")
        else:
            ra = np.asarray(rim)
            used = set(np.unique(ra).tolist())
            if used - RIVER_INDICES:
                R.err("RIVERS_INDEX", f"rivers.bmp uses palette indices outside 0-11/254/255: {sorted(used - RIVER_INDICES)[:20]}")
            river = (ra <= 11)
            on_sea = int((river & sea).sum())
            if on_sea:
                R.warn("RIVERS_ON_SEA", f"{on_sea} river pixels lie on sea provinces")
            blocks = river[:-1, :-1] & river[1:, :-1] & river[:-1, 1:] & river[1:, 1:]
            if blocks.any():
                R.warn("RIVERS_THICK", f"{int(blocks.sum())} 2x2 river blocks (rivers must be 1 px wide)")

    # ---------------------------------------------------------------- summary
    R.info("SUMMARY", f"{R.count('ERROR')} errors, {R.count('WARN')} warnings",
           states=len(states), strategic_regions=len(regions), provinces=N - 1)
    by_code = collections.defaultdict(list)
    for i in R.items:
        by_code[(i["level"], i["code"])].append(i)
    for (lvl, code), its in by_code.items():
        for i in its[:args.max_per_code]:
            extra_ = {k: v for k, v in i.items() if k not in ("level", "code", "msg")}
            print(f"[{lvl}] {code}: {i['msg']}" + (f" {extra_}" if extra_ else ""))
        if len(its) > args.max_per_code:
            print(f"[{lvl}] {code}: ... {len(its) - args.max_per_code} more (see --json)")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(R.items, fh, indent=1, default=int)
    return 1 if R.count("ERROR") else 0


if __name__ == "__main__":
    sys.exit(main())
