#!/usr/bin/env python3
"""TOO LARGE BOX analysis (P00b-f6): box table of every tested host, candidate rules, probe predictions.

    python tools/experiments/diag02.py                          builds from build/experiments
    python tools/experiments/diag02.py --build-root DIR [--build-root DIR2]   builds from other folders (first hit)

Reads vanilla ($HOI4_GAME_DIR) and the built EXP-02 / EXP-02b / EXP-02c folders (layered over
vanilla); writes nothing. Prints:

1. vanilla's maximum of every metric in ``boxrules.METRICS`` and the province holding it;
2. every host in ``boxrules.OBSERVED`` re-measured from its build: pixel box (w, h), 2-px-grid
   engine box, w*h, w+h and pixel count, with the -debug observation;
3. which single-metric rules the observations reject and which candidate families survive
   (``boxrules.candidates``), with their threshold intervals;
4. the prediction of each surviving family for every EXP-02c probe build.

Exit 1 if a pinned box in ``OBSERVED`` or a built probe's host box differs from the map (a build or
the game changed), or if two candidate families predict patterns no outcome can tell apart.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from experiments import boxrules  # noqa: E402
from experiments.common import BUILD_ROOT, game_dir  # noqa: E402
from experiments.diag03 import load_map  # noqa: E402
from experiments.mapdata import areas, bboxes  # noqa: E402


def measure(pid: np.ndarray, d, ids, label: str, flagged=None) -> list:
    """[Box] for ``ids`` on one map."""
    n = d.n
    x0, x1, y0, y1 = bboxes(pid, n)
    a = areas(pid, n)
    out = []
    for i in ids:
        i = int(i)
        out.append(boxrules.Box(label, i, d.rows[i][4], int(x0[i]), int(x1[i]), int(y0[i]), int(y1[i]), int(a[i]),
                                flagged))
    return out


def vanilla_maxima(pid: np.ndarray, d) -> dict:
    """{metric: (value, province id)} over every vanilla province (ties: lowest id)."""
    boxes = [b for b in measure(pid, d, range(1, d.n), "vanilla") if b.x1 >= 0]
    out = {}
    for name, m in boxrules.METRICS.items():
        vals = [(m(b), -b.pid) for b in boxes]
        v, neg = max(vals)
        out[name] = (v, -neg)
    return out


def row(b: boxrules.Box) -> str:
    ex, ey, ew, eh = b.engine()
    obs = {True: "TOO LARGE BOX", False: "clean", None: "not run with -debug"}[b.flagged]
    if b.confounded:
        obs += " (enclaves)"
    return (f"  {b.label:20s} {b.pid:6d} {b.kind:4s}  w {b.w:5d}  h {b.h:4d}  engine ({ex}, {ey}, {ew}, {eh})  "
            f"w*h {b.w * b.h:7d}  w+h {b.w + b.h:5d}  px {b.pixels:6d}  -> {obs}")


def find_build(roots, bid: str):
    """The first ``root / bid`` folder that exists, else None."""
    for r in roots:
        if (Path(r) / bid).is_dir():
            return Path(r) / bid
    return None


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    roots = []
    while argv[:1] == ["--build-root"]:
        roots.append(Path(argv[1]))
        argv = argv[2:]
    roots = roots or [BUILD_ROOT]
    game = game_dir()
    if game is None:
        raise SystemExit("HOI4_GAME_DIR is not set (or not a HOI4 install)")
    from experiments.exp02c import PROBES, distinct, patterns
    pid, d = load_map(None, game)
    print("== vanilla 1.19.3: maximum of each metric over all provinces")
    for name, (v, i) in vanilla_maxima(pid, d).items():
        print(f"  {name:16s} {v:>10}  (province {i})")
    drift = 0
    maps = {"vanilla": (pid, d)}
    print("== observed hosts (re-measured) and the -debug result")
    for b in boxrules.OBSERVED:
        if b.label not in maps:
            p = find_build(roots, b.label)
            maps[b.label] = load_map(p, game) if p is not None else None
        if maps[b.label] is None:
            print(f"  {b.label:20s} {b.pid:6d}  not built in {', '.join(map(str, roots))}: pinned values used")
            print(row(b))
            continue
        got, = measure(*maps[b.label], [b.pid], b.label, b.flagged)
        if (got.x0, got.x1, got.y0, got.y1, got.pixels) != (b.x0, b.x1, b.y0, b.y1, b.pixels):
            drift += 1
            print(f"  DRIFT {b.label} {b.pid}: pinned {(b.x0, b.x1, b.y0, b.y1, b.pixels)}, "
                  f"map {(got.x0, got.x1, got.y0, got.y1, got.pixels)}")
        print(row(b))
    print("== single-metric rules 'm > T' the observations reject (max clean >= min flagged)")
    for name, lo, hi in boxrules.rejected():
        print(f"  {name:16s} clean up to {lo}, flagged from {hi}")
    print("== surviving candidate families")
    cands = boxrules.candidates()
    for cid, text, _ in cands:
        print(f"  {cid}: {text}")
    for f in boxrules.grid_families():
        print(f"  (grid, not separated by the probes) {f.name} > K, K in [{f.lo}, {f.hi})")
    print("== predictions for the EXP-02c probes (F = TOO LARGE BOX, c = clean, ? = depends on the threshold)")
    print("  " + " " * 30 + "  ".join(f"{cid:>3s}" for cid, _, _ in cands) + "   box w x h, w*h, w+h")
    for bid, p in PROBES.items():
        b = p.boxrule_box()
        where = find_build(roots, bid)
        seen = ""
        if where is not None:
            got, = measure(*load_map(where, game), [p.host], bid)
            ok = (got.x0, got.x1, got.y0, got.y1) == p.box
            drift += not ok
            seen = f", built: host {p.host} box {'as designed' if ok else f'DRIFT {(got.x0, got.x1, got.y0, got.y1)}'}"
        print(f"  {bid:30s}" + "  ".join(f"{fn(b):>3s}" for _, _, fn in cands)
              + f"   {p.w} x {p.h}, {p.w * p.h}, {p.w + p.h}{seen}")
    same = distinct(patterns())
    print("  families the four builds cannot tell apart: " + (", ".join(f"{a}/{b}" for a, b in same) or "none"))
    return 1 if drift or same else 0


if __name__ == "__main__":
    sys.exit(main())
