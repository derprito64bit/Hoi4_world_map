"""EXP-02c: TOO LARGE BOX threshold probes (P00b-f6).

Each build changes ONE province against vanilla 1.19.3: the host takes every pixel of one clean,
filled shape (``boxfill``: a rectangle, or an L of two rectangles), so its bounding box becomes the
shape's box. The boxes are chosen so that the rule families that survive the -debug observations
(``boxrules.candidates``) each predict a different pattern of TOO LARGE BOX lines over the owner's
run (``patterns``): EXP-02b-strip-full first (already built; to be re-run with -debug; its land
host 3172 is the tie-breaker), then the four probes. A test keeps the patterns pairwise distinct,
also exactly over every allowed threshold (``boxrules.outcomes``):

    build (box w x h, w*h, w+h)          C1 w*h   C2 w+h   C3 w or h   C4 longest side
    strip-full 3172 (30,632, 2202)         either   LINE     LINE        LINE
    land-440x150   (66,000, 590)           LINE     none     none        none
    sea-70x440     (30,800, 510)           none     none     LINE        none
    land-150x300   (45,000, 450)           either   none     either      none
    sea-L-330x480  (158,400, 810)          LINE     LINE     LINE        none

(LINE = TOO LARGE BOX under every threshold the family allows, none = no line, either = the line
tells where the threshold lies.) land-440x150 alone names C1, sea-70x440 alone names C3, sea-L alone
names C2, no line on the probes names C4; land-150x300 then narrows C1's area (45,000 in [33,600,
61,200)) or C3's height limit (300 in [173, 400), e.g. H/8 = 256).

ASSUMPTIONS (``boxrules``): one limit for land and sea, one rule (no combination), the box only.
What the run cannot separate is printed in every README (``outcome_meanings``): the C2 row is also
the row of a 32-/64-px tile-count rule; without strip-full it would also be the row of a land-only
area limit in [66,000, 90,000), which strip-full's land host (30,632) rules in (no line) or out
(line). The C4 row also fits "width, or height >= 480, or area >= 158,400".

Why an L: C2 (w+h) and C4 (longest side) differ only on boxes with w+h >= 804 and both sides <= 600.
No clean filled rectangle of that kind exists on the vanilla map (``find_rects`` finds none from
404x400 to 210x594, land or sea: a province always lies wholly inside, which would become an
enclave), so the host fills an L instead: a 38-px band along the southern map edge and a 60-px arm
rising from it. Like the EXP-02 strips (which also triggered the line at 1,200 px), its box is large
and its fill low; every candidate family depends on the box only.

The shapes are aligned to even pixels (rows and columns of every rectangle start and end on the
2-px grid), so the engine box of ``regioncentre.engine_boxes`` equals the pixel box.

Rules (checked at build and again by ``--check``, see ``probe_problems``): only pixels inside the
shape change, all to the host, which fills it completely (no enclave); every donor keeps
>= ``boxfill.REMNANT`` px outside, in one piece per original part (no donor disconnected); no
X-crossing, coastal flag, type or protected province changes; the sea provinces of every naval
strategic region stay one 4-connected piece across the wrap (``boxfill.fractioned_naval``, the
fatal MAP_ERROR of block-400); no strategic region or state becomes non-contiguous; the region-centre
guard has 0 failures; position lines on taken pixels move into their own province (x/y/z only).
definition.csv, states and strategic regions are untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import boxrules, texts
from .base import Expected, Experiment, check_descriptor, check_file_set
from .bmpio import read_bmp, write_bmp
from .boxfill import (FOUR, REMNANT, Rect, as_shape, bounding, corner_crossings, ell, fill, find_ells, find_rects,
                      fractioned_naval, kind_ok, shape_candidate, shape_mask)
from .common import KitError, decode, encode, write_bytes
from .exp02b import (BBOX_BASELINE, POS_FILES, neighbour_counts, noncontiguous_regions, noncontiguous_states,
                     position_problems,
                     protected_ids, rail_gaps, relocate_positions)
from .mapdata import (LAND, SEA, adjacency_links, adjacency_pairs, areas, bboxes, coastal_flags, pid_from_rgb,
                      rgb_from_pid, x_crossings)
from .regioncentre import guard_problems, region_centres

PROV = "map/provinces.bmp"
KIND_NAME = {LAND: "land", SEA: "sea"}
H_MAP = 2048


@dataclass(frozen=True)
class Probe:
    kind: int
    shape: tuple        # tuple of Rects (boxfill.as_shape)
    host: int
    purpose: str

    @property
    def box(self) -> tuple:
        """(x0, x1, y0, y1) inclusive, row 0 = north."""
        return bounding(self.shape)

    @property
    def w(self) -> int:
        return self.box[1] - self.box[0] + 1

    @property
    def h(self) -> int:
        return self.box[3] - self.box[2] + 1

    @property
    def is_rect(self) -> bool:
        return len(self.shape) == 1

    def boxrule_box(self) -> boxrules.Box:
        x0, x1, y0, y1 = self.box
        return boxrules.Box("probe", self.host, KIND_NAME[self.kind], x0, x1, y0, y1, self.pixels)

    @property
    def pixels(self) -> int:
        return sum(r.w * r.h for r in self.shape)


def _rect(r0, c0, h, w):
    return as_shape(Rect(r0, c0, h, w))


# Found on vanilla 1.19.3 with ``find_site`` (the first shape, in the search order of ``find_rects`` /
# ``find_ells`` on even pixels, that passes every rule); the build fails loudly if one no longer fits.
# Run order = dict order.
PROBES = {
    "EXP-02c-land-440x150": Probe(LAND, _rect(0, 4852, 150, 440), 4006,
                                  "box area only: w*h 66,000 is above the flagged 61,200, while w+h 590 is below "
                                  "the clean 656 and both sides are below the clean 600 x 173"),
    "EXP-02c-sea-70x440": Probe(SEA, _rect(100, 2304, 440, 70), 47,
                                "height only: 440 is above the flagged 400, while w*h 30,800 and w+h 510 are "
                                "below every clean value and the width is 70"),
    "EXP-02c-land-150x300": Probe(LAND, _rect(0, 4396, 300, 150), 9224,
                                  "a threshold inside the open intervals: w*h 45,000 (area rule) and height 300 "
                                  "(height rule), with w+h 450 and the longest side 300 clean under the others"),
    "EXP-02c-sea-L-330x480": Probe(SEA, ell(H_MAP, 862, 60, 480, 330, 38, True), 639,
                                   "width + height: w+h 810 is above the flagged 800, while the longest side 480 "
                                   "is below the clean 600"),
}


# ------------------------------------------------------------------ whole-map rules and the site search
def whole_map_problems(v, van: np.ndarray, got: np.ndarray, observed=None) -> list:
    """Naval-region contiguity, region / state contiguity and the region-centre guard on a finished map."""
    probs = []
    types = v.types
    fr0 = fractioned_naval(van, v.province_region, types)
    fr1 = fractioned_naval(got, v.province_region, types)
    if fr1 - fr0:
        probs.append(f"naval strategic regions whose sea provinces are no longer one piece (fatal MAP_ERROR "
                     f"'Naval strategic region ... is fractioned'): {sorted(fr1 - fr0)[:10]}")
    links = adjacency_links(v.text("map/adjacencies.csv"))
    rc0 = noncontiguous_regions(van, v.province_region, links)
    rc1 = noncontiguous_regions(got, v.province_region, links)
    if rc1 != rc0:
        probs.append(f"strategic-region contiguity changed: now split {sorted(rc1 - rc0)[:10]}, "
                     f"now joined {sorted(rc0 - rc1)[:10]}")
    nc0 = noncontiguous_states(van, types, v.province_state, links)
    nc1 = noncontiguous_states(got, types, v.province_state, links)
    if nc1 != nc0:
        probs.append(f"state contiguity changed: now split {sorted(nc1 - nc0)[:10]}, now joined "
                     f"{sorted(nc0 - nc1)[:10]}")
    regions = {}
    for p, (rid, _) in v.province_region.items():
        regions.setdefault(rid, []).append(p)
    if observed is None:
        observed = region_centres(van, regions)
    probs += guard_problems(region_centres(got, regions), observed, clear_ids=[])
    return probs


def find_site(v, kind: int, w: int, h: int, *, ell_arm: tuple | None = None, limit: int = 40, **kw):
    """First (shape, host) that passes every rule: a w x h rectangle (``find_rects``), or with
    ``ell_arm`` = (arm width, band height) a bottom-edge L with box w x h (``find_ells``)."""
    van = np.asarray(v.pid)
    prot = protected_ids(v)
    if ell_arm is None:
        cands = find_rects(van, v.types, kind, h, w, prot, limit=limit, avoid={BBOX_BASELINE}, **kw)
    else:
        cands = find_ells(van, v.types, kind, ell_arm[0], h, w, ell_arm[1], prot, limit=limit,
                          avoid={BBOX_BASELINE}, **kw)
    for shape, got in cands:
        if not whole_map_problems(v, van, fill(van, shape, got["host"])):
            return as_shape(shape), got["host"]
    return None


# ------------------------------------------------------------------ rules on a finished map
def donor_problems(van: np.ndarray, got: np.ndarray, donors) -> list:
    """Each donor keeps >= REMNANT px, and each of its original 4-connected parts keeps pixels in one piece."""
    from scipy import ndimage
    n = int(max(van.max(), got.max())) + 1
    bb = bboxes(van, n)
    a = areas(got, n)
    probs = []
    for d in sorted(donors):
        if a[d] < REMNANT:
            probs.append(f"donor {d} keeps {int(a[d])} px, below the {REMNANT}-px remnant")
            continue
        x0, x1, y0, y1 = int(bb[0][d]), int(bb[1][d]), int(bb[2][d]), int(bb[3][d])
        before = van[y0:y1 + 1, x0:x1 + 1] == d
        after = got[y0:y1 + 1, x0:x1 + 1] == d
        if int(a[d]) != int(after.sum()):
            probs.append(f"donor {d} gained pixels outside its vanilla box")
            continue
        lab0, n0 = ndimage.label(before, structure=FOUR)
        _, n1 = ndimage.label(after, structure=FOUR)
        kept = len(np.unique(lab0[after]))
        if n1 != n0 or kept != n0:
            probs.append(f"donor {d} is disconnected: {n0} part(s) in vanilla, {n1} now ({kept} of them kept)")
    return probs


def probe_problems(v, van: np.ndarray, got: np.ndarray, probe: Probe, observed=None) -> list:
    """Every rule of one probe build on the finished province map (positions: ``position_problems``)."""
    probs = []
    types = v.types
    n = len(types)
    host = probe.host
    if not kind_ok(types[van], probe.kind, probe.shape):
        probs.append(f"shape {probe.shape} or its ring holds another kind than {KIND_NAME[probe.kind]}, or touches "
                     "the wrap seam")
    if types[host] != probe.kind:
        probs.append(f"host {host} is not {KIND_NAME[probe.kind]}")
    inside = shape_mask(probe.shape, van.shape)
    diff = got != van
    if (diff & ~inside).any():
        bad = sorted(set(van[diff & ~inside].tolist()))
        probs.append(f"pixels changed outside the shape: provinces {bad[:10]}")
    if not (got[inside] == host).all():
        probs.append(f"the shape is not filled by host {host}: {int((got[inside] != host).sum())} px of other "
                     "provinces (enclaves or remnants)")
    bb = bboxes(got, n)
    box = (int(bb[0][host]), int(bb[1][host]), int(bb[2][host]), int(bb[3][host]))
    if box != probe.box:
        probs.append(f"host {host}: bounding box {box}, expected {probe.box}")
    a_van = areas(van, n)
    if int((van[inside] == host).sum()) != int(a_van[host]):
        probs.append(f"host {host} was not wholly inside the shape in vanilla")
    donors = sorted(set(van[diff].tolist()) - {host})
    prot = protected_ids(v)
    if set(donors) & prot:
        probs.append(f"protected provinces lost pixels: {sorted(set(donors) & prot)[:10]}")
    if set(got[diff].tolist()) - {host}:
        probs.append(f"changed pixels went to provinces other than host {host}")
    if (types[van[diff]] != types[got[diff]]).any():
        probs.append("a re-assignment changed the type (land/sea/lake) of some pixels")
    probs += donor_problems(van, got, donors)
    if len(x_crossings(got)[0]):
        probs.append("X-crossings present")
    if (coastal_flags(van, types) != coastal_flags(got, types)).any():
        probs.append("coastal flags would change (definition.csv would be stale)")
    before = {tuple(x) for x in adjacency_pairs(van).tolist()}
    after = {tuple(x) for x in adjacency_pairs(got).tolist()}
    lost = [p for p in before - after if not set(p) & set(donors)]
    if lost:
        probs.append(f"contacts lost between provinces that are not donors: {sorted(lost)[:5]}")
    stray = [p for p in after - before if host not in p]
    if stray:
        probs.append(f"new contacts that do not involve the host: {sorted(stray)[:5]}")
    gaps = rail_gaps(v.text("map/railways.txt"), after | adjacency_links(v.text("map/adjacencies.csv")))
    if gaps:
        probs.append(f"railway steps no longer adjacent: {gaps[:5]}")
    probs += whole_map_problems(v, van, got, observed)
    return probs


def foreign_lines(v, van: np.ndarray, got: np.ndarray) -> dict:
    """{rel: [(line number, own province)]}: position lines on re-assigned pixels that already sat outside their
    own province in vanilla (vanilla quirks); EXP-02c leaves them unchanged (``keep_foreign``)."""
    from .exp02b import _pos, is_foreign
    from .positions import split_lines
    H, W = van.shape
    diff = got != van
    out = {}
    for rel, cols in sorted(POS_FILES.items()):
        lines, _ = split_lines(v.text(rel))
        for i, ln in enumerate(lines):
            px = _pos(ln, cols, H, W)
            if px is not None and diff[px] and is_foreign(rel, ln, van, px):
                out.setdefault(rel, []).append((i + 1, int(ln.split(";")[0])))
    return out


def centre_pixel(probe: Probe) -> tuple:
    """(row, col) of the box centre (integer halves rounded down)."""
    x0, x1, y0, y1 = probe.box
    return (y0 + y1) // 2, (x0 + x1) // 2


# ------------------------------------------------------------------ outcome patterns
WORD = {"F": "LINE", "c": "none", "?": "either"}


TIEBREAK_ID = "EXP-02b-strip-full"      # run first, with -debug; its land host 3172 decides area vs the rest


def run_boxes(probes=None) -> dict:
    """{build id: Box} in owner run order: the strip-full tie-breaker (land host 3172), then the probes."""
    probes = PROBES if probes is None else probes
    return {TIEBREAK_ID: boxrules.TIEBREAK, **{b: p.boxrule_box() for b, p in probes.items()}}


def patterns(probes=None, cands=None) -> dict:
    """{family id: (text, {build id: 'F' | 'c' | '?'})} over strip-full and the probe builds (run order)."""
    boxes = run_boxes(probes)
    cands = boxrules.candidates() if cands is None else cands
    return {cid: (text, {b: fn(bx) for b, bx in boxes.items()}) for cid, text, fn in cands}


def outcome_meanings(probes=None) -> list:
    """[(outcome, [family ids])] for every outcome some family allows (exact, ``boxrules.outcomes``), sorted by
    the first main family that allows it."""
    boxes = list(run_boxes(probes).values())
    sets = {f: boxrules.outcomes(f, boxes) for f in boxrules.FAMILIES}
    every = sorted(set().union(*sets.values()))
    rows = [(o, [f for f in boxrules.FAMILIES if o in sets[f]]) for o in every]
    order = list(boxrules.FAMILIES)
    return sorted(rows, key=lambda r: (order.index(r[1][0]), r[0]))


def distinct(pats: dict) -> list:
    """Pairs of families whose patterns some outcome cannot tell apart ('?' matches both answers)."""
    out = []
    ids = sorted(pats)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            pa, pb = pats[a][1], pats[b][1]
            if all(pa[k] == pb[k] or "?" in (pa[k], pb[k]) for k in pa):
                out.append((a, b))
    return out


# ------------------------------------------------------------------ experiment
LAUNCH = ("Add the launch option -debug (Steam -> Hearts of Iron IV -> Properties -> Launch options), then start "
          "the game from the launcher (Play). -debug is REQUIRED for this test: without it the game writes no "
          "map-check lines (TOO LARGE BOX) to error.log. Remove -debug after the test.")
RUN_NOTE = ("Run order: FIRST EXP-02b-strip-full once more, now with -debug (it is already built and loaded fine "
            "before; its land province 3172 is the tie-breaker between an area rule and the others), THEN the four "
            "EXP-02c builds one at a time, in any order (each changes a different single province). The answer is "
            "the pattern over all five, so report every build, also when it shows no line.")
ASSUME = ("The reading assumes ONE limit for land and sea, ONE rule (not a combination of two), and that only the "
          "box counts (not how full it is).")
CANNOT = [
    "the exact threshold: the four boxes tell the rule families apart; inside the winning family they narrow the "
    "threshold to an interval, not to one number",
    "the width threshold of the either-side (C3) and longest-side (C4) families stays between 600 and 1,200 px",
    "one large province is not a map of them: whether many large provinces together affect loading, pathing or "
    "performance is not tested",
    "only these four shapes: a rule that no candidate family describes may still fit; a pattern that matches no "
    "row of the table is itself the answer to report",
    "heights above 480 px and box areas above 158,400 px are not tested by a clean box: if no build shows a line, "
    "a rule 'width, or height >= 480, or area >= 158,400' fits as well as 'longest side only'",
    "the table assumes one limit for land and sea; separate limits are only partly covered (the 'C1k' lines)",
]


class Exp02c(Experiment):
    exp_id = "EXP-02c"
    title = "TOO LARGE BOX threshold probes"
    priority = 2

    def build_ids(self, ctx):
        return list(PROBES)

    def title_for(self, build_id):
        p = PROBES[build_id]
        what = "filled" if p.is_rect else "filled L-shape, box"
        return f"one {KIND_NAME[p.kind]} province {what} {p.w}x{p.h} px"

    def expected(self, build_id):
        p = PROBES[build_id]
        return Expected(text=f"WARN BBOX_LARGE lists the {KIND_NAME[p.kind]} test province {p.host} "
                             f"({max(p.w, p.h)} px) besides vanilla's 7855 (280 px); that is the property under "
                             "test. Everything else as the vanilla baseline (0 ERROR; WARN DEF_SEA_CONTINENT, "
                             "STATE_NONCONTIGUOUS, RIVERS_ON_SEA, RIVERS_THICK, STATE_CATEGORY_DUP).")

    def make(self, v, probe: Probe) -> np.ndarray:
        van = np.asarray(v.pid)
        n = len(v.types)
        got = shape_candidate(van, v.types, areas(van, n), bboxes(van, n), probe.kind, probe.shape,
                              protected_ids(v), avoid={BBOX_BASELINE})
        if got is None or got["host"] != probe.host:
            raise KitError(f"EXP-02c: shape {probe.shape} is no longer a clean site for host {probe.host} "
                           "(re-run exp02c.find_site)")
        out = fill(van, probe.shape, probe.host)
        if corner_crossings(out, probe.shape):
            raise KitError(f"EXP-02c: shape {probe.shape} makes an X-crossing at a corner")
        return out

    def build(self, ctx, build_id, out: Path):
        v = ctx.vanilla
        probe = PROBES[build_id]
        van = np.asarray(v.pid)
        pid = self.make(v, probe)
        probs = probe_problems(v, van, pid, probe)
        if probs:
            raise KitError(f"EXP-02c {build_id} breaks its own rules: " + "; ".join(probs[:5]))
        write_bytes(out, PROV, write_bmp(v.provinces_bmp, rgb_from_pid(pid, v.definition.colors()), keep_tail=True))
        files, moved = relocate_positions(v, van, pid, keep_foreign=True)
        for rel, text in sorted(files.items()):
            write_bytes(out, rel, encode(text))
        donors = sorted(set(van[pid != van].tolist()) - {probe.host})
        kept = foreign_lines(v, van, pid)
        where = v.province_state[probe.host][1] if probe.kind == LAND else v.province_region[probe.host][1]
        nb_van, nb_got = neighbour_counts(van, len(v.types)), neighbour_counts(pid, len(v.types))
        return {"kind": KIND_NAME[probe.kind], "host": probe.host, "shape": [list(r) for r in probe.shape],
                "box": list(probe.box), "donors": donors, "moved": dict(sorted(moved.items())),
                "neighbours": int(nb_got[probe.host]), "neighbours_before": int(nb_van[probe.host]),
                "vanilla_max_neighbours": int(nb_van[1:].max()), "kept_foreign": kept,
                "box_centre_inside": bool(shape_mask(probe.shape, van.shape)[centre_pixel(probe)]),
                "where": where.rsplit(".", 1)[0], "pixels_before": int(areas(van, len(v.types))[probe.host]),
                "predictions": {cid: pat[build_id] for cid, (_, pat) in patterns().items()}}

    # -------------------------------------------------------------- README
    def outcome_table(self) -> list:
        boxes = run_boxes()
        short = {b: (b.split("EXP-02c-", 1)[1] if b in PROBES else "strip-full") for b in boxes}
        lines = ["How to read the five results (LINE = 'Province <host> has TOO LARGE BOX' appears for the test "
                 "province, for strip-full: for land province 3172; none = it does not; either = this build only "
                 "narrows the threshold). " + ASSUME]
        for cid, (text, pat) in patterns().items():
            cells = []
            for b in boxes:
                cell = f"{short[b]} {WORD[pat[b]]}"
                if pat[b] == "?":
                    cell += f" (a line means {boxrules.narrows(cid, boxes[b])})"
                cells.append(cell)
            lines.append(f"{cid}: " + ", ".join(cells) + f" -> {text}")
        lines.append("Every pattern the rules allow, and which rules give it (C1k = an area limit of its own for land "
                     "and for sea; G32 / G64 = more than K 32-px / 64-px map tiles touched, a coarse area rule):")
        for o, fams in outcome_meanings():
            pat = ", ".join(f"{short[b]} {'LINE' if f else 'none'}" for b, f in zip(boxes, o))
            lines.append(f"  {pat} -> {' or '.join(fams)}")
        lines.append("Note: the C2 pattern (strip-full LINE, and of the four only sea-L-330x480) is also given by a "
                     "G32 / G64 tile rule, so it does not prove 'width + height'; for BBOX_MAX read it as 'w+h and "
                     "area both matter' and keep both limits. Without strip-full, 'only sea-L-330x480' would also fit "
                     "a land-only area limit between 66,000 and 90,000 (C1k); strip-full tells them apart: no line "
                     "there means an area-type rule (C1k or G64), a line means C2 (or G32 / G64).")
        lines.append("Any other pattern (for example lines for both land-440x150 and sea-70x440) matches none of "
                     "these rules: report it as it is.")
        return lines

    def readme(self, ctx, build_id, info):
        p = PROBES[build_id]
        e = info
        moved = ", ".join(f"{k.split('/')[-1]} {n}" for k, n in e["moved"].items()) or "none"
        x0, x1, y0, y1 = p.box
        kind = KIND_NAME[p.kind]
        if p.is_rect:
            shape = (f"a solid, filled rectangle of {p.w} x {p.h} pixels (rows {y0}-{y1} from the top, columns "
                     f"{x0}-{x1})")
        else:
            band, arm = sorted(p.shape, key=lambda r: -r.r0)
            shape = (f"a solid, filled L: a band {band.w} x {band.h} pixels along the bottom map edge (columns "
                     f"{band.c0}-{band.c0 + band.w - 1}) and an arm {arm.w} pixels wide rising from it to row {y0}; "
                     f"its bounding box is {p.w} x {p.h} pixels (rows {y0}-{y1}, columns {x0}-{x1}). An L, not a "
                     "rectangle, because no clean filled rectangle with this box exists on the map (some province "
                     "would be left inside it as an enclave)")
        prop = (f"map/provinces.bmp: {kind} province {p.host} becomes {shape}. Before, it had "
                f"{e['pixels_before']} pixels, all inside that shape. It takes the rest of the shape from "
                f"{len(e['donors'])} neighbouring {kind} provinces; each of them also reaches outside the shape and "
                f"keeps that outside part in one piece (at least {REMNANT} pixels). Nothing is left inside the "
                "shape: no enclaves, no remnants. No province is removed; no state, strategic region, coast, "
                "terrain or definition changes; the sea provinces of every naval strategic region stay in one "
                f"piece. Position lines that stood on taken pixels moved into their own province ({moved}). The "
                f"host now touches {e['neighbours']} provinces (before: {e['neighbours_before']}; the most-connected "
                f"province of the normal game touches {e['vanilla_max_neighbours']}).")
        why = ("With -debug the game logs 'Province N has TOO LARGE BOX' for EXP-02-1200 (1-px strips 1,200 px "
               "wide) and for the 400 x 400 squares of EXP-02b-block-400, but not for EXP-02-600 (600 px strips) "
               "or any vanilla province. Several rules fit that: box area, width + height, a separate width and "
               "height limit, or only the longest side if block-400's line came from its enclaves. This build is "
               f"one of four that tell them apart; it tests {p.purpose}. The answer decides BBOX_MAX (today land "
               "250 / sea 180 px).")
        steps = ["The check runs while the map loads, so the line (if any) is in error.log once the main menu "
                 "appears. Start a new game with any country and let it run for 1-2 days, then quit.",
                 f"Optional: hover {kind} province {p.host} ('{e['where']}'); it should be one straight-edged "
                 + ("rectangle." if p.is_rect else "L.")]
        send = ["Did the game reach the main menu? Did a game start? (yes/no each)",
                f"Every error.log line that contains 'TOO LARGE BOX', 'fractioned', 'MAP_ERROR' or '{p.host}' "
                "(copy them exactly), or 'no such line'."]
        extra = []
        if not e["box_centre_inside"]:
            r, c = centre_pixel(p)
            extra.append(f"The centre of this province's box (row {r}, column {c}) lies OUTSIDE the province, in the "
                         "empty corner of the L; the four other builds do not have that. A line about the centre or "
                         "about stack positions of this province may come from it; it is not the box answer. Only "
                         "'TOO LARGE BOX' is.")
        if e["neighbours"] > e["vanilla_max_neighbours"]:
            extra.append(f"The host touches {e['neighbours']} provinces, more than any in the normal game "
                         f"({e['vanilla_max_neighbours']}). There is precedent: EXP-02-1200's sea host 8337 touched "
                         "27 and logged only TOO LARGE BOX and stack lines with -debug, and the strip-full hosts "
                         "touched 77 and 114 and loaded.")
        kept = e["kept_foreign"]
        if kept:
            n = sum(len(x) for x in kept.values())
            provs = sorted({q for x in kept.values() for _, q in x})
            outsiders = not (set(provs) & (set(e["donors"]) | {p.host}))
            extra.append(f"{n} unit-stack lines of province{'s' if len(provs) > 1 else ''} "
                         f"{', '.join(map(str, provs))}{' (neither host nor donor)' if outsiders else ''} already "
                         "stood inside this shape in the normal game, outside their own province (a quirk of the "
                         "normal game). They were left unchanged.")
        notes = [RUN_NOTE] + self.outcome_table() + extra + [
            "A 'too far away from center' line for this province (unit or ship stacks) came with TOO LARGE BOX "
            "in EXP-02-1200; copy it too, it does not change the reading. The same line for the donor provinces is "
            "expected as well (their stacks were moved into what is left of them): an artefact, not the answer.",
            "If the game does not load, that is not the size rule (TOO LARGE BOX is a warning): send the whole "
            "error log. The kit checked the known fatal cause (a naval strategic region cut in pieces)."]
        return texts.readme(build_id, self.title_for(build_id), prop=prop, why=why, launch=LAUNCH, steps=steps,
                            send=send, expected=self.expected(build_id).text, cannot=[], cannot_extra=CANNOT,
                            user_dir=ctx.user, notes=notes)

    # -------------------------------------------------------------- check
    def check(self, ctx, build_id, out):
        v = ctx.vanilla
        probe = PROBES[build_id]
        van = np.asarray(v.pid)
        present = {rel for rel in POS_FILES if (out / rel).is_file()}
        probs = check_file_set(out, {PROV} | present)
        probs += check_descriptor(self, build_id, out)
        p = out / PROV
        if not p.is_file():
            return probs
        try:
            got = pid_from_rgb(read_bmp(p.read_bytes()).pixels, v.definition.colors())
        except KitError as e:
            return probs + [f"provinces.bmp: {e}"]
        probs += probe_problems(v, van, got, probe)
        for rel in sorted(POS_FILES):
            text = decode((out / rel).read_bytes()) if rel in present else None
            if text is not None and text == v.text(rel):
                probs.append(f"{rel} is present but identical to vanilla")
            probs += position_problems(v, van, got, rel, text, keep_foreign=True)[:5]
        return probs
