"""P00b-f6: TOO LARGE BOX candidate rules and the EXP-02c probe design (no game needed)."""
import dataclasses

import numpy as np
import pytest

from experiments import boxrules
from experiments.boxrules import OBSERVED, candidates, rejected, single, two_axis


def test_single_metric_rules_the_observations_reject():
    names = {n for n, _, _ in rejected()}
    # pure width / longest side: block-400 (400) flagged, EXP-02-600 (600) clean; diagonal 565.7 vs 602.6;
    # pixel count: the 4,060-px 1200 strip flagged, vanilla's 15,697-px 4006 clean
    assert {"w", "max(w,h)", "diagonal", "pixels", "w*h/pixels", "engine w", "engine max side",
            "128-px tiles", "256-px tiles"} <= names
    assert not {"w*h", "w+h", "engine w*h", "engine w+h"} & names


def test_surviving_families_and_their_intervals():
    ids = [c[0] for c in candidates()]
    assert ids == ["C1", "C2", "C3", "C4"]
    a, s = single("w*h", OBSERVED), single("w+h", OBSERVED)
    assert (a.lo, a.hi) == (33600, 61200)            # EXP-02-600 sea 600x56 clean, EXP-02-1200 sea 1200x51 flagged
    assert (s.lo, s.hi) == (656, 800)                # 600x56 clean, 400x400 flagged
    assert (single("engine w*h", OBSERVED).lo, single("engine w*h", OBSERVED).hi) == (34800, 62504)
    t = two_axis(OBSERVED)
    assert t.consistent and t.tw == (600, 1200) and t.th == (173, 400)
    c4 = single("max(w,h)", OBSERVED, drop_confounded=True)
    assert c4.consistent and (c4.lo, c4.hi) == (600, 1200)


def test_c4_exists_only_because_block400_is_confounded():
    plain = tuple(dataclasses.replace(b, confounded=False) for b in OBSERVED)
    assert [c[0] for c in candidates(plain)] == ["C1", "C2", "C3"]


def test_engine_boxes_match_the_region_centre_model():
    from experiments.regioncentre import engine_boxes
    for b in OBSERVED:
        H = boxrules.H_VANILLA
        bx, by, bw, bh = engine_boxes([b.x0], [b.x1], [H - 1 - b.y1], [H - 1 - b.y0])
        assert b.engine() == (int(bx[0]), int(by[0]), int(bw[0]), int(bh[0]))
    b8337 = next(b for b in OBSERVED if b.pid == 8337)
    assert b8337.engine() == (86, 554, 1202, 52)


def test_predictions_are_firm_only_outside_the_interval():
    f = single("w*h", OBSERVED)
    assert boxrules.predict_single(f, 61200) == "F" and boxrules.predict_single(f, 33600) == "c"
    assert boxrules.predict_single(f, 45000) == "?"
    t = two_axis(OBSERVED)
    assert boxrules.predict_two_axis(t, 70, 440) == "F" and boxrules.predict_two_axis(t, 600, 173) == "c"
    assert boxrules.predict_two_axis(t, 150, 300) == "?" and boxrules.predict_two_axis(t, 840, 38) == "?"


def test_pixel_and_engine_predictions_must_agree():
    c1 = candidates()[0][2]
    odd = boxrules.probe_box(501, 123, 1, 1)         # pixel w*h 61,623 > 61,200, engine 502 x 124 = 62,248 < 62,504
    assert c1(odd) == "?"
    even = boxrules.probe_box(520, 122, 0, 2)
    assert even.engine()[2:] == (520, 122) and c1(even) == "F"


def test_narrows_names_the_threshold_a_line_would_bound():
    b = boxrules.probe_box(150, 300, 0, 4396)
    assert boxrules.narrows("C1", b) == "A < 45000" and boxrules.narrows("C3", b) == "Th < 300"
    assert boxrules.narrows("C3", boxrules.probe_box(840, 38, 0, 2)) == "Tw < 840"
    with pytest.raises(KeyError):
        boxrules.narrows("C9", b)


def test_grid_families_are_listed_for_the_record():
    names = [f.name for f in boxrules.grid_families()]
    assert names == ["32-px tiles", "64-px tiles"]


# ---------------------------------------------------------------- the EXP-02c probe design
def test_probe_patterns_tell_every_family_apart():
    from experiments.exp02c import distinct, patterns
    pats = patterns()
    assert distinct(pats) == []
    assert {k: v[1] for k, v in pats.items()} == {
        "C1": {"EXP-02c-land-440x150": "F", "EXP-02c-sea-70x440": "c", "EXP-02c-land-150x300": "?",
               "EXP-02c-sea-L-330x480": "F"},
        "C2": {"EXP-02c-land-440x150": "c", "EXP-02c-sea-70x440": "c", "EXP-02c-land-150x300": "c",
               "EXP-02c-sea-L-330x480": "F"},
        "C3": {"EXP-02c-land-440x150": "c", "EXP-02c-sea-70x440": "F", "EXP-02c-land-150x300": "?",
               "EXP-02c-sea-L-330x480": "F"},
        "C4": {"EXP-02c-land-440x150": "c", "EXP-02c-sea-70x440": "c", "EXP-02c-land-150x300": "c",
               "EXP-02c-sea-L-330x480": "c"}}


def test_distinct_reports_families_one_outcome_cannot_separate():
    from experiments.exp02c import distinct
    pats = {"A": ("a", {"x": "F", "y": "c"}), "B": ("b", {"x": "?", "y": "c"}), "C": ("c", {"x": "c", "y": "F"})}
    assert distinct(pats) == [("A", "B")]


def test_docstring_table_matches_the_patterns():
    from experiments import exp02c
    word = exp02c.WORD
    rows = {ln.split()[0]: ln.split()[-4:] for ln in exp02c.__doc__.splitlines()
            if ln.strip().startswith(("land-", "sea-"))}
    pats = exp02c.patterns()
    for bid in exp02c.PROBES:
        short = bid.split("EXP-02c-", 1)[1]
        assert rows[short] == [word[pats[c][1][bid]] for c in ("C1", "C2", "C3", "C4")], short


def test_probes_sit_on_the_engine_grid_and_have_the_named_boxes():
    from experiments.exp02c import PROBES
    for bid, p in PROBES.items():
        b = p.boxrule_box()
        assert b.engine()[2:] == (p.w, p.h), bid                 # 2-px grid box == pixel box
        for r in p.shape:
            assert r.r0 % 2 == 0 and r.c0 % 2 == 0 and r.h % 2 == 0 and r.w % 2 == 0, bid
        assert bid.endswith(f"{p.w}x{p.h}")
    L = PROBES["EXP-02c-sea-L-330x480"]
    assert len(L.shape) == 2 and L.w + L.h >= 804 and max(L.w, L.h) <= 600     # C2 line, C4 clean


def test_probe_build_ids_are_installable():
    from experiments.exp02c import PROBES
    from experiments.install import mod_file_name
    for bid in PROBES:
        assert mod_file_name(bid) == f"p00b_{bid}.mod"


def test_observed_hosts_are_distinct_and_hold_their_boxes():
    keys = [(b.label, b.pid) for b in OBSERVED]
    assert len(keys) == len(set(keys))
    for b in OBSERVED:
        assert b.w * b.h >= b.pixels > 0 and b.flagged in (True, False, None)
        assert not b.confounded or b.flagged is True
    assert np.all([b.flagged is None for b in OBSERVED if b.label in ("EXP-02-300", "EXP-02b-strip-full")])


def test_diag02_find_build_takes_the_first_root_that_has_the_build(tmp_path):
    from experiments.diag02 import find_build
    a, b = tmp_path / "a", tmp_path / "b"
    (b / "EXP-02-600").mkdir(parents=True)
    (a / "EXP-02c-sea-70x440").mkdir(parents=True)
    (b / "EXP-02c-sea-70x440").mkdir(parents=True)
    assert find_build([a, b], "EXP-02-600") == b / "EXP-02-600"
    assert find_build([a, b], "EXP-02c-sea-70x440") == a / "EXP-02c-sea-70x440"
    assert find_build([a, b], "EXP-02-1200") is None
