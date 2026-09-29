#!/usr/bin/env python3
"""EXP-03 crash diagnosis (P00b-f3): compare builds on the properties the map loader reads.

    python tools/experiments/diag03.py                         vanilla + every EXP-03 build present
    python tools/experiments/diag03.py EXP-03-24k EXP-03-30k   selected builds (vanilla always first)

Reads build/experiments/<ID>/ layered over the vanilla install ($HOI4_GAME_DIR);
writes nothing. Per build it prints the province-level features that were ruled
in or out for the 24k crash and, most importantly, the strategic-region centre
model of ``regioncentre.py``: how many regions take the engine's fallback path and
which of them divide by zero (the EXP-03-24k crash). Exit 1 if any build has an
unsafe region.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.bmpio import read_bmp  # noqa: E402
from experiments.common import BUILD_ROOT, KitError, decode, game_dir  # noqa: E402
from experiments.mapdata import Definition, adjacency_pairs, areas, block_ids, pid_from_rgb  # noqa: E402
from experiments.regioncentre import region_centres  # noqa: E402

FOUR = [[0, 1, 0], [1, 1, 1], [0, 1, 0]]


def _layered(build: Path | None, game: Path, rel: str) -> Path:
    if build is not None and (build / rel).is_file():
        return build / rel
    return game / rel


def load_map(build: Path | None, game: Path):
    """(pid, Definition) of a build layered over vanilla."""
    d = Definition.parse(decode(_layered(build, game, "map/definition.csv").read_bytes()))
    pid = pid_from_rgb(read_bmp(_layered(build, game, "map/provinces.bmp").read_bytes()).pixels, d.colors())
    return pid, d


def load_regions(build: Path | None, game: Path) -> dict:
    """{region id: [province ids]} from map/strategicregions (build files replace vanilla files by name)."""
    names = {p.name for p in (game / "map/strategicregions").iterdir() if p.is_file()}
    if build is not None and (build / "map/strategicregions").is_dir():
        names |= {p.name for p in (build / "map/strategicregions").iterdir() if p.is_file()}
    out = {}
    for f in sorted(names):
        t = decode(_layered(build, game, "map/strategicregions/" + f).read_bytes())
        m = re.search(r"\bid\s*=\s*(\d+)", re.sub(r"#[^\n]*", "", t))
        if m is None:
            raise KitError(f"strategic region {f}: no id")
        out[int(m.group(1))] = block_ids(t, "provinces", 1)
    return out


def region_names(build: Path | None, game: Path) -> dict:
    out = {}
    for f in sorted(p.name for p in (game / "map/strategicregions").iterdir() if p.is_file()):
        t = decode(_layered(build, game, "map/strategicregions/" + f).read_bytes())
        m = re.search(r"\bid\s*=\s*(\d+)", re.sub(r"#[^\n]*", "", t))
        if m:
            out[int(m.group(1))] = f
    return out


def features(pid: np.ndarray, d: Definition) -> dict:
    """Province-level features that were compared across 16k/20k/24k/30k (all equal in kind)."""
    n = d.n
    a = areas(pid, n)
    objs = ndimage.find_objects(pid + 1)
    multi = 0
    for i in range(1, n):
        sl = objs[i]
        if sl is not None and ndimage.label(pid[sl] == i, structure=FOUR)[1] > 1:
            multi += 1
    same = np.ones(pid.shape, bool)
    same[1:] &= pid[1:] == pid[:-1]
    same[:-1] &= pid[:-1] == pid[1:]
    same[:, 1:] &= pid[:, 1:] == pid[:, :-1]
    same[:, :-1] &= pid[:, :-1] == pid[:, 1:]
    same[0, :] = same[-1, :] = False
    inner = np.bincount(pid[same].ravel(), minlength=n)
    nb = np.bincount(adjacency_pairs(pid).ravel(), minlength=n)
    cols = d.colors().astype(int)[1:]
    return {"provinces": n - 1, "min_area": int(a[1:].min()), "multi_part": multi,
            "no_interior_px": int((inner[1:] == 0).sum()), "min_neighbours": int(nb[1:].min()),
            "max_neighbours": int(nb[1:].max()), "rgb_byte_0": int((cols == 0).any(1).sum()),
            "rgb_byte_255": int((cols == 255).any(1).sum())}


def report(label: str, build: Path | None, game: Path) -> int:
    pid, d = load_map(build, game)
    f = features(pid, d)
    cs = region_centres(pid, load_regions(build, game))
    names = region_names(build, game)
    fb = [c for c in cs.values() if c.fallback]
    bad = [c for c in cs.values() if c.unsafe]
    near = sorted(fb, key=lambda c: (abs(c.divisor), c.region))[:3]
    print(f"== {label}: " + ", ".join(f"{k}={v}" for k, v in f.items()))
    print(f"   strategic regions {len(cs)}, fallback path {len(fb)}, divide-by-zero {len(bad)}; "
          f"closest: " + ", ".join(f"{c.region} (divisor {c.divisor})" for c in near))
    for c in bad:
        print(f"   UNSAFE region {c.region} {names.get(c.region, '?')}: {c.n} provinces, mean point {c.mean}, "
              f"rect {c.rect} -> centre x {c.rect[0] + c.rect[2] // 2}" + ("  [seam]" if c.seam else ""))
    return len(bad)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    game = game_dir()
    if game is None:
        raise SystemExit("HOI4_GAME_DIR is not set (or not a HOI4 install)")
    builds = argv or sorted(p.name for p in BUILD_ROOT.glob("EXP-03-*") if p.is_dir())
    bad = report("vanilla", None, game)
    for b in builds:
        p = BUILD_ROOT / b
        if not p.is_dir():
            print(f"== {b}: not built")
            continue
        bad += report(b, p, game)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
