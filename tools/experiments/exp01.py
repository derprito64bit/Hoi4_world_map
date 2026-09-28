"""EXP-01: link two NON-touching sea provinces with one adjacencies.csv row.

Pair (vanilla 1.19.3): From 2942 = the North Sea province off Rosyth / Firth of
Forth (Scotland's east coast), To 8314 = the Bristol Channel off Cardiff/Bristol
(Wales / England's west coast). They do not touch; the shortest ordinary sea
route between them is 7 sea provinces (around Scotland or through the English
Channel), so a working link shows up as a one-step route straight across
Britain. The build re-verifies all of this against the installed game.

Variant A: Type ``sea`` with a sea province as Through (Through = To).
Variant B: empty Type, Through -1 (the pattern vanilla uses for 7 rule-only rows
between touching seas).
"""
from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np

from . import texts
from .base import Expected, Experiment, check_descriptor, check_file_set
from .common import KitError, decode, encode, write_bytes
from .mapdata import SEA, adjacency_pairs

FROM, TO = 2942, 8314
MIN_ROUTE = 5          # ordinary sea route must be at least this many steps
ADJ = "map/adjacencies.csv"


def link_row(variant: str) -> str:
    if variant == "A":
        return f"{FROM};{TO};sea;{TO};-1;-1;-1;-1;;EXP-01A test link (sea type, sea Through)"
    if variant == "B":
        return f"{FROM};{TO};;-1;-1;-1;-1;-1;;EXP-01B test link (empty type, Through -1)"
    raise KitError(f"EXP-01 has no variant {variant!r}")


def insert_before_terminator(text: str, row: str) -> str:
    """Insert one row directly before the '-1;-1;' terminator line; everything else byte-identical."""
    lines = text.split("\n")
    idx = [i for i, ln in enumerate(lines) if ln.startswith("-1;-1;")]
    if len(idx) != 1:
        raise KitError(f"adjacencies.csv must contain exactly one terminator line (found {len(idx)})")
    if not lines[0].lower().startswith("from;to;type;through"):
        raise KitError("adjacencies.csv header row missing")
    lines.insert(idx[0], row)
    return "\n".join(lines)


def sea_route_length(pairs: np.ndarray, types: np.ndarray, a: int, b: int) -> int:
    """Steps between two sea provinces over pixel-adjacent seas only (-1 if unreachable)."""
    nb: dict = {}
    for u, v in pairs.tolist():
        if types[u] == SEA and types[v] == SEA:
            nb.setdefault(u, []).append(v)
            nb.setdefault(v, []).append(u)
    dist, q = {a: 0}, deque([a])
    while q:
        u = q.popleft()
        if u == b:
            return dist[u]
        for v in sorted(nb.get(u, [])):
            if v not in dist:
                dist[v] = dist[u] + 1
                q.append(v)
    return -1


class Exp01(Experiment):
    exp_id = "EXP-01"
    title = "sea-to-sea link between non-touching seas"
    priority = 1

    def build_ids(self, ctx):
        return ["EXP-01A", "EXP-01B"]

    def title_for(self, build_id):
        return self.title + (" (type sea, sea Through)" if build_id.endswith("A") else " (empty type, Through -1)")

    def expected(self, build_id):
        if build_id.endswith("A"):
            return Expected(errors={"ADJ_THROUGH"},
                            text="ERROR ADJ_THROUGH on the new line (the validator only knows vanilla's canal "
                                 "pattern, where a sea-sea 'sea' row needs a LAND Through); that is exactly the "
                                 "property under test. Otherwise " + texts.BASELINE_WARNS + ".")
        return Expected(text="No new finding: " + texts.BASELINE_WARNS + ".")

    def verify_pair(self, v):
        t = v.types
        if t[FROM] != SEA or t[TO] != SEA:
            raise KitError(f"EXP-01: {FROM} and {TO} must both be sea provinces in this game version")
        pairs = adjacency_pairs(np.asarray(v.pid))
        if ((pairs[:, 0] == min(FROM, TO)) & (pairs[:, 1] == max(FROM, TO))).any():
            raise KitError(f"EXP-01: {FROM} and {TO} touch; pick another pair")
        route = sea_route_length(pairs, t, FROM, TO)
        if route < MIN_ROUTE:
            raise KitError(f"EXP-01: ordinary route {FROM}->{TO} is only {route} steps")
        for ln in v.text(ADJ).split("\n")[1:]:
            s = ln.split(";")
            if len(s) > 1 and {s[0], s[1]} == {str(FROM), str(TO)}:
                raise KitError("EXP-01: vanilla already has a row for this pair")
        return route

    def build(self, ctx, build_id, out: Path):
        v = ctx.vanilla
        route = self.verify_pair(v)
        text = insert_before_terminator(v.text(ADJ), link_row(build_id[-1]))
        write_bytes(out, ADJ, encode(text))
        return {"route": route}

    def readme(self, ctx, build_id, info):
        var = build_id[-1]
        kind = ("Type 'sea' and Through = 8314 (a sea province)" if var == "A"
                else "an empty Type and Through = -1")
        return texts.readme(
            build_id, self.title_for(build_id),
            prop=f"map/adjacencies.csv gets ONE extra line that connects sea province {FROM} (North Sea, off "
                 f"Rosyth / Firth of Forth, east of Edinburgh) with sea province {TO} (Bristol Channel, off "
                 f"Cardiff and Bristol) using {kind}. The two seas do not touch; the normal sea route between "
                 f"them is {info.get('route', 7)} sea provinces long (around the north of Scotland or through "
                 "the English Channel). Everything else is the normal game.",
            why="Our Equal Earth map needs links between Pacific sea provinces that face each other across the "
                "left/right map edge but do not touch. Vanilla has no such sea-to-sea link; this test shows "
                "which way of writing the line makes ships use it (variant A vs. B, same instructions).",
            launch=texts.LAUNCH_DEBUG,
            steps=[
                "Start a new game (1936) as the United Kingdom. Pause the game (space bar).",
                "Find the 'Rosyth Escort Force' fleet at Rosyth (east coast of Scotland, next to Edinburgh). "
                "Select it (left-click the fleet or pick it in the navy list).",
                f"Right-click the sea just off Cardiff / Bristol (Bristol Channel, between South Wales and "
                f"Somerset; hover shows province {TO}). Look at the route line the game draws before unpausing.",
                "Take a screenshot of the route line. Straight across Britain in one step = the link works. "
                "A long line around Scotland or through the English Channel = the link is ignored.",
                "Unpause for a few days and check where the fleet actually goes. Take a second screenshot.",
                f"Also try the reverse: move the fleet back from {TO} to {FROM}.",
            ],
            send=["Link works: yes / no (from the route line), plus both screenshots.",
                  "Did the fleet really arrive after one move, and roughly how many days did it take?",
                  "Any strange icon (like a canal symbol) drawn across Britain?"],
            expected=self.expected(build_id).text,
            cannot=["EXP-01"], user_dir=ctx.user,
            notes=["Variant A and B are separate mods; install and test them one at a time (same steps)."])

    def check(self, ctx, build_id, out):
        probs = check_file_set(out, {ADJ}) + check_descriptor(self, build_id, out)
        p = out / ADJ
        if not p.is_file():
            return probs
        van = ctx.vanilla.text(ADJ).split("\n")
        got = decode(p.read_bytes()).split("\n")
        row = link_row(build_id[-1])
        if len(got) != len(van) + 1:
            probs.append(f"adjacencies.csv: expected exactly one extra line, got {len(got) - len(van)}")
            return probs
        k = next((i for i, (a, b) in enumerate(zip(van, got)) if a != b), len(van))
        if got[k] != row or got[:k] != van[:k] or got[k + 1:] != van[k:]:
            probs.append("adjacencies.csv: differs from vanilla by more than the one link row")
        if not got[k + 1].startswith("-1;-1;"):
            probs.append("adjacencies.csv: the link row is not directly before the terminator")
        return probs
