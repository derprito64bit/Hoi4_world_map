#!/usr/bin/env python3
"""Work-unit board checks (run by overwatch before dispatch and before merge).

  python .claude/agentops/wu_check.py diff <WU-ID> [--base main] [--head <branch>]
      every file changed between base and head must match the WU's scope globs
  python .claude/agentops/wu_check.py overlap
      no two work units that are in_progress/review share a scope path
  python .claude/agentops/wu_check.py list [--status todo]

Board: docs/board/work_units.json  (schema in docs/AGENT_SYSTEM.md §4)
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scope_guard import glob_to_regex, matches  # noqa: E402

ROOT = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip() or "."
BOARD = os.path.join(ROOT, "docs", "board", "work_units.json")
ACTIVE = {"in_progress", "review", "changes_requested"}


def load():
    with open(BOARD, encoding="utf-8") as fh:
        return json.load(fh)


def find(board, wid):
    for w in board["work_units"]:
        if w["id"] == wid:
            return w
    sys.exit(f"unknown work unit {wid}")


def literal_prefix(g):
    cut = min([i for i in (g.find("*"), g.find("?")) if i >= 0] or [len(g)])
    return g[:cut]


def globs_overlap(a, b):
    """Conservative: overlap if either glob matches the other's literal prefix path or prefixes nest."""
    pa, pb = literal_prefix(a), literal_prefix(b)
    return pa.startswith(pb) or pb.startswith(pa) or matches(pa, [b]) or matches(pb, [a])


def cmd_diff(a):
    w = find(load(), a.wu)
    head = a.head or w.get("branch") or "HEAD"
    out = subprocess.run(["git", "diff", "--name-only", f"{a.base}...{head}"], capture_output=True, text=True, cwd=ROOT)
    if out.returncode:
        sys.exit(out.stderr)
    files = [f for f in out.stdout.split() if f]
    bad = [f for f in files if not matches(f, w["scope"])]
    print(f"{a.wu}: {len(files)} changed files, {len(bad)} outside scope {w['scope']}")
    for f in bad:
        print("  OUTSIDE:", f)
    return 1 if bad else 0


def cmd_overlap(a):
    ws = [w for w in load()["work_units"] if w["status"] in ACTIVE]
    clash = 0
    for i, x in enumerate(ws):
        for y in ws[i + 1:]:
            for gx in x["scope"]:
                for gy in y["scope"]:
                    if globs_overlap(gx, gy):
                        print(f"OVERLAP {x['id']} [{gx}] <-> {y['id']} [{gy}]"); clash += 1
    print(f"{len(ws)} active work units, {clash} overlaps")
    return 1 if clash else 0


def cmd_list(a):
    for w in load()["work_units"]:
        if a.status and w["status"] != a.status:
            continue
        print(f"{w['id']:14s} {w['status']:18s} {w['agent']:18s} {w['title']}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    d = sp.add_parser("diff"); d.add_argument("wu"); d.add_argument("--base", default="main"); d.add_argument("--head")
    sp.add_parser("overlap")
    l = sp.add_parser("list"); l.add_argument("--status")
    a = ap.parse_args()
    return {"diff": cmd_diff, "overlap": cmd_overlap, "list": cmd_list}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
