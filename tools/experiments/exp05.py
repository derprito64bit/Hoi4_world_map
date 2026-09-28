"""EXP-05: trees.bmp at 2:1 and 3:1 (vanilla 1650x600 = 2.75:1).

Only ``map/trees.bmp`` changes: the whole image is resampled (nearest
neighbour, so no new palette indices) to 1200x600 (2:1) or 1800x600 (3:1).
Height stays 600; the original BITMAPV5 header and 256-entry palette are kept.
If the engine stretches trees.bmp over the whole map, forests stay where they
were (just coarser/finer); if it does not, forests near the right and top map
edges shift or disappear. That is what the screenshots show.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import texts
from .base import Expected, Experiment, check_descriptor, check_file_set
from .bmpio import read_bmp, write_bmp
from .common import write_bytes

TREES = "map/trees.bmp"
SIZES = {"2to1": (1200, 600), "3to1": (1800, 600)}


def resize_nearest(img: np.ndarray, w: int, h: int) -> np.ndarray:
    """Nearest-neighbour resample of a 2-D index image (pixel-centre sampling, exact integers)."""
    H, W = img.shape
    ys = ((2 * np.arange(h) + 1) * H) // (2 * h)
    xs = ((2 * np.arange(w) + 1) * W) // (2 * w)
    return img[ys][:, xs]


class Exp05(Experiment):
    exp_id = "EXP-05"
    title = "trees.bmp aspect ratio"
    priority = 5

    def build_ids(self, ctx):
        return [f"EXP-05-{k}" for k in SIZES]

    def title_for(self, build_id):
        w, h = SIZES[build_id.split("-")[-1]]
        return f"trees.bmp {w}x{h} ({build_id.split('-')[-1].replace('to', ':')})"

    def expected(self, build_id):
        return Expected(text="No new finding (the validator does not read trees.bmp): " + texts.BASELINE_WARNS + ".")

    def build(self, ctx, build_id, out: Path):
        w, h = SIZES[build_id.split("-")[-1]]
        tb = ctx.vanilla.bmp(TREES)
        write_bytes(out, TREES, write_bmp(tb, resize_nearest(tb.pixels, w, h)))
        return {"size": (w, h)}

    def readme(self, ctx, build_id, info):
        w, h = info["size"]
        return texts.readme(
            build_id, self.title_for(build_id),
            prop=f"map/trees.bmp only: resized from 1650x600 (2.75:1) to {w}x{h} "
                 f"({build_id.split('-')[-1].replace('to', ':')}), same colours, same palette. Nothing else changes.",
            why="trees.bmp (where forests are drawn) is not the size of the map; the game stretches it. Our map "
                "has a different shape (5120x2304 = 2.22:1), so we need to know whether the game stretches "
                "any trees.bmp to the whole map or needs one exact shape.",
            launch=texts.LAUNCH_NORMAL,
            steps=["Start a new game with any country and pause. Use the normal map mode, zoom in until trees "
                   "are visible (about the height where province names appear).",
                   "Take screenshots of forests at the same four places, in this test AND once in the normal "
                   "game without mods (for comparison): (1) Alaska / Yukon (left map edge), (2) Kamchatka "
                   "(right map edge), (3) northern Scandinavia (top), (4) southern Chile (bottom).",
                   "Name each screenshot with the place and 'test' or 'vanilla'."],
            send=["The 8 screenshots (4 places x test/vanilla).",
                  "In words: are forests in the same places as in the normal game? Shifted? Missing? Stretched?"],
            expected=self.expected(build_id).text, cannot=["EXP-05"], user_dir=ctx.user,
            notes=["Two variants (2:1 and 3:1); test both the same way."])

    def check(self, ctx, build_id, out):
        probs = check_file_set(out, {TREES}) + check_descriptor(self, build_id, out)
        p = out / TREES
        if not p.is_file():
            return probs
        van = ctx.vanilla.bmp(TREES)
        got = read_bmp(p.read_bytes())
        w, h = SIZES[build_id.split("-")[-1]]
        if (got.width, got.height) != (w, h):
            probs.append(f"trees.bmp is {got.width}x{got.height}, expected {w}x{h}")
            return probs
        if got.bpp != 8 or got.dib_size != van.dib_size or got.palette != van.palette:
            probs.append("trees.bmp header type, bit depth or palette differs from vanilla")
        # header bytes identical apart from the size fields
        a, b = bytearray(van.header), bytearray(got.header)
        for off in (2, 18, 22, 34):
            a[off:off + 4] = b[off:off + 4] = b"\0\0\0\0"
        if a != b:
            probs.append("trees.bmp header differs beyond width/height/size fields")
        if not np.array_equal(got.pixels, resize_nearest(van.pixels, w, h)):
            probs.append("trees.bmp content is not the nearest-neighbour resample of vanilla")
        return probs
