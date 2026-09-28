"""Province-map primitives."""
import numpy as np
import pytest

from conftest import make_definition
from experiments.common import KitError
from experiments.mapdata import (LAND, SEA, Definition, adjacency_links, adjacency_pairs, append_ids, block_ids,
                                 coast_points, coastal_flags, find_block, fix_x_crossings, game_to_pixel, game_xz,
                                 interior_points, new_colors, pid_from_rgb, rgb_from_pid, x_crossings)
from experiments.tiling import merge_small, tile


def test_definition_roundtrip_and_errors():
    text = "0;0;0;0;land;false;unknown;0\n1;1;2;3;sea;true;ocean;0\n2;4;5;6;land;true;plains;1"
    d = Definition.parse(text)
    assert d.format() == text and d.n == 3 and list(d.types()) == [-1, SEA, LAND]
    assert Definition.parse(text + "\n").format() == text + "\n"
    with pytest.raises(KitError):
        Definition.parse("0;0;0;0;land;false;unknown;0\n2;1;2;3;sea;true;ocean;0")


def test_pid_rgb_roundtrip(tiny_map):
    pid, d = tiny_map
    rgb = rgb_from_pid(pid, d.colors())
    assert np.array_equal(pid_from_rgb(rgb, d.colors()), pid)
    rgb[0, 0] = (250, 251, 252)
    with pytest.raises(KitError):
        pid_from_rgb(rgb, d.colors())


def test_coastal_flags(tiny_map):
    pid, d = tiny_map
    c = coastal_flags(pid, d.types())
    assert c[4] and c[5] and not c[6] and not c[7] and not c[8]      # land touching the sea band
    assert c[1] and c[2] and c[3]


def test_x_crossings_and_fix(tiny_map):
    pid, d = tiny_map
    assert len(x_crossings(pid)[0]) == 0
    p = pid.copy()
    p[20:25, 10:15], p[25:30, 15:20], p[20:25, 15:20] = 9, 10, 11     # 4-way corner 9/11/4/10 inside province 4
    assert len(x_crossings(p)[0]) == 1
    fam = {9: 1, 10: 1, 11: 1}
    before = p.copy()
    assert fix_x_crossings(p, lambda a, b: a != b and fam.get(a) == fam.get(b) == 1) == 1
    assert len(x_crossings(p)[0]) == 0
    changed = np.nonzero(p != before)
    assert set(before[changed].tolist()) <= {9, 10, 11}           # only family pixels moved
    with pytest.raises(KitError):
        q = pid.copy()
        q[20:25, 10:15], q[25:30, 15:20], q[20:25, 15:20] = 9, 10, 11
        fix_x_crossings(q, lambda a, b: False)


def test_x_fix_never_crosses_the_seam():
    pid = np.array([[1, 3, 3, 2], [4, 3, 3, 5]], dtype=np.int32)   # seam block: (0,3),(0,0),(1,3),(1,0) = 2,1,5,4
    assert len(x_crossings(pid)[0]) == 1
    fix_x_crossings(pid, lambda a, b: a != b)
    assert len(x_crossings(pid)[0]) == 0
    assert pid[0, 3] != pid[0, 0] and pid[1, 3] != pid[1, 0]    # nothing handed across the wrap


def test_adjacency_pairs_wrap():
    pid = np.array([[1, 2, 3]], dtype=np.int32)
    assert {tuple(x) for x in adjacency_pairs(pid).tolist()} == {(1, 2), (2, 3), (1, 3)}


def test_adjacency_links():
    text = ("From;To;Type;Through;a;b;c;d;e;f\n5;3;sea;9;-1;-1;-1;-1;;x\n7;8;impassable;-1;-1;-1;-1;-1;;y\n"
            "-1;-1;;-1;-1;-1;-1;-1;-1\n")
    assert adjacency_links(text) == {(3, 5)}


def test_block_editing_keeps_layout_and_skips_comments():
    t = ('state = {\n\tid = 1\n\t# provinces = { 99 }\n\tname = "x { y"\n\thistory = {\n\t\tprovinces = { 7 }\n\t}\n'
         '\tprovinces = {\n\t\t2211 8232 \n\t}\n}\n')
    assert block_ids(t, "provinces") == [2211, 8232]
    out = append_ids(t, "provinces", [13414, 13415])
    assert "\t\t2211 8232 13414 13415 \n\t}" in out
    assert out.replace(" 13414 13415", "") == t
    o, c = find_block(t, "history")
    assert t[o] == "{" and t[c] == "}"


def test_positions_convention():
    x, z = game_xz(10, 20, 100)
    assert (x, z) == (20.5, 89.5)
    assert game_to_pixel(x, z, 100) == (20, 10)


def test_interior_and_coast_points(tiny_map):
    pid, d = tiny_map
    types = d.types()
    ip = interior_points(pid)
    for i, (r, c) in ip.items():
        assert pid[r, c] == i
    cp = coast_points(pid, types, [4, 5], ip)
    for i, (r, c, s) in cp.items():
        assert pid[r, c] == i and types[s] == SEA and pid[r - 1, c] == s


def test_new_colors_unique_and_deterministic():
    existing = np.array([[0, 0, 0], [1, 2, 3]], dtype=np.uint8)
    a = new_colors(existing, 500, 7)
    assert np.array_equal(a, new_colors(existing, 500, 7))
    keys = {tuple(x) for x in a.tolist()}
    assert len(keys) == 500 and (0, 0, 0) not in keys and (1, 2, 3) not in keys


def test_tile_and_merge():
    mask = np.zeros((40, 60), bool)
    mask[5:35, 5:55] = True
    mask[0, 0] = True                     # 1-px island
    lab, n = tile(mask, 16, 10)
    assert (lab[mask] >= 0).all() and (lab[~mask] == -1).all()
    ys, xs = np.nonzero(lab >= 0)
    for k in range(n):
        m = lab == k
        yy, xx = np.nonzero(m)
        assert yy.max() - yy.min() < 10 and xx.max() - xx.min() < 16
    lab2, n2 = merge_small(lab, 20)
    sizes = np.bincount(lab2[lab2 >= 0])
    assert (sizes[sizes > 0] >= 20).sum() >= n2 - 1       # the isolated pixel has no neighbour to merge into
    assert (lab2[mask] >= 0).all()


def test_make_definition_helper():
    d = make_definition(["", "sea", "land"])
    assert d.n == 3 and d.rows[2][4] == "land"
