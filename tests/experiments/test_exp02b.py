"""EXP-02b: filled blocks and full-width strips (synthetic maps, no game needed)."""
import numpy as np
import pytest

from conftest import make_definition
from experiments.common import KitError
from experiments.mapdata import LAND, SEA, adjacency_pairs, areas, bboxes, coastal_flags, x_crossings

FOUR = [[0, 1, 0], [1, 1, 1], [0, 1, 0]]


def grid_world(H=120, W=160, cell=10, sea_cols=30):
    """Sea on the left (sea_cols wide, 10x10 sea provinces), land grid on the right (10x10 provinces).

    The grid is staggered by half a cell every other row band so no four provinces meet at a corner.
    """
    pid = np.zeros((H, W), dtype=np.int32)
    types = [""]
    for kind, c_lo, c_hi, shift in (("sea", 0, sea_cols, cell // 2), ("land", sea_cols, W, 0)):
        # sea bands are shifted half a cell down so band borders never meet at the sea/land edge
        for band, r in enumerate(range(-shift, H, cell)):
            off = (cell // 2) * (band % 2)
            c = c_lo
            first = True
            while c < c_hi:
                w = cell - off if first and off else cell
                first = False
                w = min(w, c_hi - c)
                pid[max(0, r):r + cell, c:c + w] = len(types)
                types.append(kind)
                c += w
    return pid, make_definition(types)


def test_grid_world_is_clean():
    pid, d = grid_world()
    assert len(x_crossings(pid)[0]) == 0 and (areas(pid, d.n)[1:] >= 8).all()


def _square_host(pid, types, kind, r0, c0, n):
    area = areas(pid, len(types))
    sub = pid[r0:r0 + n, c0:c0 + n]
    ids, cnt = np.unique(sub, return_counts=True)
    return max(int(i) for i, c in zip(ids, cnt) if c == area[i] and types[i] == kind)


@pytest.mark.parametrize("r0,c0,n", [(20, 60, 43), (5, 45, 70), (33, 81, 37)])
def test_make_block_fills_the_square_and_keeps_everyone(r0, c0, n):
    from experiments.exp02b import REMNANT, block_donors, make_block
    pid, d = grid_world()
    types = d.types()
    host = _square_host(pid, types, LAND, r0, c0, n)
    protected = {int(pid[r0 + n // 2, c0 + n // 2])} - {host}
    out, info = make_block(pid, types, LAND, host, r0, c0, n, protected)
    n_ids = d.n
    bb = bboxes(out, n_ids)
    assert (bb[0][host], bb[1][host], bb[2][host], bb[3][host]) == (c0, c0 + n - 1, r0, r0 + n - 1)
    diff = out != pid
    donors = block_donors(pid, types, LAND, host, r0, c0, n, protected)
    assert info["donors"] == donors
    assert set(out[diff].tolist()) == {host}
    assert set(pid[diff].tolist()) <= set(donors)
    assert not diff[:r0].any() and not diff[r0 + n:].any() and not diff[:, :c0].any() and not diff[:, c0 + n:].any()
    for p in protected:
        assert np.array_equal(out == p, pid == p)                     # protected stay whole
    a = areas(out, n_ids)
    assert (a[1:] >= 8).all() and (a[1:] > 0).all()                    # nobody disappears
    assert all(a[p] >= REMNANT for p in donors)
    assert len(x_crossings(out)[0]) == 0
    assert np.array_equal(coastal_flags(out, types), coastal_flags(pid, types))
    assert info["fill"] > 0.8


def test_make_block_sea():
    from experiments.exp02b import make_block
    pid, d = grid_world(sea_cols=90)
    types = d.types()
    host = _square_host(pid, types, SEA, 20, 20, 50)
    out, info = make_block(pid, types, SEA, host, 20, 20, 50, set())
    assert np.array_equal(coastal_flags(out, types), coastal_flags(pid, types))
    assert (out[20:70, 20:70] == host).mean() == info["fill"] > 0.9


def test_make_block_refuses_bad_squares():
    from experiments.exp02b import make_block
    pid, d = grid_world()
    types = d.types()
    host = _square_host(pid, types, LAND, 20, 60, 40)
    with pytest.raises(KitError):                                       # ring touches the sea
        make_block(pid, types, LAND, _square_host(pid, types, LAND, 20, 30, 40), 20, 30, 40, set())
    with pytest.raises(KitError):                                       # host not wholly inside
        make_block(pid, types, LAND, host, 20 + 40, 60, 40, set())
    with pytest.raises(KitError):                                       # wrong kind
        make_block(pid, types, SEA, host, 20, 60, 40, set())


def test_make_block_is_deterministic():
    from experiments.exp02b import make_block
    pid, d = grid_world()
    types = d.types()
    host = _square_host(pid, types, LAND, 20, 60, 43)
    a = make_block(pid, types, LAND, host, 20, 60, 43, set())
    b = make_block(pid, types, LAND, host, 20, 60, 43, set())
    assert np.array_equal(a[0], b[0]) and a[1] == b[1]


def test_fix_block_crossings_only_flips_between_host_and_donor():
    from experiments.exp02b import fix_block_crossings
    orig = np.ones((10, 10), dtype=np.int32)          # T-junction of 1 (top), 2 (bottom left), 3 (bottom right)
    orig[5:, :5] = 2
    orig[5:, 5:] = 3
    out = orig.copy()
    out[4, 5] = 9                         # host pixel creates a 4-ID corner {1, 9, 2, 3}
    dm = np.zeros(10, dtype=bool)
    dm[[1, 2, 3]] = True
    before = len(x_crossings(out)[0])
    flips = fix_block_crossings(out, orig, 9, dm, 2, 2, 6)
    assert before and flips and len(x_crossings(out)[0]) == 0
    ch = out != orig
    assert set(out[ch].tolist()) <= {9}


def test_noncontiguous_states_and_rail_gaps():
    from experiments.exp02b import noncontiguous_states, rail_gaps
    pid = np.array([[1, 1, 2, 3, 3, 2]], dtype=np.int32)   # no wrap contact 3|1
    types = np.array([-1, LAND, LAND, LAND])
    ps = {1: (10, "a"), 3: (10, "a"), 2: (20, "b")}
    assert noncontiguous_states(pid, types, ps, set()) == {10}
    assert noncontiguous_states(pid, types, ps, {(1, 3)}) == set()
    pairs = {tuple(x) for x in adjacency_pairs(np.concatenate([pid, pid[:, :1] * 0 + 3], 1)).tolist()}
    assert rail_gaps("1 3 1 2 3\n", pairs) == []
    assert rail_gaps("1 2 1 3\n", {(1, 2)}) == [(1, 1, 3)]


def test_noncontiguous_regions_and_neighbour_counts():
    from experiments.exp02b import neighbour_counts, noncontiguous_regions
    pid = np.array([[1, 1, 2, 3, 3, 2]], dtype=np.int32)
    pr = {1: (5, "r"), 3: (5, "r"), 2: (6, "s")}
    assert noncontiguous_regions(pid, pr, set()) == {5}
    assert noncontiguous_regions(pid, pr, {(1, 3)}) == set()
    assert neighbour_counts(pid, 4).tolist() == [0, 1, 2, 1]


class FakeV:
    """Just enough of vanilla.Vanilla for the position helpers."""

    def __init__(self, pid, files):
        self.pid = pid
        self.files = files
        self.heightmap = np.full(pid.shape, 120, dtype=np.uint8)

    def text(self, rel):
        return self.files[rel]


def _pos_world():
    H, W = 20, 30
    van = np.ones((H, W), dtype=np.int32)
    van[:, 10:20] = 2
    van[:, 20:] = 3
    got = van.copy()
    got[:, 10:18] = 1                     # host 1 takes most of donor 2; 2 keeps columns 18-19
    files = {
        # unitstacks: province;type;x;y;z;rot;offset  (z counts from the bottom)
        "map/unitstacks.txt": "2;0;12.50;9.50;10.50;0.00;0.20\n3;0;25.50;9.50;5.50;0.00;0.20\n",
        "map/buildings.txt": "7;bunker;14.50;9.50;3.50;1.00;0\n7;bunker;25.00;9.50;3.00;1.00;0\n",
        "map/weatherpositions.txt": "4;15.50;9.50;15.50;small\n",
    }
    return van, got, files


def test_relocate_positions_moves_only_lines_on_taken_pixels():
    from experiments.exp02b import position_problems, relocate_positions
    van, got, files = _pos_world()
    v = FakeV(van, files)
    new, counts = relocate_positions(v, van, got)
    assert counts == {"map/buildings.txt": 1, "map/unitstacks.txt": 1, "map/weatherpositions.txt": 1}
    for rel in files:
        assert position_problems(v, van, got, rel, new[rel]) == []
        a, b = files[rel].splitlines(), new[rel].splitlines()
        assert len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1
    assert new["map/unitstacks.txt"].splitlines()[1] == files["map/unitstacks.txt"].splitlines()[1]


def test_position_problems_negative():
    from experiments.exp02b import position_problems, relocate_positions
    van, got, files = _pos_world()
    v = FakeV(van, files)
    new, _ = relocate_positions(v, van, got)
    rel = "map/unitstacks.txt"
    assert position_problems(v, van, got, rel, None)                             # line on a taken pixel not moved
    bad = new[rel].replace(";0.20\n", ";0.30\n", 1)
    assert any("other than x/y/z" in p for p in position_problems(v, van, got, rel, bad))
    moved_wrong = new[rel].splitlines()
    s = moved_wrong[0].split(";")
    s[2] = "12.50"                                                              # back onto the host's pixels
    moved_wrong[0] = ";".join(s)
    assert position_problems(v, van, got, rel, "\n".join(moved_wrong) + "\n")
    low = new[rel].replace(";12.00;", ";0.00;", 1)                              # moved line with a wrong height
    assert low != new[rel]
    assert any("height y=0.00" in p for p in position_problems(v, van, got, rel, low))
    extra = new[rel].replace("3;0;25.50", "3;0;26.50")                          # untouched line changed
    assert any("not re-assigned" in p for p in position_problems(v, van, got, rel, extra))
    assert position_problems(v, van, got, rel, new[rel] + "3;1;25.50;9.50;5.50;0.00;0.20\n")


# ---------------------------------------------------------------- against the game install (skipped without it)
@pytest.fixture(scope="module")
def built(ctx, tmp_path_factory):
    """Fresh strip-full and block-400 builds (block-800 is the same code at 34 s; build.py --check covers it)."""
    from experiments.build import build_into
    from experiments.registry import resolve
    root = tmp_path_factory.mktemp("e2b")
    outs = {}
    for bid in ("EXP-02b-strip-full", "EXP-02b-block-400"):
        (exp, b), = resolve(ctx, bid)
        out = root / b
        out.mkdir()
        build_into(ctx, exp, b, out)
        outs[b] = (exp, out)
    return outs


def _edit_pid(ctx, out, fn):
    from experiments.bmpio import read_bmp, write_bmp
    from experiments.mapdata import pid_from_rgb, rgb_from_pid
    p = out / "map" / "provinces.bmp"
    orig = p.read_bytes()
    bmp = read_bmp(orig)
    colors = ctx.vanilla.definition.colors()
    pid = pid_from_rgb(bmp.pixels, colors)
    fn(pid)
    p.write_bytes(write_bmp(bmp, rgb_from_pid(pid, colors), keep_tail=True))
    return p, orig


@pytest.mark.parametrize("bid", ["EXP-02b-strip-full", "EXP-02b-block-400"])
def test_fresh_build_passes_check(ctx, built, bid):
    exp, out = built[bid]
    assert exp.check(ctx, bid, out) == []


def test_selector_picks_the_remaining_builds_in_run_order(ctx):
    """P00b-f6 retired block-800-sea / -land (they cut naval regions in pieces; no clean 800-px square exists)."""
    from experiments.exp02b import RETIRED
    from experiments.registry import resolve
    assert [b for _, b in resolve(ctx, "EXP-02b")] == ["EXP-02b-strip-full", "EXP-02b-block-400"]
    assert "EXP-02b-strip-full" not in [b for _, b in resolve(ctx, "EXP-02")]
    everything = [b for _, b in resolve(ctx, "all")]
    assert not set(RETIRED) & set(everything)
    for b in RETIRED:
        with pytest.raises(SystemExit):
            resolve(ctx, b)


@pytest.mark.parametrize("bid", ["EXP-02b-strip-full", "EXP-02b-block-400"])
def test_readme_states_side_effects(ctx, built, bid):
    exp, out = built[bid]
    r = (out / "README.txt").read_text(encoding="utf-8")
    for part in ("If this build fails, it does NOT by itself show a size limit", "neighbours",
                 "the most-connected province in the normal game touches 23", "donor provinces lost pixels",
                 "position lines moved", "strategic regions", "strip-full and block-400, were both run",
                 "block-800-sea and block-800-land were retired", "each EXP-02b build tests one size"):
        assert part in r, part
    assert "only the three sizes tested" not in r                       # no reused EXP-02 limitation
    assert ("DO NOT RUN AGAIN" in r) == (bid == "EXP-02b-block-400")      # the rejected build says so first


def test_constants_still_valid_on_this_game(ctx):
    from experiments.exp02b import BLOCKS, protected_ids, ring_ok
    v = ctx.vanilla
    pid = np.asarray(v.pid)
    prot = protected_ids(v)
    for size, spec in BLOCKS.items():
        for kind, (r0, c0, host) in spec.items():
            assert ring_ok(v.types[pid], kind, r0, c0, size) and host not in prot


def _block_neg(ctx, built, fn, needle):
    bid = "EXP-02b-block-400"
    exp, out = built[bid]
    p, orig = _edit_pid(ctx, out, fn)
    try:
        probs = exp.check(ctx, bid, out)
        assert any(needle in x for x in probs), probs
    finally:
        p.write_bytes(orig)
    assert exp.check(ctx, bid, out) == []


def test_check_catches_a_non_donor_pixel(ctx, built):
    from experiments.exp02b import BLOCKS, protected_ids
    r0, c0, host = BLOCKS[400][LAND]
    prot = protected_ids(ctx.vanilla)
    van = np.asarray(ctx.vanilla.pid)

    def fn(pid):                           # a protected province inside the square loses one pixel to the host
        sub = van[r0:r0 + 400, c0:c0 + 400]
        ys, xs = np.nonzero(np.isin(sub, sorted(prot)) & (ctx.vanilla.types[sub] == LAND))
        pid[r0 + ys[0], c0 + xs[0]] = host
    _block_neg(ctx, built, fn, "outside the allowed donors")


@pytest.fixture(scope="module")
def inside_remnant(ctx, built):
    """(host, donor) of the 400-px sea block: a donor that now exists only as its remnant inside the square."""
    from experiments.exp02b import BLOCKS
    exp, out = built["EXP-02b-block-400"]
    r0, c0, host = BLOCKS[400][SEA]
    info = exp.make_blocks(ctx.vanilla, 400, (LAND, SEA))[1][SEA]
    van = np.asarray(ctx.vanilla.pid)
    whole = [int(d) for d in sorted(info["remnant_inside"], key=int)
             if (van[r0:r0 + 400, c0:c0 + 400] == int(d)).sum() == (van == int(d)).sum()]
    return host, whole[0]


def test_check_catches_a_vanished_donor(ctx, built, inside_remnant):
    host, d = inside_remnant

    def fn(pid):                           # only that donor's remnant goes to the host: the province vanishes
        assert (pid == d).sum() >= 9
        pid[pid == d] = host
    _block_neg(ctx, built, fn, "below 8 px")


def test_check_catches_a_remnant_below_the_promised_size(ctx, built, inside_remnant):
    from experiments.exp02b import REMNANT
    host, d = inside_remnant

    def fn(pid):                           # the remnant loses one pixel: 8 px is legal, but the README promises 9
        ys, xs = np.nonzero(pid == d)
        assert len(ys) == REMNANT
        pid[ys[0], xs[0]] = host
    _block_neg(ctx, built, fn, f"below the {REMNANT}-px remnant")


def test_check_catches_a_moved_line_with_a_wrong_height(ctx, built):
    bid = "EXP-02b-block-400"
    exp, out = built[bid]
    p = out / "map" / "unitstacks.txt"
    orig = p.read_bytes()
    van = ctx.vanilla.bytes("map/unitstacks.txt")
    a, b = orig.split(b"\n"), van.split(b"\n")
    i = next(k for k in range(len(a)) if a[k] != b[k])
    s = a[i].split(b";")
    s[3] = b"0.00"
    a[i] = b";".join(s)
    try:
        p.write_bytes(b"\n".join(a))
        assert any("height y=0.00" in x for x in exp.check(ctx, bid, out))
    finally:
        p.write_bytes(orig)


def test_check_catches_an_unfilled_block(ctx, built):
    from experiments.exp02b import BLOCKS
    r0, c0, host = BLOCKS[400][SEA]
    van = np.asarray(ctx.vanilla.pid)

    def fn(pid):                           # give a 20x20 patch back to its donors
        pid[r0 + 150:r0 + 170, c0 + 150:c0 + 170] = van[r0 + 150:r0 + 170, c0 + 150:c0 + 170]
    _block_neg(ctx, built, fn, "block not filled")


def test_check_catches_a_host_outside_the_square(ctx, built):
    from experiments.exp02b import BLOCKS
    r0, c0, host = BLOCKS[400][LAND]

    def fn(pid):
        pid[r0 + 200, c0 + 400] = host     # one pixel right of the square
    _block_neg(ctx, built, fn, "bounding box")


@pytest.mark.parametrize("bid", ["EXP-02b-strip-full", "EXP-02b-block-400"])
def test_check_catches_an_unmoved_position(ctx, built, bid):
    exp, out = built[bid]
    p = out / "map" / "unitstacks.txt"
    orig = p.read_bytes()
    van = ctx.vanilla.bytes("map/unitstacks.txt")
    a, b = orig.split(b"\n"), van.split(b"\n")
    i = next(k for k in range(len(a)) if a[k] != b[k])
    a[i] = b[i]                            # put one relocated line back on its taken pixel
    try:
        p.write_bytes(b"\n".join(a))
        assert any("was not moved" in x for x in exp.check(ctx, bid, out))
    finally:
        p.write_bytes(orig)


def test_check_catches_a_moved_untouched_line(ctx, built):
    bid = "EXP-02b-block-400"
    exp, out = built[bid]
    p = out / "map" / "buildings.txt"
    orig = p.read_bytes()
    lines = orig.split(b"\n")
    s = lines[0].split(b";")
    s[2] = b"%.2f" % (float(s[2]) + 1)
    lines[0] = b";".join(s)
    try:
        p.write_bytes(b"\n".join(lines))
        assert any("not re-assigned" in x for x in exp.check(ctx, bid, out))
    finally:
        p.write_bytes(orig)


def test_check_catches_an_extra_identical_file(ctx, built):
    bid = "EXP-02b-strip-full"
    exp, out = built[bid]
    p = out / "map" / "weatherpositions.txt"
    assert not p.exists()
    p.write_bytes(ctx.vanilla.bytes("map/weatherpositions.txt"))
    try:
        assert any("identical to vanilla" in x for x in exp.check(ctx, bid, out))
    finally:
        p.unlink()


def test_check_catches_a_second_strip_row(ctx, built):
    bid = "EXP-02b-strip-full"
    exp, out = built[bid]
    meta = exp.make_strips(ctx.vanilla)[1]

    def fn(pid):
        pid[meta["row"] + 1, meta["c0"] + 50] = meta["host"]
    p, orig = _edit_pid(ctx, out, fn)
    try:
        probs = exp.check(ctx, bid, out)
        assert any("strip is not a single row" in x for x in probs), probs
    finally:
        p.write_bytes(orig)


@pytest.mark.parametrize("bid", ["EXP-02b-strip-full", "EXP-02b-block-400"])
def test_rebuild_is_byte_identical(ctx, built, tmp_path, bid):
    from experiments.build import build_into
    from experiments.common import sha256_tree
    exp, out = built[bid]
    again = tmp_path / bid
    again.mkdir()
    build_into(ctx, exp, bid, again)
    assert sha256_tree(again) == sha256_tree(out)
