"""EXP-01: link two NON-touching sea provinces with one adjacencies.csv row.

Two pairs (vanilla 1.19.3), each in two row forms, = four builds:

* UK (control, link inside the map): From 2942 = North Sea off Rosyth / Firth of
  Forth, To 8314 = Bristol Channel. The ordinary route is 7 sea provinces
  (around Scotland or through the Channel); a working link is one step across
  Britain.
* SEAM (the real question): From 2560 = Sea of Okhotsk (right map edge, x~5358),
  To 3836 = Bering Sea just east of the date line (left map edge, x~7). They sit
  on opposite sides of vanilla's own wrap seam: ~283 px apart across the seam,
  ~5,350 px apart if the engine does not wrap. The ordinary route is 14 sea
  provinces around Kamchatka, so a link measured across the seam is clearly
  shorter; a link measured without the wrap would never be chosen.

Variant A: Type ``sea`` with a sea province as Through (Through = To).
Variant B: empty Type, Through -1 (the pattern vanilla uses for 7 rule-only rows
between touching seas). The build re-verifies every pair property against the
installed game.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np

from . import texts
from .base import Expected, Experiment, check_descriptor, check_file_set
from .common import KitError, decode, encode, write_bytes
from .mapdata import SEA, adjacency_pairs

PAIRS = {"UK": (2942, 8314), "SEAM": (2560, 3836)}
MIN_ROUTE = 5          # ordinary sea route must be at least this many steps
ADJ = "map/adjacencies.csv"
# kept for callers that use the control pair directly
FROM, TO = PAIRS["UK"]


def parse_id(build_id: str):
    """'EXP-01-SEAM-A' -> ('SEAM', 'A')."""
    parts = build_id.split("-")
    if len(parts) != 4 or parts[2] not in PAIRS or parts[3] not in ("A", "B"):
        raise KitError(f"not an EXP-01 build id: {build_id}")
    return parts[2], parts[3]


def link_row(variant: str, pair: str = "UK") -> str:
    a, b = PAIRS[pair]
    tag = f"EXP-01-{pair}-{variant}"
    if variant == "A":
        return f"{a};{b};sea;{b};-1;-1;-1;-1;;{tag} test link (sea type, sea Through)"
    if variant == "B":
        return f"{a};{b};;-1;-1;-1;-1;-1;;{tag} test link (empty type, Through -1)"
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
        return [f"EXP-01-{p}-{v}" for p in PAIRS for v in ("A", "B")]

    def title_for(self, build_id):
        pair, var = parse_id(build_id)
        where = "UK control pair" if pair == "UK" else "across the Pacific wrap seam"
        return f"{self.title}, {where} " + ("(type sea, sea Through)" if var == "A" else "(empty type, Through -1)")

    def expected(self, build_id):
        _, var = parse_id(build_id)
        if var == "A":
            return Expected(errors={"ADJ_THROUGH"},
                            text="ERROR ADJ_THROUGH on the new line (the validator only knows vanilla's canal "
                                 "pattern, where a sea-sea 'sea' row needs a LAND Through); that is exactly the "
                                 "property under test. Otherwise " + texts.BASELINE_WARNS + ".")
        return Expected(text="No new finding: " + texts.BASELINE_WARNS + ".")

    def verify_pair(self, v, pair: str = "UK"):
        a, b = PAIRS[pair]
        t = v.types
        if t[a] != SEA or t[b] != SEA:
            raise KitError(f"EXP-01: {a} and {b} must both be sea provinces in this game version")
        pid = np.asarray(v.pid)
        pairs = adjacency_pairs(pid)
        if ((pairs[:, 0] == min(a, b)) & (pairs[:, 1] == max(a, b))).any():
            raise KitError(f"EXP-01: {a} and {b} touch; pick another pair")
        route = sea_route_length(pairs, t, a, b)
        if route < MIN_ROUTE:
            raise KitError(f"EXP-01: ordinary route {a}->{b} is only {route} steps")
        for ln in v.text(ADJ).split("\n")[1:]:
            s = ln.split(";")
            if len(s) > 1 and {s[0], s[1]} == {str(a), str(b)}:
                raise KitError("EXP-01: vanilla already has a row for this pair")
        if pair == "SEAM":
            W = pid.shape[1]
            xa = np.nonzero(pid == a)[1].mean()
            xb = np.nonzero(pid == b)[1].mean()
            if not ((xa > 0.75 * W and xb < 0.25 * W) or (xa < 0.25 * W and xb > 0.75 * W)):
                raise KitError("EXP-01: the SEAM pair must sit on opposite sides of the wrap seam")
        return route

    def build(self, ctx, build_id, out: Path):
        pair, var = parse_id(build_id)
        v = ctx.vanilla
        route = self.verify_pair(v, pair)
        text = insert_before_terminator(v.text(ADJ), link_row(var, pair))
        write_bytes(out, ADJ, encode(text))
        return {"route": route}

    def readme(self, ctx, build_id, info):
        pair, var = parse_id(build_id)
        a, b = PAIRS[pair]
        kind = (f"Type 'sea' and Through = {b} (a sea province)" if var == "A" else "an empty Type and Through = -1")
        common_send = ["Link used: yes / no (from the route line), plus the screenshots.",
                       "Transit time in days for the move (and, if you can, for the ordinary route in the normal game).",
                       "Any strange icon (like a canal symbol) drawn along the link?"]
        notes = ["There are four EXP-01 mods: UK-A, UK-B (control: link inside the map) and SEAM-A, SEAM-B (link "
                 "across the left/right map edge). Install and test them one at a time; A and B differ only in "
                 "how the one line is written."]
        if pair == "UK":
            prop = (f"map/adjacencies.csv gets ONE extra line that connects sea province {a} (North Sea, off "
                    f"Rosyth / Firth of Forth, east of Edinburgh) with sea province {b} (Bristol Channel, off "
                    f"Cardiff and Bristol) using {kind}. The two seas do not touch; the normal sea route between "
                    f"them is {info.get('route', 7)} sea provinces long (around the north of Scotland or through "
                    "the English Channel). Everything else is the normal game.")
            steps = [
                "Start a new game (1936) as the United Kingdom. Pause the game (space bar).",
                "Find the 'Rosyth Escort Force' fleet at Rosyth (east coast of Scotland, next to Edinburgh). "
                "Select it (left-click the fleet or pick it in the navy list).",
                f"Right-click the sea just off Cardiff / Bristol (Bristol Channel, between South Wales and "
                f"Somerset; hover shows province {b}). Look at the route line the game draws before unpausing.",
                "Take a screenshot of the route line. Straight across Britain in one step = YES, the link is used. "
                "A long line around Scotland or through the English Channel = NO, the link is ignored.",
                "Unpause and note how many days the fleet needs; take a second screenshot.",
                f"Also try the reverse: move the fleet back from {b} to {a}.",
            ]
        else:
            prop = (f"map/adjacencies.csv gets ONE extra line that connects sea province {a} (Sea of Okhotsk, "
                    f"west of Kamchatka, near the RIGHT map edge) with sea province {b} (Bering Sea just east of "
                    f"the date line, at the LEFT map edge) using {kind}. The two seas do not touch; they face each "
                    "other across the left/right map edge (about 280 pixels apart if the game wraps the map, about "
                    f"5,350 if it does not). The normal sea route is {info.get('route', 14)} sea provinces long, "
                    "around the south of Kamchatka. Everything else is the normal game.")
            steps = [
                "Start a new game (1936) as the Soviet Union. Pause the game (space bar).",
                "Find the Pacific Fleet 'Tikhookeanskiy Flot' at Vladivostok and select it.",
                f"Right-click sea province {a} in the Sea of Okhotsk (the sea west of Kamchatka, north of Sakhalin; "
                "hover shows the number) and unpause until the fleet has arrived there. Pause again.",
                f"With the fleet still selected, right-click sea province {b}: it is in the Bering Sea at the far "
                "LEFT edge of the map, just across the map edge from Kamchatka (scroll east past the right map edge "
                "and it appears; hover shows the number). Look at the route line before unpausing.",
                "Take a screenshot of the route line. One short step across the map edge (over Kamchatka) = YES, "
                "the link is used. A long line south around Kamchatka and back north = NO, the link is ignored.",
                "Unpause and note how many days the fleet needs to arrive (a link used with a wrong, huge length "
                "would show as a very long transit); take a second screenshot.",
                f"Also try the reverse: move the fleet back from {b} to {a}.",
            ]
        return texts.readme(
            build_id, self.title_for(build_id), prop=prop,
            why="Our Equal Earth map needs links between Pacific sea provinces that face each other across the "
                "left/right map edge but do not touch. Vanilla has no such sea-to-sea link. The SEAM pair tests "
                "exactly that case; the UK pair is the control (same line, no map edge involved).",
            launch=texts.LAUNCH_DEBUG, steps=steps, send=common_send,
            expected=self.expected(build_id).text, cannot=["EXP-01"], user_dir=ctx.user, notes=notes)

    def check(self, ctx, build_id, out):
        pair, var = parse_id(build_id)
        probs = check_file_set(out, {ADJ}) + check_descriptor(self, build_id, out)
        p = out / ADJ
        if not p.is_file():
            return probs
        van = ctx.vanilla.text(ADJ).split("\n")
        got = decode(p.read_bytes()).split("\n")
        row = link_row(var, pair)
        if len(got) != len(van) + 1:
            probs.append(f"adjacencies.csv: expected exactly one extra line, got {len(got) - len(van)}")
            return probs
        k = next((i for i, (a, b) in enumerate(zip(van, got)) if a != b), len(van))
        if got[k] != row or got[:k] != van[:k] or got[k + 1:] != van[k:]:
            probs.append("adjacencies.csv: differs from vanilla by more than the one link row")
        if not got[k + 1].startswith("-1;-1;"):
            probs.append("adjacencies.csv: the link row is not directly before the terminator")
        return probs
