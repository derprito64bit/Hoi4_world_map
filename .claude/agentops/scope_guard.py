#!/usr/bin/env python3
"""PreToolUse hook: block Write/Edit/NotebookEdit outside the calling agent's scope.

Reads the hook JSON from stdin (tool_name, tool_input.file_path / notebook_path,
cwd, agent_type when running inside a subagent). Scopes live in scopes.json next
to this file. Exit 2 + stderr = block (Claude Code hook contract); exit 0 = no
decision (normal permission flow continues).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def glob_to_regex(g):
    out, i = [], 0
    while i < len(g):
        if g.startswith("**", i):
            out.append(".*"); i += 2
            if i < len(g) and g[i] == "/":
                i += 1
                out[-1] = "(?:.*/)?"
        elif g[i] == "*":
            out.append("[^/]*"); i += 1
        elif g[i] == "?":
            out.append("[^/]"); i += 1
        else:
            out.append(re.escape(g[i])); i += 1
    return re.compile("^" + "".join(out) + "$")


def matches(path, globs):
    return any(glob_to_regex(g).match(path) for g in globs)


def repo_relative(path, cwd):
    p = path if os.path.isabs(path) else os.path.join(cwd or os.getcwd(), path)
    p = os.path.normpath(p)
    d = os.path.dirname(p)
    while True:  # nearest enclosing git checkout (worktrees have a .git file)
        if os.path.exists(os.path.join(d, ".git")):
            return os.path.relpath(p, d).replace("\\", "/")
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if data.get("tool_name") not in ("Write", "Edit", "NotebookEdit", "MultiEdit"):
        return 0
    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path")
    if not path:
        return 0
    rel = repo_relative(path, data.get("cwd"))
    if rel is None or rel.startswith(".."):
        return 0  # outside any repo (scratch files): not this hook's business
    with open(os.path.join(HERE, "scopes.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    agent = data.get("agent_type")
    if matches(rel, cfg["hard_deny_all"]):
        print(f"scope_guard: '{rel}' is generated output — change the generator in tools/ and rebuild; never edit it directly.", file=sys.stderr)
        return 2
    if agent:
        if matches(rel, cfg.get("agent_exceptions", {}).get(agent, [])):
            return 0
        if matches(rel, cfg["hard_deny_subagents"]):
            print(f"scope_guard: subagents may not edit '{rel}' (project rules/prompts). Propose the change in your report instead.", file=sys.stderr)
            return 2
        allowed = cfg["agents"].get(agent)
        if allowed is not None and not matches(rel, allowed):
            print(f"scope_guard: agent '{agent}' may only write {allowed}; '{rel}' is outside its scope. Report what needs to change instead.", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
