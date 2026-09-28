"""Read-only access to the local vanilla install, with in-process caching.

Nothing read here is ever written into the repository: builds copy vanilla
bytes into ``build/experiments/`` (gitignored) only.
"""
from __future__ import annotations

import re
from functools import cached_property
from pathlib import Path

import numpy as np

from .bmpio import read_bmp
from .common import KitError, decode, safe_join
from .mapdata import Definition, pid_from_rgb


class Vanilla:
    def __init__(self, game_dir: Path):
        self.root = Path(game_dir)
        if not (self.root / "map" / "provinces.bmp").is_file():
            raise KitError(f"{self.root} does not look like a HOI4 install (map/provinces.bmp missing)")

    # -- raw access
    def path(self, rel: str) -> Path:
        p = safe_join(self.root, rel)
        if not p.is_file():
            raise KitError(f"vanilla file {rel} not found")
        return p

    def bytes(self, rel: str) -> bytes:
        with open(self.path(rel), "rb") as fh:
            return fh.read()

    def text(self, rel: str) -> str:
        return decode(self.bytes(rel))

    def listdir(self, rel: str) -> list:
        d = safe_join(self.root, rel)
        return sorted(p.name for p in d.iterdir() if p.is_file())

    # -- parsed, cached
    @cached_property
    def definition(self) -> Definition:
        return Definition.parse(self.text("map/definition.csv"))

    @cached_property
    def provinces_bmp(self):
        return read_bmp(self.bytes("map/provinces.bmp"))

    @cached_property
    def pid(self) -> np.ndarray:
        pid = pid_from_rgb(self.provinces_bmp.pixels, self.definition.colors())
        pid.setflags(write=False)
        return pid

    @cached_property
    def types(self) -> np.ndarray:
        return self.definition.types()

    @cached_property
    def shape(self):
        return self.pid.shape

    def bmp(self, rel: str):
        return read_bmp(self.bytes(rel))

    @cached_property
    def heightmap(self) -> np.ndarray:
        return self.bmp("map/heightmap.bmp").pixels

    @cached_property
    def state_files(self) -> dict:
        """{file name: text} for history/states."""
        return {f: self.text("history/states/" + f) for f in self.listdir("history/states")}

    @cached_property
    def region_files(self) -> dict:
        return {f: self.text("map/strategicregions/" + f) for f in self.listdir("map/strategicregions")}

    @cached_property
    def province_state(self) -> dict:
        """{province id: (state id, file name)}."""
        from .mapdata import block_ids, find_block
        out = {}
        for f, t in self.state_files.items():
            o, c = find_block(t, "state", 0)
            body = t[o:c + 1]
            sid = int(re.search(r"\bid\s*=\s*(\d+)", re.sub(r"#[^\n]*", "", body)).group(1))
            for p in block_ids(t, "provinces", 1):
                out[p] = (sid, f)
        return out

    @cached_property
    def province_region(self) -> dict:
        from .mapdata import block_ids
        out = {}
        for f, t in self.region_files.items():
            rid = int(re.search(r"\bid\s*=\s*(\d+)", re.sub(r"#[^\n]*", "", t)).group(1))
            for p in block_ids(t, "provinces", 1):
                out[p] = (rid, f)
        return out
