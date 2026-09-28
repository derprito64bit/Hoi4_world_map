"""EXP-07 (low priority, built last): one gap in the state IDs.

The last vanilla state (1081, Otago) becomes state 1083, so ID 1082 is missing.
Consistency edits, all mechanical:
* its history/states file is renamed ``1083 - Otago.txt`` and its ``id`` line changed;
* every script reference to state 1081 (``state = 1081``, ``controls_state = 1081``,
  ``1081 = { ... }`` scopes) in common/, events/ and history/ (except history/states)
  is changed to 1083; any other kind of reference makes the build fail loudly;
* column 1 (state id) of map/buildings.txt: 1081 -> 1083.
``replace_path = "history/states"`` is needed because the file is renamed: without
it the game would still load vanilla's ``1081 - Otago.txt`` next to the new
file (two states owning the same provinces). So all 1,081 state files are copied
(1,080 unchanged). The localisation key STATE_1081 is only a name key and stays.
Province 1081 (in Korea) is a different thing and is not touched.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import texts
from .base import Expected, Experiment, check_descriptor, check_file_set
from .common import KitError, decode, encode, write_bytes
from .positions import join_lines, split_lines

OLD, NEW = 1081, 1083
SCRIPT_DIRS = ("common", "events", "history")
BUILDINGS = "map/buildings.txt"
NUM = re.compile(r"(?<![\w.])%d(?![\w.])")
STATE_REF = re.compile(r"\b(state|controls_state|owns_state|owns_and_controls_state|is_owned_by_state|"
                       r"state_id|capital|target_state|add_state_core|transfer_state|set_state_owner)"
                       r"(\s*=\s*)%d(?![\w.])")
SCOPE = re.compile(r"(?m)^(\s*)%d(\s*=\s*\{)")


def renumber_state_refs(text: str, old: int, new: int) -> tuple:
    """Replace state references old -> new. Returns (text, replaced, leftover) where leftover
    counts standalone occurrences of ``old`` that are not a recognised state reference."""
    num = re.compile(NUM.pattern % old)
    code = re.sub(r"#[^\n]*", lambda m: " " * len(m.group(0)), text)   # ignore comments when counting
    total = len(num.findall(code))
    ref = re.compile(STATE_REF.pattern % old)
    scope = re.compile(SCOPE.pattern % old)
    n_ref = len(ref.findall(code))
    n_scope = len(scope.findall(code))
    text = ref.sub(lambda m: f"{m.group(1)}{m.group(2)}{new}", text)
    text = scope.sub(lambda m: f"{m.group(1)}{new}{m.group(2)}", text)
    return text, n_ref + n_scope, total - n_ref - n_scope


def renumber_state_file(text: str, old: int, new: int) -> str:
    """Change only the top-level ``id = old`` of a state file."""
    m = re.search(r"(\bid\s*=\s*)%d(?![\w.])" % old, text)
    if not m:
        raise KitError(f"state file has no id = {old}")
    return text[:m.start()] + m.group(1) + str(new) + text[m.end():]


def renumber_buildings(text: str, old: int, new: int) -> tuple:
    lines, tr = split_lines(text)
    out, n = [], 0
    for ln in lines:
        s = ln.split(";", 1)
        if s[0] == str(old) and len(s) == 2:
            out.append(f"{new};{s[1]}")
            n += 1
        else:
            out.append(ln)
    return join_lines(out, tr), n


class Exp07(Experiment):
    exp_id = "EXP-07"
    title = "state IDs with one gap (1081 -> 1083)"
    priority = 99

    def build_ids(self, ctx):
        return ["EXP-07"]

    def replace_paths(self, build_id):
        return ["history/states"]

    def expected(self, build_id):
        return Expected(errors={"STATE_IDS"},
                        text="ERROR STATE_IDS (state ids 1..1082 with a gap; max is 1083); that is the property "
                             "under test. Otherwise " + texts.BASELINE_WARNS + ".")

    def state_file(self, v):
        names = [f for f in v.state_files if re.match(r"%d\D" % OLD, f)]
        if len(names) != 1:
            raise KitError(f"expected one state file for {OLD}, found {names}")
        return names[0]

    def script_edits(self, v) -> dict:
        """{game-relative path: new text} for every script file referencing state OLD."""
        out = {}
        pat = re.compile(rb"(?<![\w.])%d(?![\w.])" % OLD)
        for top in SCRIPT_DIRS:
            for p in sorted((v.root / top).rglob("*.txt")):
                rel = p.relative_to(v.root).as_posix()
                if rel.startswith("history/states/"):
                    continue
                with open(p, "rb") as fh:
                    raw = fh.read()
                if not pat.search(raw):
                    continue
                new, n, left = renumber_state_refs(decode(raw), OLD, NEW)
                if left:
                    raise KitError(f"{rel}: {left} reference(s) to {OLD} of an unknown kind; refusing to guess")
                if n:
                    out[rel] = new
        return out

    def build(self, ctx, build_id, out: Path):
        v = ctx.vanilla
        src = self.state_file(v)
        dst = src.replace(str(OLD), str(NEW), 1)
        for f, t in sorted(v.state_files.items()):
            if f == src:
                write_bytes(out, "history/states/" + dst, encode(renumber_state_file(t, OLD, NEW)))
            else:
                write_bytes(out, "history/states/" + f, v.bytes("history/states/" + f))
        edits = self.script_edits(v)
        for rel, t in sorted(edits.items()):
            write_bytes(out, rel, encode(t))
        b, nb = renumber_buildings(v.text(BUILDINGS), OLD, NEW)
        write_bytes(out, BUILDINGS, encode(b))
        return {"state_file": dst, "scripts": sorted(edits), "building_lines": nb}

    def readme(self, ctx, build_id, info):
        return texts.readme(
            build_id, self.title,
            prop=f"State number {OLD} (Otago, New Zealand) is renumbered to {NEW}, so there is no state {OLD + 1} "
                 f"(the state numbers have one gap). Files that mention state {OLD} are updated to {NEW} "
                 f"({', '.join(info['scripts'])} and {info['building_lines']} lines of map/buildings.txt). "
                 "Nothing else changes.",
            why="Tells us whether our state numbering may have gaps (e.g. if a vanilla state has no counterpart "
                "on our map) or must be continuous.",
            launch=texts.LAUNCH_NORMAL,
            steps=["Start a new game (1936) as New Zealand (or any country) and pause.",
                   "Find Otago (the south of New Zealand's South Island) and click it. With -debug the state "
                   f"number is shown; it should be {NEW}. Screenshot the state view.",
                   "Unpause for a few days; open the construction menu and try to queue something in Otago."],
            send=["Did the game load and start? (yes/no)",
                  "Screenshot of the Otago state view; does it behave normally (owner, buildings, construction)?",
                  f"Every error.log line that mentions '{OLD}', '{NEW}', '{OLD + 1}' or 'state'."],
            expected=self.expected(build_id).text, cannot=["EXP-07"], user_dir=ctx.user,
            notes=["Low priority: run this one last, after the others.",
                   "The mod replaces the whole history/states folder (replace_path) because the Otago file is "
                   f"renamed to '{info['state_file']}'; without that the game would also load the original "
                   "'1081 - Otago.txt' and two states would own the same provinces. The other 1,080 state files "
                   "are unchanged copies."])

    def check(self, ctx, build_id, out):
        v = ctx.vanilla
        probs = check_descriptor(self, build_id, out)
        src = self.state_file(v)
        dst = src.replace(str(OLD), str(NEW), 1)
        expected = {"history/states/" + f for f in v.state_files if f != src} | {"history/states/" + dst, BUILDINGS}
        edits = self.script_edits(v)
        expected |= set(edits)
        probs += check_file_set(out, expected)
        for f in v.state_files:
            if f == src:
                continue
            p = out / "history/states" / f
            if p.is_file() and p.read_bytes() != v.bytes("history/states/" + f):
                probs.append(f"state file {f} changed")
        p = out / "history/states" / dst
        if p.is_file():
            got = decode(p.read_bytes())
            if got != renumber_state_file(v.state_files[src], OLD, NEW):
                probs.append(f"{dst}: differs by more than the id line")
        for rel, want in edits.items():
            p = out / rel
            if p.is_file():
                got = decode(p.read_bytes())
                van = v.text(rel)
                # the only differences are OLD -> NEW at state-reference sites
                if got != want or re.sub(r"(?<![\w.])%d(?![\w.])" % NEW, str(OLD), got) != \
                        re.sub(r"(?<![\w.])%d(?![\w.])" % NEW, str(OLD), van):
                    probs.append(f"{rel}: differs by more than state {OLD} -> {NEW}")
        bp = out / BUILDINGS
        if bp.is_file():
            got, _ = split_lines(decode(bp.read_bytes()))
            van, _ = split_lines(v.text(BUILDINGS))
            if len(got) != len(van) or any(
                    g != a and not (a.startswith(f"{OLD};") and g == f"{NEW};" + a.split(";", 1)[1])
                    for g, a in zip(got, van)):
                probs.append("buildings.txt differs by more than the state id column of state 1081")
        return probs
