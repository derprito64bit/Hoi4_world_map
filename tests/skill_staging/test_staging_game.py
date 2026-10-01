"""P00e: the staged validator on vanilla 1.19.3 and on the P00b experiment builds whose in-game outcome is known.

Skipped without HOI4_GAME_DIR. The build checks also need the experiment builds (read-only):
$P00E_EXPERIMENTS_DIR, else <repo>/build/experiments, else C:/dev/Hoi4_world_map/build/experiments.
Each run takes ~20 s, so the runs are started together (3 at a time) and cached for the session.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from staging_helpers import run_validator

# CHK-014 (2026-09-28): vanilla 1.19.3, --bbox-limit 250 --bbox-limit-sea 180
CHK014_WARN = {"DEF_SEA_CONTINENT", "BBOX_LARGE", "STATE_NONCONTIGUOUS", "RIVERS_ON_SEA", "RIVERS_THICK",
               "STATE_CATEGORY_DUP"}
VANILLA_WRAPPING = {88, 95, 96, 97, 178, 180}
BBOX = ("--bbox-limit", 250, "--bbox-limit-sea", 180)
BUILDS = ("EXP-03-24k", "EXP-03-24k-fix", "EXP-03-div0c", "EXP-03-div0", "EXP-02b-block-400", "EXP-08-5632x2560",
          "EXP-03-20k", "EXP-01-SEAM-A")


def experiments_dir():
    here = Path(__file__).resolve().parents[2]
    for p in (os.environ.get("P00E_EXPERIMENTS_DIR"), here / "build" / "experiments",
              "C:/dev/Hoi4_world_map/build/experiments"):
        if p and Path(p).is_dir() and any(Path(p).glob("EXP-*")):
            return Path(p)
    return None


@pytest.fixture(scope="session")
def runs(game, tmp_path_factory):
    """{name: Report} for vanilla and every present build (each layered over the game)."""
    out = tmp_path_factory.mktemp("p00e_game")
    exp = experiments_dir()
    jobs = {"vanilla": (game, ())}
    if exp is not None:
        for b in BUILDS:
            if (exp / b).is_dir():
                jobs[b] = (exp / b, ("--vanilla", game))

    def one(item):
        name, (root, extra) = item
        # the JSON report goes to tmp, never into the game or the build folders
        rep = run_validator(root, *extra, *BBOX, report=out / f"{name}.json")
        return name, rep
    with ThreadPoolExecutor(max_workers=3) as ex:
        return dict(ex.map(one, sorted(jobs.items())))


def build(runs, name):
    if name not in runs:
        pytest.skip(f"{name} not built (experiments dir: {experiments_dir()})")
    return runs[name]


def test_vanilla_has_no_error_and_the_baseline_warnings(runs):
    rep = runs["vanilla"]
    assert rep.rc == 0 and not rep.codes("ERROR"), [i["msg"] for i in rep if i["level"] == "ERROR"]
    assert rep.codes("WARN") == CHK014_WARN | {"REGION_CENTRE_UNKNOWN"}
    assert rep.regions("REGION_CENTRE_UNKNOWN", "WARN") == VANILLA_WRAPPING
    assert len(rep.of("STATE_CATEGORY_DUP")) == 4
    for code in ("PROVINCE_CROSSES_SEAM", "SEA_REGION_FRACTIONED", "BBOX_ENGINE_RISK", "ADJ_SEAM_LINK",
                 "PROVINCE_TOO_SMALL"):
        assert code not in rep.codes(), code


def test_24k_region_191_divides_by_zero(runs):
    rep = build(runs, "EXP-03-24k")
    assert rep.regions("REGION_CENTRE_DIV0", "ERROR") == {191}
    (f,) = rep.of("REGION_CENTRE_DIV0")
    # the crash dump's numbers (both dumps): mean (3141, 1961), rect (2990, 1854, 302, 170), divisor 0
    assert tuple(f["mean_grid"]) == (3141, 1961) and tuple(f["rect_grid"]) == (2990, 1854, 302, 170)
    assert f["dx_grid"] == 0 and f["file"].startswith("191")


def test_24k_fix_is_clear(runs):
    assert "REGION_CENTRE_DIV0" not in build(runs, "EXP-03-24k-fix").codes()


def test_div0c_region_193_divides_by_zero(runs):
    rep = build(runs, "EXP-03-div0c")
    assert rep.regions("REGION_CENTRE_DIV0", "ERROR") == {193}
    (f,) = rep.of("REGION_CENTRE_DIV0")
    assert [c.split(":")[0] for c in f["clauses"]] == ["grid model"]       # only the grid model predicted it


def test_div0_stays_flagged_conservatively(runs):
    """EXP-03-div0 loaded in game, but the older pixel-box model flags region 193: the guard is the union."""
    rep = build(runs, "EXP-03-div0")
    assert rep.regions("REGION_CENTRE_DIV0", "ERROR") == {193}
    (f,) = rep.of("REGION_CENTRE_DIV0")
    assert all(c.startswith("pixel-box model") for c in f["clauses"]) and f["dx_grid"] == 1


def test_block_400_fractioned_naval_regions(runs):
    rep = build(runs, "EXP-02b-block-400")
    assert rep.regions("SEA_REGION_FRACTIONED", "ERROR") == {115, 176}
    # the province lists the engine printed with -debug (P00b section 17 / registry.KNOWN_FRACTIONED)
    assert {f["region"]: f["separated"] for f in rep.of("SEA_REGION_FRACTIONED")} == {
        115: [2378, 2404, 2452, 2503, 2551, 2627, 2650, 2676, 2701, 2779],
        176: [263, 460, 644, 2144, 2252, 2278, 2305, 8583, 9029, 9086]}


def test_5632x2560_province_crosses_the_seam(runs):
    rep = build(runs, "EXP-08-5632x2560")
    (f,) = rep.of("PROVINCE_CROSSES_SEAM", "ERROR")
    assert [s[0] for s in f["sample"]] == [13511]


def test_20k_has_the_three_tiny_provinces(runs):
    rep = build(runs, "EXP-03-20k")
    (f,) = rep.of("PROVINCE_TOO_SMALL", "ERROR")
    assert sorted(s[0] for s in f["sample"]) == [19998, 19999, 20000]
    assert sorted(s[1] for s in f["sample"]) == [6, 7, 8]


def test_seam_a_link_is_flagged(runs):
    rep = build(runs, "EXP-01-SEAM-A")
    (f,) = rep.of("ADJ_SEAM_LINK")
    assert f["level"] == "WARN" and "2560 -> 3836 (sea)" in f["msg"]
