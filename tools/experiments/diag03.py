#!/usr/bin/env python3
"""EXP-03 crash diagnosis (P00b-f3): compare builds on the properties the map loader reads.

    python tools/experiments/diag03.py                           vanilla + every EXP-03 build present
    python tools/experiments/diag03.py EXP-03-24k EXP-03-30k     selected builds (vanilla always first)
    python tools/experiments/diag03.py --build-root DIR EXP-09a  builds from another build folder

Reads <build root>/<ID>/ layered over the vanilla install ($HOI4_GAME_DIR);
writes nothing. Per build it prints the province-level features that were ruled
in or out for the 24k crash and, most importantly, the conservative strategic-region
centre model of ``regioncentre.py``: how many regions take the engine's fallback
path, which of them divide by zero (the EXP-03-24k crash), and which wrapping
regions the model cannot judge (``unknown``). Exit 1 if any build has a guard
failure: an unsafe region, or an unknown one without an identical vanilla twin.
Failures listed in ``exp08.KNOWN_RISK`` for that build ID with the exact member-box
signature are printed as "KNOWN RISK (allowed)" and do not count.
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
from experiments.exp08 import KNOWN_RISK  # noqa: E402
from experiments.regioncentre import guard_failures, region_centres, split_known  # noqa: E402

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


def _region_texts(build: Path | None, game: Path):
    """Yield (region id, file name, text) for vanilla's and the build's region files (build replaces by name)."""
    names = {p.name for p in (game / "map/strategicregions").iterdir() if p.is_file()}
    if build is not None and (build / "map/strategicregions").is_dir():
        names |= {p.name for p in (build / "map/strategicregions").iterdir() if p.is_file()}
    for f in sorted(names):
        t = decode(_layered(build, game, "map/strategicregions/" + f).read_bytes())
        m = re.search(r"\bid\s*=\s*(\d+)", re.sub(r"#[^\n]*", "", t))
        if m is None:
            raise KitError(f"strategic region {f}: no id")
        yield int(m.group(1)), f, t


def load_regions(build: Path | None, game: Path) -> dict:
    """{region id: [province ids]} from map/strategicregions layered over vanilla."""
    return {rid: block_ids(t, "provinces", 1) for rid, _, t in _region_texts(build, game)}


def region_names(build: Path | None, game: Path) -> dict:
    """{region id: file name}, including region files that exist only in the build."""
    return {rid: f for rid, f, _ in _region_texts(build, game)}


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


def report(label: str, build: Path | None, game: Path, observed: dict | None = None) -> tuple:
    """Print one build's features and region-centre report; returns (guard failures, centres).

    ``observed``: centres of a map seen loading in game (vanilla; default: this map itself).
    Wrapping regions that take the fallback (``unknown``) pass only when identical to that twin.
    """
    pid, d = load_map(build, game)
    f = features(pid, d)
    cs = region_centres(pid, load_regions(build, game))
    names = region_names(build, game)
    observed = cs if observed is None else observed
    fails, known = split_known(guard_failures(cs, observed), cs, KNOWN_RISK.get(label))
    fb = [c for c in cs.values() if c.fallback]
    near = sorted((c for c in fb if not c.seam), key=lambda c: (min(abs(c.dx), abs(c.dy)), c.region))[:3]
    unknown = [c for c in cs.values() if c.unknown]
    print(f"== {label}: " + ", ".join(f"{k}={v}" for k, v in f.items()))
    print(f"   strategic regions {len(cs)}, fallback path {len(fb)} (under every convention "
          f"{sum(c.fallback_all for c in fb)}), unsafe {sum(c.unsafe for c in cs.values())}, "
          f"unknown (wrapping + fallback) {len(unknown)}; closest: "
          + ", ".join(f"{c.region} (dx {c.dx}, dy {c.dy}, gap {c.gap})" for c in near))
    for c in cs.values():
        if c.unsafe:
            why = " and ".join(w for w, z in (("dx", c.dx), ("dy", c.dy)) if z == 0)
            print(f"   UNSAFE region {c.region} {names.get(c.region, '?')}: {why} = 0, {c.n} provinces, mean point "
                  f"{c.mean}, rect {c.rect}, gap to nearest box {c.gap} px"
                  + ("" if c.fallback_all else " (fallback only under the strictest box convention)"))
    for c in unknown:
        twin = observed.get(c.region)
        tag = "identical in vanilla, observed loading" if twin is not None and twin.signature == c.signature else "NEW"
        print(f"   unknown region {c.region} {names.get(c.region, '?')}: wraps the seam, {c.n} provinces, "
              f"dx {c.dx}, dy {c.dy} -> {tag}")
    for n in known:                       # documented, signature-matched known risks (exp08.KNOWN_RISK)
        print(f"   {n}")
    print(f"   guard failures {len(fails)}" + (f" (+ {len(known)} KNOWN RISK allowed)" if known else ""))
    return fails, cs


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = BUILD_ROOT
    if argv[:1] == ["--build-root"]:
        root, argv = Path(argv[1]), argv[2:]
    game = game_dir()
    if game is None:
        raise SystemExit("HOI4_GAME_DIR is not set (or not a HOI4 install)")
    builds = argv or sorted(p.name for p in root.glob("EXP-03-*") if p.is_dir())
    fails, van = report("vanilla", None, game)
    bad = len(fails)
    for b in builds:
        p = root / b
        if not p.is_dir():
            print(f"== {b}: not built")
            continue
        bad += len(report(b, p, game, van)[0])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
