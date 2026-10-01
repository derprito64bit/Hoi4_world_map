"""P00e: the engine rules of the staged validator on synthetic fixtures (no game needed).

Every fixture is a TileMap (1024 x 256 px, 32 x 32 px tiles, one province per tile and one region per
province unless grouped). Tile (r, c) covers x 32c..32c+31, y 32r..32r+31 (rows from the top).
"""
import pytest

from staging_helpers import TileMap, run_validator

NEW_ERRORS = ("REGION_CENTRE_DIV0", "SEA_REGION_FRACTIONED", "PROVINCE_CROSSES_SEAM")


def build(tmp_path, m, name="mod"):
    return m.write(tmp_path / name)


# --------------------------------------------------------------------------- the base fixture
def test_base_fixture_has_none_of_the_new_codes(tmp_path):
    rep = run_validator(build(tmp_path, TileMap()))
    for code in NEW_ERRORS + ("REGION_CENTRE_UNKNOWN", "BBOX_ENGINE_RISK", "ADJ_SEAM_LINK", "PROVINCE_TOO_SMALL"):
        assert code not in rep.codes(), code


# --------------------------------------------------------------------------- 1. REGION_CENTRE_DIV0
def test_region_built_to_divide_by_zero(tmp_path):
    """Two tiles in one row, three columns apart: box centres x 48 and 144 -> mean 96, outside both boxes;
    the rect (x 32..160) has its centre at 96 too -> divisor 0 under both models."""
    m = TileMap()
    m.region(m.tile(2, 1), m.tile(2, 4))
    rep = run_validator(build(tmp_path, m))
    assert rep.rc == 1
    (f,) = rep.of("REGION_CENTRE_DIV0", "ERROR")
    assert f["region"] == 1 and f["file"] == "1-R1.txt" and f["n"] == 2
    assert f["dx_grid"] == 0 and f["dx"] == 0 and tuple(f["mean_grid"]) == (96, 176) and tuple(f["mean"]) == (96, 176)
    assert tuple(f["rect_grid"]) == (32, 160, 128, 32)
    assert any(c.startswith("grid model") for c in f["clauses"])
    assert "strategic region 1 (1-R1.txt): the engine's region-centre calculation divides by zero" in f["msg"]


def test_clear_region_does_not_divide(tmp_path):
    """Three tiles: the mean (x 112) lies inside the middle member's box -> no fallback, no division."""
    m = TileMap()
    m.region(m.tile(2, 1), m.tile(2, 3), m.tile(2, 5))
    rep = run_validator(build(tmp_path, m))
    assert "REGION_CENTRE_DIV0" not in rep.codes() and "REGION_CENTRE_UNKNOWN" not in rep.codes()


def test_seam_region_is_unknown_not_error(tmp_path):
    """Tiles at x 0..31 and x 992..1023: the region wraps; its mean misses both boxes -> WARN, not ERROR."""
    m = TileMap()
    m.region(m.tile(4, 0), m.tile(4, 31))
    rep = run_validator(build(tmp_path, m))
    assert "REGION_CENTRE_DIV0" not in rep.codes()
    (f,) = rep.of("REGION_CENTRE_UNKNOWN", "WARN")
    assert f["region"] == 1 and f["signature"] and "wraps the seam" in f["msg"]


def test_seam_region_with_mean_in_a_member_box_is_quiet(tmp_path):
    m = TileMap()
    m.region(m.tile(4, 0), m.tile(4, 16), m.tile(4, 31))     # mean x 517 lies in tile (4, 16)
    rep = run_validator(build(tmp_path, m))
    assert "REGION_CENTRE_UNKNOWN" not in rep.codes() and "REGION_CENTRE_DIV0" not in rep.codes()


def test_seam_region_identical_to_vanilla_is_info(tmp_path):
    """--vanilla: a wrapping region whose member boxes equal a vanilla region's is INFO; a changed one stays WARN."""
    van = TileMap()
    van.region(van.tile(4, 0), van.tile(4, 31))
    vroot = build(tmp_path, van, "vanilla")
    same = TileMap()
    same.region(same.tile(4, 0), same.tile(4, 31))
    same.replace_paths = ["map/strategicregions"]
    rep = run_validator(build(tmp_path, same, "same"), "--vanilla", vroot)
    (f,) = rep.of("REGION_CENTRE_UNKNOWN")
    assert f["level"] == "INFO" and f["vanilla_twin"] == 1
    changed = TileMap()
    changed.region(changed.tile(4, 0), changed.tile(4, 1), changed.tile(4, 31))
    changed.replace_paths = ["map/strategicregions"]
    rep = run_validator(build(tmp_path, changed, "changed"), "--vanilla", vroot)
    (f,) = rep.of("REGION_CENTRE_UNKNOWN")
    assert f["level"] == "WARN" and "vanilla_twin" not in f


# --------------------------------------------------------------------------- 2. SEA_REGION_FRACTIONED
def naval_map():
    m = TileMap()
    m.set_type("sea", *(m.tile(6, c) for c in range(32)))
    m.set_type("lake", m.tile(6, 25))
    return m


def test_fractioned_naval_regions(tmp_path):
    m = naval_map()
    m.region(m.tile(6, 2), m.tile(6, 5))                          # 1: two separate seas
    m.region(m.tile(6, 8), m.tile(6, 10), m.tile(6, 11))          # 2: lowest ID alone, larger piece listed
    m.region(m.tile(6, 18), m.tile(6, 20))                        # 3: joined only by an adjacencies.csv row
    m.adjacency.append((m.tile(6, 18), m.tile(6, 20), "sea", m.tile(5, 19)))
    m.region(m.tile(6, 24), m.tile(6, 25), m.tile(6, 26))         # 4: joined only through a lake
    m.region(m.tile(6, 0), m.tile(6, 31))                         # 5: contiguous across the wrap seam
    m.region(m.tile(6, 14), m.tile(6, 15), m.tile(2, 20))         # 6: a far land member does not count
    rep = run_validator(build(tmp_path, m))
    got = {f["region"]: (f["kept"], f["separated"]) for f in rep.of("SEA_REGION_FRACTIONED", "ERROR")}
    assert got == {1: (m.id(m.tile(6, 2)), [m.id(m.tile(6, 5))]),
                   2: (m.id(m.tile(6, 8)), [m.id(m.tile(6, 10)), m.id(m.tile(6, 11))]),
                   3: (m.id(m.tile(6, 18)), [m.id(m.tile(6, 20))]),
                   4: (m.id(m.tile(6, 24)), [m.id(m.tile(6, 26))])}
    f = rep.of("SEA_REGION_FRACTIONED")[0]
    assert f["msg"].startswith("naval strategic region 1 (1-R1.txt) is fractioned (fatal MAP_ERROR): 1 sea provinces "
                               "are separated from the piece holding its lowest sea province")


def test_contiguous_naval_region_across_the_wrap(tmp_path):
    m = naval_map()
    m.region(m.tile(6, 0), m.tile(6, 31))
    m.region(m.tile(6, 14), m.tile(6, 15), m.tile(2, 20))
    rep = run_validator(build(tmp_path, m))
    assert "SEA_REGION_FRACTIONED" not in rep.codes()


# --------------------------------------------------------------------------- 3. PROVINCE_CROSSES_SEAM
def test_province_crossing_the_seam(tmp_path):
    m = TileMap()
    m.paint(992, 96, 32, 32, pid=m.tile(3, 0))          # tile (3, 31) joins tile (3, 0) across the seam
    rep = run_validator(build(tmp_path, m))
    (f,) = rep.of("PROVINCE_CROSSES_SEAM", "ERROR")
    assert [tuple(s) for s in f["sample"]] == [(m.id(m.tile(3, 0)), "land", 32)]
    assert "pixels in both column 0 and column 1023" in f["msg"]


def test_province_at_both_edges_without_contact_is_flagged(tmp_path):
    """The engine measures the raw box (no wrap), so pixels at both edges mean a full-width box even when the
    two parts do not touch across the seam."""
    m = TileMap()
    m.paint(992, 32, 32, 32, pid=m.tile(3, 0))
    rep = run_validator(build(tmp_path, m))
    (f,) = rep.of("PROVINCE_CROSSES_SEAM", "ERROR")
    assert [tuple(s) for s in f["sample"]] == [(m.id(m.tile(3, 0)), "land", 0)]


def test_provinces_meeting_at_the_seam_are_fine(tmp_path):
    rep = run_validator(build(tmp_path, TileMap()))     # tiles (r, 0) and (r, 31) touch across the seam
    assert "PROVINCE_CROSSES_SEAM" not in rep.codes()


# --------------------------------------------------------------------------- 4. PROVINCE_TOO_SMALL
def test_8_px_is_too_small_9_px_is_not(tmp_path):
    m = TileMap()
    p8 = m.paint(330, 40, 4, 2)
    p9 = m.paint(400, 40, 3, 3)
    root = build(tmp_path, m)
    rep = run_validator(root)
    (f,) = rep.of("PROVINCE_TOO_SMALL", "ERROR")
    assert [tuple(s) for s in f["sample"]] == [(m.id(p8), 8)] and m.id(p9)
    assert "< 9 px" in f["msg"]
    rep = run_validator(root, "--min-pixels", 8)                   # the old floor still works on request
    assert "PROVINCE_TOO_SMALL" not in rep.codes()


# --------------------------------------------------------------------------- 5. BBOX_ENGINE_RISK
@pytest.mark.parametrize("w,h,flagged", [(600, 2, True), (599, 2, False), (2, 174, True), (2, 173, False)])
def test_engine_box_risk(tmp_path, w, h, flagged):
    m = TileMap()
    x0, y0 = (100, 100) if w > h else (800, 40)
    p = m.paint(x0, y0, w, h)
    rep = run_validator(build(tmp_path, m))
    found = rep.of("BBOX_ENGINE_RISK", "WARN")
    if flagged:
        (f,) = found
        assert [tuple(s) for s in f["sample"]] == [(m.id(p), w, h, "land")]
        assert ">= 600 px wide or >= 174 px high" in f["msg"]
    else:
        assert not found
    assert "BBOX_LARGE" in rep.codes()          # the old heuristic is unchanged (default limit W/8 = 128)


# --------------------------------------------------------------------------- 6. ADJ_SEAM_LINK
def test_adjacency_across_the_seam(tmp_path):
    m = TileMap()
    m.adjacency += [(m.tile(3, 0), m.tile(3, 31), "sea", m.tile(2, 0)),     # line 2: x 15.5 / 1007.5 -> WARN
                    (m.tile(4, 31), m.tile(4, 1), "", -1),                  # line 3: x 1007.5 / 47.5 -> WARN
                    (m.tile(3, 1), m.tile(3, 29), "", -1),                  # line 4: 943.5 is outside the band
                    (m.tile(3, 0), m.tile(3, 2), "", -1)]                   # line 5: same side
    rep = run_validator(build(tmp_path, m))
    found = rep.of("ADJ_SEAM_LINK", "WARN")
    assert [f["line"] for f in found] == [2, 3]
    assert "links opposite sides of the wrap seam" in found[0]["msg"] and "(sea)" in found[0]["msg"]
    assert "(empty type)" in found[1]["msg"]


def test_adjacency_without_seam_rows(tmp_path):
    m = TileMap()
    m.adjacency.append((m.tile(3, 1), m.tile(3, 29), "", -1))
    rep = run_validator(build(tmp_path, m))
    assert "ADJ_SEAM_LINK" not in rep.codes()


# --------------------------------------------------------------------------- --no-engine-rules
def test_no_engine_rules_skips_checks_1_to_3(tmp_path):
    m = naval_map()
    m.region(m.tile(2, 1), m.tile(2, 4))
    m.region(m.tile(4, 0), m.tile(4, 31))
    m.region(m.tile(6, 2), m.tile(6, 5))
    m.paint(992, 96, 32, 32, pid=m.tile(3, 0))
    m.paint(100, 140, 600, 2)
    root = build(tmp_path, m)
    on = run_validator(root)
    assert set(NEW_ERRORS) | {"REGION_CENTRE_UNKNOWN", "BBOX_ENGINE_RISK"} <= on.codes()
    off = run_validator(root, "--no-engine-rules")
    assert not (set(NEW_ERRORS) | {"REGION_CENTRE_UNKNOWN"}) & off.codes()
    assert "BBOX_ENGINE_RISK" in off.codes()
