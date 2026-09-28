"""EXP-06: a block of open South Pacific becomes lake provinces (off-globe filler simulation).

The block is vanilla strategic region 113 "South Pacific": 39 sea provinces,
none coastal, none touching land, none named in adjacencies.csv, fleet
locations or naval-base spawns, and the rest of the ocean stays connected
without them (all re-verified at build time). The one property: those 39
provinces are ``lake`` instead of ``sea``, exactly as the planned off-globe
filler would be written:

* definition.csv   type sea -> lake, terrain ocean -> lakes (coastal false, continent 0 already)
* unitstacks.txt   their naval position lines removed (124 of 126 vanilla lakes have none)
Rasters stay as they are (heightmap 89, terrain index 15 = the off-globe plan),
the region file stays (it becomes a lake-only region, vanilla has one).
"""
from __future__ import annotations

import glob
import re
from collections import deque
from pathlib import Path

import numpy as np

from . import texts
from .base import Expected, Experiment, check_descriptor, check_file_set
from .common import KitError, decode, encode, write_bytes
from .mapdata import SEA, Definition, adjacency_links, adjacency_pairs, block_ids
from .positions import join_lines, split_lines

REGION_FILE = "113-South Pacific.txt"
REGION_ID = 113
DEF = "map/definition.csv"
STACKS = "map/unitstacks.txt"


def convert_to_lakes(d: Definition, ids) -> Definition:
    out = d.copy()
    for i in sorted(ids):
        r = out.rows[i]
        if r[4] != "sea":
            raise KitError(f"province {i} is not a sea province")
        r[4], r[5], r[6], r[7] = "lake", "false", "lakes", "0"
    return out


def drop_stacks(text: str, ids) -> str:
    ids = {str(i) for i in ids}
    lines, tr = split_lines(text)
    return join_lines([ln for ln in lines if ln.split(";", 1)[0] not in ids], tr)


class Exp06(Experiment):
    exp_id = "EXP-06"
    title = "open-ocean block as lake provinces (off-globe filler)"
    priority = 6

    def build_ids(self, ctx):
        return ["EXP-06"]

    def expected(self, build_id):
        return Expected(text="No new finding: " + texts.BASELINE_WARNS + ". (Lakes are allowed anywhere, in no "
                                                                         "state, in any region.)")

    def block(self, v):
        ids = block_ids(v.region_files[REGION_FILE], "provinces")
        t = v.types
        d = v.definition
        pairs = adjacency_pairs(np.asarray(v.pid))
        nb: dict = {}
        for a, b in pairs.tolist():
            nb.setdefault(a, set()).add(b)
            nb.setdefault(b, set()).add(a)
        refs = set()
        for a, b in adjacency_links(v.text("map/adjacencies.csv")):
            refs |= {a, b}
        for ln in v.text("map/adjacencies.csv").splitlines()[1:]:
            s = ln.split(";")
            if len(s) > 3 and s[3].strip().lstrip("-").isdigit():
                refs.add(int(s[3]))
        for f in sorted(glob.glob(str(v.root / "history" / "units" / "*.txt"))):
            with open(f, "rb") as fh:
                refs |= {int(x) for x in re.findall(rb"location\s*=\s*(\d+)", fh.read())}
        for ln in v.text("map/buildings.txt").splitlines():
            s = ln.split(";")
            if len(s) >= 7 and s[1] == "naval_base_spawn":
                refs.add(int(float(s[6])))
        for i in ids:
            if t[i] != SEA or d.rows[i][5] != "false":
                raise KitError(f"EXP-06: province {i} is not an open-sea province")
            if any(t[j] != SEA for j in nb.get(i, ())):
                raise KitError(f"EXP-06: province {i} touches a non-sea province")
            if i in refs:
                raise KitError(f"EXP-06: province {i} is referenced by adjacencies/units/naval bases")
        # the remaining sea stays one connected ocean
        blk = set(ids)
        seas = [i for i in range(1, len(t)) if t[i] == SEA and i not in blk]
        seen, q = {seas[0]}, deque([seas[0]])
        while q:
            u = q.popleft()
            for w in nb.get(u, ()):
                if t[w] == SEA and w not in blk and w not in seen:
                    seen.add(w)
                    q.append(w)
        if len(seen) != len(seas):
            raise KitError("EXP-06: removing the block would cut the ocean in two")
        ring = sorted({j for i in ids for j in nb.get(i, ()) if j not in blk})
        return sorted(ids), ring

    def build(self, ctx, build_id, out: Path):
        v = ctx.vanilla
        ids, ring = self.block(v)
        write_bytes(out, DEF, encode(convert_to_lakes(v.definition, ids).format()))
        write_bytes(out, STACKS, encode(drop_stacks(v.text(STACKS), ids)))
        pid = np.asarray(v.pid)
        ys, xs = np.nonzero(np.isin(pid, ids))
        # sea provinces just west / east of the block, on its middle row, for the owner's fleet test
        mid = int(np.median(ys))
        row = pid[mid]
        cols = np.nonzero(np.isin(row, ids))[0]
        west, east = int(row[cols.min() - 3]), int(row[cols.max() + 3])
        return {"ids": ids, "count": len(ids), "west": west, "east": east,
                "box": (int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max()))}

    def readme(self, ctx, build_id, info):
        return texts.readme(
            build_id, self.title,
            prop=f"The {info['count']} sea provinces of the strategic region 'South Pacific' (the empty ocean "
                 "between New Zealand and South America, roughly between Pitcairn and the Chatham Islands) are "
                 "turned into lake provinces, the same way our map will fill the area outside the curved Equal "
                 "Earth outline. The water still looks like ocean (same height and texture). Nothing else "
                 "changes.",
            why="Our map must fill the corners outside the globe with provinces that ships and armies can't "
                "enter. This checks that such 'lake' ocean renders cleanly and that fleets route around it.",
            launch=texts.LAUNCH_DEBUG,
            steps=["Start a new game (1936) as the United States or the United Kingdom and pause.",
                   "Pan to the South Pacific (east of New Zealand, west of Chile). Take a screenshot at medium "
                   "zoom and one close up. Hover a few tiles: they should say lake (debug shows the province "
                   f"number; the block is provinces {info['ids'][0]}..{info['ids'][-1]}, list in the kit).",
                   f"Select any fleet and order it to sea province {info['west']} (just west of the block), then to "
                   f"{info['east']} (just east of it). Screenshot the route line: it should go around the block, "
                   "never through it.",
                   "Try to order the fleet INTO the block. Note what the game says."],
            send=["Screenshots: medium zoom, close-up, the two route lines.",
                  "Does the block look like normal ocean? Any borders, colour seams, flicker, missing water?",
                  "Can a fleet enter the block (yes/no)? Does it route around it (yes/no)?",
                  "Map modes 'strategic region' and 'terrain': anything odd over the block?"],
            expected=self.expected(build_id).text, cannot=["EXP-06"], user_dir=ctx.user)

    def check(self, ctx, build_id, out):
        probs = check_file_set(out, {DEF, STACKS}) + check_descriptor(self, build_id, out)
        v = ctx.vanilla
        ids = set(block_ids(v.region_files[REGION_FILE], "provinces"))
        try:
            d = Definition.parse(decode((out / DEF).read_bytes()))
            stacks = decode((out / STACKS).read_bytes())
        except (OSError, KitError) as e:
            return probs + [f"cannot read output: {e}"]
        vd = v.definition
        if d.n != vd.n:
            return probs + ["definition.csv row count changed"]
        for i in range(vd.n):
            want = vd.rows[i] if i not in ids else [vd.rows[i][0], *vd.rows[i][1:4], "lake", "false", "lakes", "0"]
            if d.rows[i] != want:
                probs.append(f"definition.csv row {i} differs from the expected value")
                break
        vl, _ = split_lines(v.text(STACKS))
        gl, _ = split_lines(stacks)
        if gl != [ln for ln in vl if int(ln.split(";", 1)[0]) not in ids]:
            probs.append("unitstacks.txt differs by more than the removed block lines")
        return probs
