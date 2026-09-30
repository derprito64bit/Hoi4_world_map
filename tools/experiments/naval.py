#!/usr/bin/env python3
"""Naval-region contiguity for every build (P00b-f7): a kit-wide ``--check`` rule.

    python tools/experiments/naval.py                              every build present below build/experiments
    python tools/experiments/naval.py EXP-09a EXP-08-6144x2560     selected builds
    python tools/experiments/naval.py --build-root DIR EXP-09a     builds from another build folder

The engine refuses a map whose naval strategic region is not one piece: ``MAP_ERROR: Naval
strategic region <name> is fractioned! The following provinces are separated from the rest:``
(fatal: singleplayer cannot start). The rule is P00b-f6's (``boxfill.fractioned_naval`` /
``boxfill.fractioned_parts``, the one shared implementation): only the region's ``sea`` members
count, they must be one piece by 4-neighbour pixel contact across the wrap seam, adjacencies.csv
links do not join them, and the separated provinces are those outside the largest piece. It
reproduces every such line the game has logged (EXP-02b-block-400, EXP-09a; tests) and passes
vanilla 1.19.3 (98 naval regions).

A build is read layered over the vanilla install ($HOI4_GAME_DIR): provinces.bmp and
definition.csv from the build if present, region files by name (a build file replaces the
vanilla file of the same name; a ``replace_path`` covering map/strategicregions drops vanilla's).
Findings documented for a concluded build (``registry.KNOWN_FRACTIONED``) are notes when they
match exactly; anything else fails. Writes nothing; exit 1 on any failure.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.bmpio import read_bmp  # noqa: E402
from experiments.boxfill import fractioned_parts  # noqa: E402
from experiments.common import BUILD_ROOT, KitError, decode, game_dir  # noqa: E402
from experiments.mapdata import Definition, block_ids, pid_from_rgb  # noqa: E402

REGIONS = "map/strategicregions"
MAP_FILES = ("map/provinces.bmp", "map/definition.csv")


VANILLA_LOC = "localisation/english/strategic_region_names_l_english.yml"
LOC_LINE = re.compile(r'^\s*STRATEGICREGION_(\d+):\d*\s*"([^"]*)"', re.M)


def region_name(file_name: str) -> str:
    """'88-Bering Sea.txt' -> 'Bering Sea': the fallback when a region has no localised name."""
    stem = file_name.rsplit(".", 1)[0]
    return re.sub(r"^\s*\d+\s*-\s*", "", stem)


def loc_names(build: Path | None, game: Path) -> dict:
    """{region id: English name} as the engine prints it in the MAP_ERROR line: vanilla's
    ``STRATEGICREGION_<id>`` keys, overridden by the build's own english .yml files. The file names
    differ from these (vanilla '95-Western pacific 2.txt' is 'West Emperor Chain' in game)."""
    texts = []
    p = Path(game) / VANILLA_LOC
    if p.is_file():
        texts.append(decode(p.read_bytes()))
    if build is not None and (Path(build) / "localisation").is_dir():
        texts += [decode(q.read_bytes()) for q in sorted((Path(build) / "localisation").rglob("*_l_english.yml"))]
    out = {}
    for t in texts:
        out.update({int(k): v for k, v in LOC_LINE.findall(t)})
    return out


def _region_texts(build: Path | None, game: Path, replaced: bool = False):
    """[(file name, text)] of the region files the game reads for this build, sorted by name."""
    names = set() if replaced else {p.name for p in (Path(game) / REGIONS).iterdir() if p.is_file()}
    if build is not None and (Path(build) / REGIONS).is_dir():
        names |= {p.name for p in (Path(build) / REGIONS).iterdir() if p.is_file()}
    out = []
    for f in sorted(names):
        p = Path(build) / REGIONS / f if build is not None else None
        if p is None or not p.is_file():
            p = Path(game) / REGIONS / f
        out.append((f, decode(p.read_bytes())))
    return out


def province_region(texts) -> dict:
    """{province id: (region id, file name)} from [(file name, text)]; a province listed twice keeps the last."""
    out = {}
    for f, t in texts:
        m = re.search(r"\bid\s*=\s*(\d+)", re.sub(r"#[^\n]*", "", t))
        if m is None:
            raise KitError(f"strategic region {f}: no id")
        rid = int(m.group(1))
        for p in block_ids(t, "provinces", 1):
            out[p] = (rid, f)
    return out


def findings(pid: np.ndarray, types: np.ndarray, pregion: dict, loc: dict | None = None) -> dict:
    """{region name: sorted separated sea provinces} for every fractioned naval region (empty = clean).
    Names: ``loc`` ({region id: localised name}), else from the file name."""
    loc = loc or {}
    names = {rid: loc.get(rid) or region_name(f) for rid, f in pregion.values()}
    parts = fractioned_parts(pid, pregion, types)
    out = {}
    for rid, ids in sorted(parts.items()):
        key = names[rid] if names[rid] not in out else f"{names[rid]} ({rid})"
        out[key] = ids
    return out


def _touches_map(build: Path | None) -> bool:
    return build is not None and (any((Path(build) / r).is_file() for r in MAP_FILES)
                                  or (Path(build) / REGIONS).is_dir())


def build_findings(build: Path | None, game: Path, vanilla=None, replace_paths=()) -> dict:
    """``findings`` for a build layered over vanilla (``build`` None = vanilla itself).

    ``vanilla``: an optional ``vanilla.Vanilla`` whose cached pid / types are reused (and whose own result is
    cached on it) when the build changes none of provinces.bmp, definition.csv and the region files."""
    replaced = any(REGIONS == r.strip("/") or REGIONS.startswith(r.strip("/") + "/") for r in replace_paths)
    if vanilla is not None and not _touches_map(build) and not replaced:
        if getattr(vanilla, "_naval_findings", None) is None:
            vanilla._naval_findings = findings(np.asarray(vanilla.pid), vanilla.types, vanilla.province_region,
                                               loc_names(None, game))
        return dict(vanilla._naval_findings)
    game = Path(game)

    def layered(rel):
        if build is not None and (Path(build) / rel).is_file():
            return Path(build) / rel
        return game / rel
    d = Definition.parse(decode(layered("map/definition.csv").read_bytes()))
    pid = pid_from_rgb(read_bmp(layered("map/provinces.bmp").read_bytes()).pixels, d.colors())
    return findings(pid, d.types(), province_region(_region_texts(build, game, replaced)), loc_names(build, game))


def describe(found: dict, limit: int = 10) -> list:
    """One line per fractioned region, as the engine words it."""
    return [f"naval strategic region '{name}' is fractioned (fatal MAP_ERROR); separated from the rest: "
            f"{ids[:limit]}{' ...' if len(ids) > limit else ''} ({len(ids)} provinces)"
            for name, ids in sorted(found.items())]


def judge(build_id: str, found: dict, known: dict | None = None) -> tuple:
    """(problems, notes): findings that exactly match the build's documented expectation are notes."""
    from experiments.registry import KNOWN_FRACTIONED
    known = (KNOWN_FRACTIONED.get(build_id) if known is None else known) or None     # {} = nothing documented
    if not found and not known:
        return [], []
    if known is not None and found == known["regions"]:
        return [], [f"naval contiguity: expected finding ({known['why']}): " + "; ".join(describe(found, 5))]
    probs = describe(found)
    if known is not None:
        probs.append(f"naval contiguity: the documented finding for {build_id} does not match "
                     f"(expected regions {sorted(known['regions'])}, found {sorted(found)})")
    return probs, []


def check_build(ctx, exp, build_id: str, out: Path) -> tuple:
    """(problems, notes) of the naval-contiguity rule for one build folder (build.py --check, every build)."""
    try:
        found = build_findings(out, ctx.game, ctx.vanilla, _replace_paths(exp, build_id))
    except (OSError, KitError) as e:
        return [f"naval contiguity: cannot read the build: {e}"], []
    return judge(build_id, found)


def _replace_paths(exp, build_id: str):
    return exp.replace_paths(build_id) if exp is not None else ()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = BUILD_ROOT
    if argv[:1] == ["--build-root"]:
        root, argv = Path(argv[1]), argv[2:]
    game = game_dir()
    if game is None:
        raise SystemExit("HOI4_GAME_DIR is not set (or not a HOI4 install)")
    from experiments.registry import RETIRED, experiment_for
    from experiments.vanilla import Vanilla
    v = Vanilla(game)
    builds = argv or sorted(p.name for p in root.iterdir() if p.is_dir() and p.name.startswith("EXP-"))
    van = build_findings(None, game)
    print(f"{'FAIL' if van else 'OK  '} vanilla: {len(van)} fractioned naval regions")
    bad = bool(van)
    for b in builds:
        p = root / b
        if not p.is_dir():
            print(f"FAIL {b}: not built")
            bad = True
            continue
        if b in RETIRED:
            print(f"SKIP {b}: retired (registry.RETIRED)")
            continue
        probs, notes = judge(b, build_findings(p, game, v, _replace_paths(experiment_for(b), b)))
        print(f"{'FAIL' if probs else 'OK  '} {b}: " + ("fractioned naval regions" if probs else
                                                          "every naval region is one piece" if not notes else
                                                          "documented finding only"))
        for n in notes:
            print(f"    NOTE {n}")
        for x in probs:
            print(f"    - {x}")
        bad |= bool(probs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
