#!/usr/bin/env python3
"""Build / check / validate the P00b in-game experiment mods.

    python tools/experiments/build.py EXP-01|EXP-03-20k|all            build into build/experiments/<ID>/
    python tools/experiments/build.py all --check                      compare each build with vanilla
    python tools/experiments/build.py all --validate                   run validate_map.py on each build
    python tools/experiments/build.py list                             list build ids

Vanilla files are read from $HOI4_GAME_DIR (fallback: .claude/settings.local.json)
at build time and written only below build/experiments/ (gitignored).
--check writes nothing: it re-reads each build and the vanilla files and fails
(exit 1) unless only the intended property differs.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.base import Ctx  # noqa: E402
from experiments.common import BUILD_ROOT, REPO_ROOT, KitError, game_dir, reset_dir, sha256_tree, write_bytes  # noqa: E402
from experiments.registry import resolve  # noqa: E402

VALIDATOR = REPO_ROOT / ".claude" / "skills" / "hoi4-map-modding" / "scripts" / "validate_map.py"
META_DIR = BUILD_ROOT / "_meta"


def make_ctx() -> Ctx:
    g = game_dir()
    if g is None:
        raise SystemExit("HOI4_GAME_DIR is not set (or not a HOI4 install); see .claude/settings.local.json")
    from experiments.vanilla import Vanilla
    return Ctx(game=g, vanilla=Vanilla(g), repo_root=REPO_ROOT)


def build_into(ctx, exp, bid, out: Path) -> dict:
    """Build one experiment into an (empty) folder: mod content, descriptor.mod, README.txt."""
    info = exp.build(ctx, bid, out)
    write_bytes(out, "descriptor.mod", exp.descriptor(bid).encode("utf-8"))
    write_bytes(out, "README.txt", exp.readme(ctx, bid, info).encode("utf-8"))
    return info


def build_one(ctx, exp, bid) -> dict:
    t0 = time.time()
    out = reset_dir(BUILD_ROOT / bid)
    info = build_into(ctx, exp, bid, out)
    hashes = sha256_tree(out)
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    meta = {"build_id": bid, "seconds": round(time.time() - t0, 1), "bytes": size, "files": hashes,
            "info": json.loads(json.dumps(info, default=str))}
    META_DIR.mkdir(parents=True, exist_ok=True)
    (META_DIR / f"{bid}.json").write_text(json.dumps(meta, indent=1, sort_keys=True), encoding="utf-8")
    print(f"built {bid}: {len(hashes)} files, {size / 1e6:.1f} MB, {meta['seconds']} s")
    return meta


def check_one(ctx, exp, bid) -> bool:
    out = BUILD_ROOT / bid
    if not out.is_dir():
        print(f"FAIL {bid}: not built (run build.py {bid} first)")
        return False
    t0 = time.time()
    exp.check_notes = []                  # documented known risks the check allowed: printed, not failures
    try:
        probs = exp.check(ctx, bid, out)
    except KitError as e:
        probs = [str(e)]
    for n in exp.check_notes:
        print(f"NOTE {bid}: {n}")
    if probs:
        print(f"FAIL {bid}: extra differences vs vanilla:")
        for p in probs:
            print(f"    - {p}")
        return False
    print(f"OK   {bid}: only the intended property differs ({time.time() - t0:.1f} s)")
    return True


def validate_one(ctx, exp, bid) -> bool:
    out = BUILD_ROOT / bid
    js = BUILD_ROOT / f"validate_{bid}.json"
    cmd = [sys.executable, str(VALIDATOR), str(out), "--vanilla", str(ctx.game), "--bbox-limit", "250",
           "--bbox-limit-sea", "180", "--json", str(js)]
    if not out.is_dir():
        print(f"FAIL {bid}: not built")
        return False
    if js.exists():
        js.unlink()                       # a stale report must never count as this run's result
    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        items = json.loads(js.read_text())
        if js.stat().st_mtime < t0 - 1:
            raise ValueError("stale report")
    except (OSError, ValueError):
        print(f"FAIL {bid}: validator produced no fresh report (exit {res.returncode}): {res.stderr.strip()[-300:]}")
        return False
    errs = {i["code"] for i in items if i["level"] == "ERROR"}
    warns = {i["code"] for i in items if i["level"] == "WARN"}
    want = exp.expected(bid)
    # validate_map.py: 0 = no ERROR, 1 = ERROR findings, anything else = it could not run
    rc_ok = res.returncode == (1 if want.errors else 0)
    if not rc_ok:
        print(f"FAIL {bid}: validator exit code {res.returncode}, expected {1 if want.errors else 0}")
    ok = rc_ok and errs == want.errors and warns <= want.warns
    tag = "OK  " if ok else "FAIL"
    print(f"{tag} {bid}: ERROR {sorted(errs) or '-'}  WARN {sorted(warns) or '-'}  "
          f"(expected ERROR {sorted(want.errors) or '-'}, WARN within baseline) {time.time() - t0:.0f} s")
    for i in items:
        if i["level"] == "ERROR" or i["code"] == "BBOX_LARGE":
            print(f"       [{i['level']}] {i['code']}: {i['msg']} {i.get('sample', '')}")
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="EXP-xx, a build id (e.g. EXP-03-20k), 'all' or 'list'")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="compare existing builds with vanilla; writes nothing")
    g.add_argument("--validate", action="store_true", help="run validate_map.py on existing builds")
    a = ap.parse_args(argv)
    ctx = make_ctx()
    if a.target.lower() == "list":
        for e, b in resolve(ctx, "all"):
            print(b)
        return 0
    todo = resolve(ctx, a.target)
    ok = True
    for exp, bid in todo:
        if a.check:
            ok &= check_one(ctx, exp, bid)
        elif a.validate:
            ok &= validate_one(ctx, exp, bid)
        else:
            try:
                build_one(ctx, exp, bid)
            except KitError as e:
                print(f"FAIL {bid}: {e}")
                ok = False
    if a.check:
        print("check: " + ("all builds differ from vanilla only in their intended property" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
