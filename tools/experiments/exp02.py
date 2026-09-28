"""EXP-02: one land and one sea province spread over 300 / 600 / 1,200 px width.

Only ``map/provinces.bmp`` changes. A 1-px-high horizontal strip of pixels is
re-assigned from existing provinces to one host province so that the host's
bounding box becomes exactly the target width. Rules that keep everything else
valid (checked at build and again by ``--check``):

* strip pixels and all their 4-neighbours are of the host's kind (land strip
  only through land, sea strip only through open sea) -> no coastal flag,
  terrain or type changes, definition.csv untouched;
* every province keeps >= 8 px and no province disappears;
* every pair of provinces that touched before still touches (states,
  railways and supply stay valid; the strip only adds contacts with the host);
* no X-crossings;
* no building / unit / weather position lies on a re-assigned pixel, so every
  position still falls in the province it belongs to.
Crossed provinces may end up in two pieces (legal: 488 vanilla provinces are
multi-part).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import texts
from .base import Expected, Experiment, check_descriptor, check_file_set
from .bmpio import read_bmp, write_bmp
from .common import KitError, write_bytes
from .mapdata import LAND, SEA, adjacency_pairs, areas, bboxes, pid_from_rgb, rgb_from_pid, x_crossings, x_crossings_window
from .positions import forbidden_mask

WIDTHS = (300, 600, 1200)
MIN_PX = 8
PROV = "map/provinces.bmp"


def _pair_keys(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a = a.astype(np.int64).ravel(); b = b.astype(np.int64).ravel()
    m = a != b
    lo, hi = np.minimum(a[m], b[m]), np.maximum(a[m], b[m])
    return lo * (1 << 32) + hi


def _window_pair_keys(pid: np.ndarray, r: int, c0: int, c1: int) -> np.ndarray:
    """Pair keys (with multiplicity) of every 4-contact that involves a pixel of row r, cols c0..c1."""
    row = pid[r, c0:c1 + 1]
    keys = [_pair_keys(pid[r, c0 - 1:c1 + 1], pid[r, c0:c1 + 2]),
            _pair_keys(pid[r - 1, c0:c1 + 1], row),
            _pair_keys(row, pid[r + 1, c0:c1 + 1])]
    return np.concatenate(keys)


def global_pair_counts(pid: np.ndarray):
    pw = np.concatenate([pid, pid[:, :1]], axis=1)
    k = np.concatenate([_pair_keys(pw[:, :-1], pw[:, 1:]), _pair_keys(pid[:-1], pid[1:])])
    return np.unique(k, return_counts=True)


def try_strip(pid, types, area, bb, forbidden, counts, kind, target, r, c0):
    """Return (host, c0, c1) if a strip on row r starting at c0 is acceptable, else None."""
    H, W = pid.shape
    host = int(pid[r, c0])
    xmin, xmax = int(bb[0][host]), int(bb[1][host])
    if bb[3][host] - bb[2][host] + 1 >= target or xmax - xmin + 1 >= target:
        return None
    c1 = xmin + target - 1
    if c1 < xmax or c1 + 2 >= W or c0 < 1:
        return None
    seg = slice(c0 - 1, c1 + 2)
    for rr in (r - 1, r, r + 1):
        if (types[pid[rr, seg]] != kind).any():
            return None
    row = pid[r, c0:c1 + 1]
    change = row != host
    if not change.any() or forbidden[r, c0:c1 + 1][change].any():
        return None
    lost = np.bincount(row[change], minlength=len(area))
    if ((area - lost)[lost > 0] < MIN_PX).any():
        return None
    before = _window_pair_keys(pid, r, c0, c1)
    trial = pid[r - 2:r + 3, c0 - 2:c1 + 3].copy()
    trial[2, 2:2 + (c1 - c0 + 1)] = host
    # pairs whose last contacts are all inside the window must survive in the window
    ku, kc = np.unique(before, return_counts=True)
    after = _window_pair_keys(trial, 2, 2, 2 + c1 - c0)
    au = set(np.unique(after).tolist())
    gi = np.searchsorted(counts[0], ku)
    total = counts[1][gi]
    for key, n_in, n_tot in zip(ku.tolist(), kc.tolist(), total.tolist()):
        if n_tot == n_in and key not in au:
            return None
    xs = x_crossings_window(trial, 0, trial.shape[0], 0, trial.shape[1])
    if len(xs[0]):
        return None
    return host, c0, c1


def widen(pid: np.ndarray, types: np.ndarray, forbidden: np.ndarray, kind: int, target: int,
          rows=None, avoid=None, step: int = 5):
    """Re-assign one strip so a province of ``kind`` gets bounding-box width ``target``.

    Returns (new pid, info). Deterministic: rows are tried in the given order,
    start columns left to right in ``step`` increments; the first strip that
    passes every rule wins. ``avoid`` = set of province IDs not to use as host.
    """
    H, W = pid.shape
    n = len(types)
    area = areas(pid, n)
    bb = bboxes(pid, n)
    counts = global_pair_counts(pid)
    avoid = avoid or set()
    rows = range(2, H - 2) if rows is None else rows
    for r in rows:
        ok = np.ones(W, dtype=bool)
        for rr in (r - 1, r, r + 1):
            ok &= types[pid[rr]] == kind
        ok &= ~forbidden[r]
        # runs of ok columns
        d = np.diff(np.r_[0, ok.astype(np.int8), 0])
        starts, ends = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
        for s, e in zip(starts.tolist(), ends.tolist()):
            if e - s < target + 4:
                continue
            for c0 in range(s + 1, e - target - 2, step):
                if int(pid[r, c0]) in avoid:
                    continue
                res = try_strip(pid, types, area, bb, forbidden, counts, kind, target, r, c0)
                if res:
                    host, a, b = res
                    out = pid.copy()
                    seg = out[r, a:b + 1]
                    crossed = sorted(set(seg[seg != host].tolist()))
                    seg[:] = host
                    return out, {"host": host, "row": r, "c0": a, "c1": b, "crossed": crossed,
                                 "width": target, "kind": "land" if kind == LAND else "sea"}
    raise KitError(f"EXP-02: no valid {target}-px strip found for kind {kind}")


def default_rows(H: int, kind: int):
    """Search order: land from the upper-middle band (northern Eurasia first), sea from the middle band."""
    mid = H // 2
    if kind == LAND:
        first = list(range(H // 10, mid))
    else:
        first = list(range(mid, 3 * H // 4))
    rest = [r for r in range(2, H - 2) if r not in set(first)]
    return first + rest


class Exp02(Experiment):
    exp_id = "EXP-02"
    title = "very wide provinces (bounding box)"
    priority = 2

    def build_ids(self, ctx):
        return [f"EXP-02-{w}" for w in WIDTHS]

    def title_for(self, build_id):
        return f"one land + one sea province {build_id.split('-')[-1]} px wide"

    def width(self, build_id):
        return int(build_id.split("-")[-1])

    def expected(self, build_id):
        w = self.width(build_id)
        return Expected(text=f"WARN BBOX_LARGE now lists the two test provinces ({w} px) besides vanilla's 7855 "
                             "(280 px); that is the property under test. Everything else as the vanilla baseline "
                             "(0 ERROR; WARN DEF_SEA_CONTINENT, STATE_NONCONTIGUOUS, RIVERS_ON_SEA, RIVERS_THICK, "
                             "STATE_CATEGORY_DUP).")

    def forbidden(self, v):
        return forbidden_mask(v.shape, [(v.text("map/buildings.txt"), 2, 4), (v.text("map/unitstacks.txt"), 2, 4),
                                        (v.text("map/weatherpositions.txt"), 1, 3)])

    def make(self, v, width):
        pid = np.asarray(v.pid)
        types = v.types
        forb = self.forbidden(v)
        H = pid.shape[0]
        pid1, land = widen(pid, types, forb, LAND, width, rows=default_rows(H, LAND), avoid={7855})
        pid2, sea = widen(pid1, types, forb, SEA, width, rows=default_rows(H, SEA))
        return pid2, land, sea

    def build(self, ctx, build_id, out: Path):
        v = ctx.vanilla
        pid, land, sea = self.make(v, self.width(build_id))
        tmpl = v.provinces_bmp
        write_bytes(out, PROV, write_bmp(tmpl, rgb_from_pid(pid, v.definition.colors()), keep_tail=True))
        return {"land": land, "sea": sea,
                "land_where": v.province_state[land["host"]][1].rsplit(".", 1)[0],
                "sea_where": v.province_region[sea["host"]][1].rsplit(".", 1)[0]}

    def readme(self, ctx, build_id, info):
        w = self.width(build_id)
        L, S = info["land"], info["sea"]
        return texts.readme(
            build_id, self.title_for(build_id),
            prop=f"map/provinces.bmp only: land province {L['host']} and sea province {S['host']} each get a "
                 f"1-pixel-high strip so that each is exactly {w} pixels wide (vanilla's widest are land 280 px "
                 "and sea 179 px). The strip borrows pixels from neighbouring provinces; no province is removed, "
                 "no state, coast, terrain or building position changes.",
            why="The game reports 'TOO LARGE BOX' when one province is spread too widely, but nobody knows the "
                "limit. It decides how big our open-ocean and off-map filler provinces may be (BBOX_MAX). The "
                "three variants (300, 600, 1200 px) bracket the limit.",
            launch=texts.LAUNCH_NORMAL,
            steps=["If the main menu appears: start a new game with any country and let it run for 2-3 days.",
                   f"Optional: look at land province {L['host']} (state file '{info['land_where']}') and sea "
                   f"province {S['host']} (strategic region '{info['sea_where']}'); a thin 1-pixel line running "
                   "east from each across other provinces is expected."],
            send=["Did the game reach the main menu? Did a game start? (yes/no each)",
                  "Loading time (roughly, in seconds).",
                  f"Every error.log line that contains 'BOX', 'box', '{L['host']}' or '{S['host']}' "
                  "(copy them exactly)."],
            expected=self.expected(build_id).text,
            cannot=["EXP-02"], user_dir=ctx.user,
            notes=["Test the three variants (300, 600, 1200) one at a time, smallest first."])

    def check(self, ctx, build_id, out):
        probs = check_file_set(out, {PROV}) + check_descriptor(self, build_id, out)
        p = out / PROV
        if not p.is_file():
            return probs
        v = ctx.vanilla
        width = self.width(build_id)
        van = np.asarray(v.pid)
        try:
            got = pid_from_rgb(read_bmp(p.read_bytes()).pixels, v.definition.colors())
        except KitError as e:
            return probs + [f"provinces.bmp: {e}"]
        types = v.types
        diff = got != van
        hosts = sorted(set(got[diff].tolist()))
        if len(hosts) != 2 or sorted(types[hosts].tolist()) != [LAND, SEA]:
            probs.append(f"changed pixels must belong to exactly one land and one sea host, got {hosts}")
            return probs
        n = len(types)
        bb = bboxes(got, n)
        for h in hosts:
            rows = np.unique(np.nonzero(diff & (got == h))[0])
            if len(rows) != 1:
                probs.append(f"host {h}: strip is not a single row")
            wdt = bb[1][h] - bb[0][h] + 1
            if wdt != width:
                probs.append(f"host {h}: bounding-box width {wdt}, expected {width}")
        if (types[van[diff]] != types[got[diff]]).any():
            probs.append("a strip changed the type (land/sea/lake) of some pixels")
        a = areas(got, n)
        if (a[1:] < MIN_PX).any():
            probs.append(f"provinces below {MIN_PX} px: {np.nonzero(a[1:] < MIN_PX)[0][:10] + 1}")
        if len(x_crossings(got)[0]):
            probs.append("X-crossings present")
        before = {tuple(x) for x in adjacency_pairs(van).tolist()}
        after = {tuple(x) for x in adjacency_pairs(got).tolist()}
        if before - after:
            probs.append(f"{len(before - after)} province contacts were lost, e.g. {sorted(before - after)[:5]}")
        stray = [pair for pair in after - before if not set(pair) & set(hosts)]
        if stray:
            probs.append(f"new contacts that do not involve a host: {stray[:5]}")
        from .mapdata import coastal_flags
        cf, cg = coastal_flags(van, types), coastal_flags(got, types)
        if (cf != cg).any():
            probs.append("coastal flags would change (definition.csv would be stale)")
        if self.forbidden(v)[diff].any():
            probs.append("a building/unit/weather position lies on a re-assigned pixel")
        return probs
