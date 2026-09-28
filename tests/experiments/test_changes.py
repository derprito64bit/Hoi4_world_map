"""Each experiment's change function alters only its target (synthetic fixtures, no game needed)."""
import numpy as np
import pytest
from scipy import ndimage

from conftest import make_definition
from experiments.common import KitError
from experiments.mapdata import LAND, SEA, adjacency_pairs, areas, bboxes, coastal_flags, x_crossings

FOUR = [[0, 1, 0], [1, 1, 1], [0, 1, 0]]


def strip_world(H=40, W=400, sea_rows=13):
    """Sea band on top (40-px provinces), land below (20-px provinces, the first wraps the seam); no X-crossings."""
    pid = np.zeros((H, W), dtype=np.int32)
    types = [""]
    for k, c in enumerate(range(-35, W, 40)):
        pid[:sea_rows, max(0, c):min(W, c + 40)] = len(types)
        types.append("sea")
    first_land = len(types)
    pid[sea_rows:, :] = first_land
    types.append("land")
    for c in range(10, W - 10, 20):
        pid[sea_rows:, c:c + 20] = len(types)
        types.append("land")
    return pid, make_definition(types)


def test_strip_world_is_clean():
    pid, d = strip_world()
    assert len(x_crossings(pid)[0]) == 0


# ---------------------------------------------------------------- EXP-01
def test_exp01_inserts_exactly_one_row_before_terminator():
    from experiments.exp01 import insert_before_terminator, link_row
    text = "From;To;Type;Through;a;b;c;d;e;Comment\n1;2;sea;3;-1;-1;-1;-1;;x\n-1;-1;;-1;-1;-1;-1;-1;-1 \n#c\n\n\n"
    out = insert_before_terminator(text, link_row("B"))
    a, b = text.split("\n"), out.split("\n")
    assert len(b) == len(a) + 1 and b[2] == link_row("B") and b[:2] == a[:2] and b[3:] == a[2:]
    assert link_row("A").split(";")[2:4] == ["sea", "8314"] and link_row("B").split(";")[2:4] == ["", "-1"]
    with pytest.raises(KitError):
        insert_before_terminator(text.replace("-1;-1;;", "x;"), "r")
    with pytest.raises(KitError):
        insert_before_terminator(text + "-1;-1;;-1;-1;-1;-1;-1;-1\n", "r")


def test_exp01_route_length():
    from experiments.exp01 import sea_route_length
    pid = np.array([[1, 2, 3, 4, 5, 9]], dtype=np.int32)
    types = np.array([-1, SEA, SEA, SEA, SEA, SEA, 0, 0, 0, LAND])
    assert sea_route_length(adjacency_pairs(pid), types, 1, 5) == 4


# ---------------------------------------------------------------- EXP-02
@pytest.mark.parametrize("kind,target", [(LAND, 150), (SEA, 150), (LAND, 300)])
def test_exp02_widen_changes_one_row_only(kind, target):
    from experiments.exp02 import widen
    pid, d = strip_world()
    types = d.types()
    forb = np.zeros(pid.shape, bool)
    forb[20, 100] = forb[5, 120] = True
    out, info = widen(pid, types, forb, kind, target, step=1)
    diff = out != pid
    rows = np.unique(np.nonzero(diff)[0])
    assert len(rows) == 1 and rows[0] == info["row"]
    assert set(out[diff].tolist()) == {info["host"]} and types[info["host"]] == kind
    assert (types[pid[diff]] == kind).all()
    bb = bboxes(out, d.n)
    assert bb[1][info["host"]] - bb[0][info["host"]] + 1 == target
    assert not forb[diff].any()
    assert {tuple(x) for x in adjacency_pairs(pid).tolist()} <= {tuple(x) for x in adjacency_pairs(out).tolist()}
    assert (areas(out, d.n)[1:] >= 8).all() and len(x_crossings(out)[0]) == 0
    assert np.array_equal(coastal_flags(out, types), coastal_flags(pid, types))


def test_exp02_widen_fails_loudly_when_impossible():
    from experiments.exp02 import widen
    pid, d = strip_world(W=200)
    with pytest.raises(KitError):
        widen(pid, d.types(), np.zeros(pid.shape, bool), LAND, 1000)


# ---------------------------------------------------------------- EXP-03 / EXP-04
def big_world():
    H, W = 160, 240
    pid = np.full((H, W), 1, dtype=np.int32)          # sea everywhere
    pid[20:140, 20:120] = 2                             # coastal land
    pid[20:140, 120:220] = 3                            # coastal land
    pid[40:80, 140:180] = 4                             # inland provinces
    pid[40:80, 40:80] = 5
    pid[90:130, 60:100] = 6
    return pid, make_definition(["", "sea", "land", "land", "land", "land", "land"])


def test_exp03_subdivide_refines_exactly():
    from experiments.exp03 import subdivide
    pid, d = big_world()
    types = d.types()
    n0 = d.n
    out, root = subdivide(pid, types, 12, np.arange(n0), {}, {2, 3}, min_px=40)
    assert len(root) == n0 + 12
    assert (root[:n0] == np.arange(n0)).all()
    assert np.array_equal(root[out], pid)                                  # every piece inside its parent
    assert (out[pid == 1] == 1).all()                                        # sea untouched
    for i in range(1, len(root)):
        assert ndimage.label(out == i, structure=FOUR)[1] == 1              # connected
    assert (areas(out, len(root))[1:] >= 40).all() and len(x_crossings(out)[0]) == 0
    t2 = np.array([types[r] for r in root])
    t2[0] = -1
    c = coastal_flags(out, t2)
    assert c[2] and c[3]                                                   # parents kept a coastal piece


def test_exp03_carve_small_exact_sizes():
    from experiments.exp03 import carve_small, subdivide
    pid, d = big_world()
    out, root = subdivide(pid, d.types(), 4, np.arange(d.n), {}, {2, 3}, min_px=40)
    hosts = set(range(d.n, len(root)))
    out2, root2, smalls = carve_small(out, root, d.types(), (6, 7, 8), hosts | {2, 3, 4, 5, 6})
    a = areas(out2, len(root2))
    assert [a[i] for i, _, _, _ in smalls] == [6, 7, 8]
    assert [i for i, *_ in smalls] == [len(root), len(root) + 1, len(root) + 2]
    changed = out2 != out
    assert set(out2[changed].tolist()) == {i for i, *_ in smalls}
    assert len(x_crossings(out2)[0]) == 0


def test_exp03_railways_reconnected_through_family():
    from experiments.exp03 import update_railways
    root = np.array([0, 1, 2, 3, 2])          # province 4 is a piece of 2
    pairs = {(1, 4), (2, 4), (2, 3)}           # 1 no longer touches 2 directly
    text = "2 3 1 2 3 \n1 2 2 3 \n"
    out, n = update_railways(text, pairs, root)
    assert out == "2 4 1 4 2 3 \n1 2 2 3 \n" and n == 1
    with pytest.raises(KitError):
        update_railways("1 2 1 3 \n", pairs, root)


# ---------------------------------------------------------------- EXP-05
def test_exp05_resize_nearest():
    from experiments.exp05 import resize_nearest
    a = np.array([[1, 2, 3, 4], [5, 6, 7, 8]], dtype=np.uint8)
    assert np.array_equal(resize_nearest(a, 8, 2), np.repeat(a, 2, axis=1))
    b = resize_nearest(a, 3, 2)
    assert b.shape == (2, 3) and set(b.ravel()) <= set(a.ravel())
    assert np.array_equal(resize_nearest(a, 4, 2), a)


# ---------------------------------------------------------------- EXP-06
def test_exp06_convert_only_targets():
    from experiments.exp06 import convert_to_lakes, drop_stacks
    d = make_definition(["", "sea", "sea", "land"])
    out = convert_to_lakes(d, [2])
    assert out.rows[2][4:] == ["lake", "false", "lakes", "0"]
    assert out.rows[:2] == d.rows[:2] and out.rows[3] == d.rows[3]
    with pytest.raises(KitError):
        convert_to_lakes(d, [3])
    stacks = "1;0;1;2;3;0;0\n2;0;1;2;3;0;0\n21;0;1;2;3;0;0\n"
    assert drop_stacks(stacks, [2]) == "1;0;1;2;3;0;0\n21;0;1;2;3;0;0\n"


# ---------------------------------------------------------------- EXP-07
def test_exp07_renumber_state_refs():
    from experiments.exp07 import renumber_buildings, renumber_state_file, renumber_state_refs
    t = ("a = {\n\tstate = 1081\n\tcontrols_state = 1081 # Otago\n\t1081 = { add_core_of = ROOT }\n"
         "\tstate = 10811\n\tvalue = 1081.5\n}\n")
    out, n, left = renumber_state_refs(t, 1081, 1083)
    assert n == 3 and left == 0
    assert out == t.replace("state = 1081\n", "state = 1083\n").replace("controls_state = 1081", "controls_state = 1083") \
        .replace("\t1081 = {", "\t1083 = {")
    _, n2, left2 = renumber_state_refs("location = 1081\n", 1081, 1083)
    assert n2 == 0 and left2 == 1                          # unknown kind is reported, not guessed
    st = "state = {\n\tid = 1081\n\tprovinces = { 1081 }\n}\n"
    assert renumber_state_file(st, 1081, 1083) == "state = {\n\tid = 1083\n\tprovinces = { 1081 }\n}\n"
    b, k = renumber_buildings("1081;arms;1;2;3;0;0\n10810;x;1;2;3;0;0\n5;naval;1;2;3;0;1081\n", 1081, 1083)
    assert k == 1 and b == "1083;arms;1;2;3;0;0\n10810;x;1;2;3;0;0\n5;naval;1;2;3;0;1081\n"


# ---------------------------------------------------------------- EXP-08
def test_exp08_pad_array_and_provinces(tiny_map):
    from experiments.exp08 import pad_array, pad_provinces
    a = np.arange(6, dtype=np.uint8).reshape(2, 3)
    p = pad_array(a, 2, 1, 9)
    assert p.shape == (4, 4) and np.array_equal(p[2:, :3], a) and (p[:2] == 9).all() and (p[:, 3] == 9).all()
    pid, d = tiny_map
    out, k = pad_provinces(pid, d.types(), 32, 16, d.n)
    assert out.shape == (96, 112)
    assert np.array_equal(out[32:, :96], pid)
    pad = np.ones(out.shape, bool)
    pad[32:, :96] = False
    assert (out[pad] >= d.n).all() or ((out[pad] < d.n).sum() <= 4)
    assert len(x_crossings(out)[0]) == 0 and k >= 1


def test_exp08_pad_dds_keeps_vanilla_blocks():
    from experiments.dds import Dds, dxt5_encode, read_dds
    from experiments.exp08 import pad_dds
    from test_formats import _dds_header
    img = np.random.default_rng(3).integers(0, 256, (8, 16, 4), dtype=np.uint8)
    l0 = dxt5_encode(img)
    t = Dds(_dds_header(16, 8, 1, True), 16, 8, b"DXT5", [l0])
    out = read_dds(pad_dds(t, 4, 4, (1, 2, 3, 255)))
    assert (out.width, out.height) == (20, 12)
    arr = np.frombuffer(out.levels[0], np.uint8).reshape(3, 5, 16)
    assert arr[1:, :4].tobytes() == l0


# ---------------------------------------------------------------- EXP-09 synthetic layout
def small_layout():
    from experiments.common import ee_project
    from experiments.synth import Params, layout
    cv = ee_project().Canvas(512, 256, 10.9, -60.0, 90.0)
    globe = cv.globe_mask()
    units = [(1, [1, 2, 3]), (2, [4, 5]), (3, [6, 7, 8, 9])]
    col, row = cv.to_pixel(-60.0, -50.0)
    anchors = [(4, [10, 11], int(row), int(col), "center")]
    seas = [12, 13, 14, 15]
    p = Params(bar_w=2, bar_h=4, gap=2, line_w=12, sea_cell=16, off_cell=20, min_sea=8, min_off=8)
    return globe, layout(globe, units, anchors, seas, 16, p)


def test_exp09_layout_filler_and_bars():
    globe, lay = small_layout()
    pid = lay.pid
    off = np.isin(pid, lay.off_ids)
    mism = np.nonzero(off == globe)
    assert len(mism[0]) <= 4 and (mism[1] == pid.shape[1] - 1).all()     # only the seam-tip exceptions
    for i in range(1, 12):
        m = pid == i
        assert m.sum() == 8 and ndimage.label(m, structure=FOUR)[1] == 1  # every land/lake bar 2x4
    for i in (12, 13, 14, 15):
        assert (pid == i).any()                                            # vanilla sea IDs used
    assert len(x_crossings(pid)[0]) == 0
    a = np.bincount(pid.ravel())
    assert (a[1:][a[1:] > 0] >= 8).all() and set(np.unique(pid).tolist()) == set(range(1, int(pid.max()) + 1))


def test_exp09_layout_rejects_oversized_state():
    from experiments.synth import Params, layout
    globe = np.ones((64, 128), bool)
    with pytest.raises(KitError):
        layout(globe, [(1, list(range(1, 40)))], [], [], 40, Params(bar_w=4, bar_h=4, line_w=20))


# ---------------------------------------------------------------- r2 additions
def test_exp01_build_ids_and_rows():
    from experiments.exp01 import PAIRS, Exp01, link_row, parse_id
    assert Exp01().build_ids(None) == ["EXP-01-UK-A", "EXP-01-UK-B", "EXP-01-SEAM-A", "EXP-01-SEAM-B"]
    assert parse_id("EXP-01-SEAM-B") == ("SEAM", "B")
    a, b = PAIRS["SEAM"]
    assert link_row("A", "SEAM").split(";")[:4] == [str(a), str(b), "sea", str(b)]
    assert link_row("B", "SEAM").split(";")[:4] == [str(a), str(b), "", "-1"]
    with pytest.raises(KitError):
        parse_id("EXP-01A")


REGION = """strategic_region={
\tid=1
\tprovinces={
\t\t1 2 3
\t}
\tnaval_terrain=water_deep_ocean
\tweather={
%s\t}
}
"""


def region_with(tmin, arctic, snow=0.0, months=12):
    per = ""
    for m in range(months):
        per += ("\t\tperiod={\n\t\t\tbetween={ 0.%d 27.%d }\n\t\t\ttemperature={ %.1f 5.0 }\n\t\t\tno_phenomenon=0.5\n"
                "\t\t\tsnow=%.3f\n\t\t\tarctic_water=%.3f\n\t\t}\n") % (m, m, tmin, snow, arctic)
    return REGION % per


def test_weather_parse_and_icy():
    from experiments.weather import parse_periods, winter_icy
    p = parse_periods(region_with(-20.0, 1.0))
    assert len(p) == 12 and p[11]["start_month"] == 11 and p[0]["tmin"] == -20.0 and p[0]["arctic_water"] == 1.0
    assert winter_icy(region_with(-20.0, 1.0)) and winter_icy(region_with(-5.0, 0.0, snow=0.2))
    assert not winter_icy(region_with(5.0, 1.0)) and not winter_icy(region_with(-5.0, 0.0))
    assert not winter_icy("strategic_region={ id=1 provinces={ 1 } }")


def test_weather_both_and_snow_donor():
    from experiments.exp08 import weather_block
    from experiments.weather import parse_periods, winter_icy, with_snow_of
    sea = weather_block(region_with(-20.0, 1.0))                 # arctic water, no snow
    land = region_with(-30.0, 0.0, snow=0.6)                     # snow, no arctic water
    assert winter_icy(sea) and not winter_icy(sea, both=True)
    merged = with_snow_of(sea, land)
    p = parse_periods(merged)
    assert len(p) == 12 and all(x["snow"] == 0.6 and x["arctic_water"] == 1.0 and x["tmin"] == -20.0 for x in p)
    assert winter_icy(merged, both=True)
    assert merged.replace("snow=0.600", "snow=0.000") == sea     # only the snow weights changed
    with pytest.raises(ValueError):
        with_snow_of(sea, region_with(-30.0, 0.0, snow=0.6, months=1))


def test_exp09_shot6_helpers():
    from experiments.exp09 import not_icy, shot6_water
    pid = np.array([[1, 1, 2, 2], [1, 3, 3, 2], [4, 4, 4, 4]], dtype=np.int32)
    types = np.array([-1, SEA, SEA, LAND, SEA])
    assert shot6_water(pid, types, [(0, 0)], radius=1) == [1]
    assert shot6_water(pid, types, [(1, 2)], radius=1) == [1, 2, 4]
    icy, warm = region_with(-20.0, 1.0), region_with(5.0, 0.0)
    assert not_icy([1, 2, 4], lambda i: icy if i != 4 else warm) == [4]
    # filler lakes need snow AND arctic water: arctic-only weather passes for sea 1 but not for lake 2
    assert not_icy([1, 2], lambda i: icy, lakes={2}) == [2]
    both = region_with(-20.0, 1.0, snow=0.5)
    assert not_icy([1, 2], lambda i: both, lakes={2}) == []


def test_exp06_drop_naval_terrain():
    from experiments.exp06 import drop_naval_terrain
    t = region_with(1.0, 0.0, months=1)
    out = drop_naval_terrain(t)
    assert "naval_terrain" not in out and out == t.replace("\tnaval_terrain=water_deep_ocean\n", "")
    with pytest.raises(KitError):
        drop_naval_terrain(out)


def test_exp03_frozen_provinces_are_never_split():
    from experiments.exp03 import subdivide
    pid, d = big_world()
    out, root = subdivide(pid, d.types(), 6, np.arange(d.n), {}, {2, 3}, min_px=40, frozen={2, 5})
    for i in (2, 5):
        assert np.array_equal(out == i, pid == i)
    assert len(root) == d.n + 6


def test_exp09_layout_north_tiles_get_new_ids():
    from experiments.common import ee_project
    from experiments.synth import Params, layout
    cv = ee_project().Canvas(512, 256, 10.9, -60.0, 90.0)
    globe = cv.globe_mask()
    north_row = int(cv.to_pixel(10.9, 50.0)[1])
    p = Params(bar_w=2, bar_h=4, gap=2, line_w=12, sea_cell=16, off_cell=20, min_sea=8, min_off=8)
    lay = layout(globe, [(1, [1, 2, 3])], [], [4, 5, 6], 7, p, north_row=north_row)
    assert lay.sea_north and lay.sea_new[:len(lay.sea_north)] == lay.sea_north
    ys, xs = np.nonzero(np.isin(lay.pid, lay.sea_north))
    assert ys.mean() < north_row
    for i in (4, 5, 6):                                         # vanilla sea IDs sit south of the northern band
        assert np.nonzero(lay.pid == i)[0].mean() >= north_row - 16
