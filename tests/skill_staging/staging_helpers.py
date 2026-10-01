"""Shared helpers for the P00e tests of the staged validator (tools/skill_staging/validate_map.py).

Synthetic fixtures need no game install: ``TileMap`` writes a tiny mod (1024 x 256 px, tiles of
32 x 32 px, one province per tile, one single-province strategic region per province unless a test
groups provinces) and ``run_validator`` runs the staged validator on it in a subprocess (the validator
keeps module-level state, so every run gets a fresh interpreter). Game-gated tests use HOI4_GAME_DIR.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
STAGED = REPO / "tools" / "skill_staging" / "validate_map.py"
ORIGINAL = REPO / ".claude" / "skills" / "hoi4-map-modding" / "scripts" / "validate_map.py"


def game_dir():
    g = os.environ.get("HOI4_GAME_DIR")
    if g and (Path(g) / "map" / "provinces.bmp").is_file():
        return Path(g)
    return None


def load_staged():
    """The staged validator as a module (for its pure functions)."""
    spec = importlib.util.spec_from_file_location("staged_validate_map", STAGED)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TileMap:
    """A synthetic mod: W x H pixels, T x T tiles; tile (r, c) starts as province r * (W // T) + c + 1."""

    def __init__(self, W=1024, H=256, T=32):
        self.W, self.H, self.T = W, H, T
        self.cols = W // T
        r, c = np.divmod(np.arange(H * W), W)
        self.pid = ((r // T) * self.cols + (c // T) + 1).reshape(H, W).astype(np.int64)
        self.next_id = int(self.pid.max()) + 1
        self.types = {}            # old id -> 'sea' / 'lake' (default land)
        self.groups = []           # [[old ids]] strategic regions with several members
        self.adjacency = []        # [(from old id, to old id, type, through old id)]
        self.replace_paths = []
        self.mapping = None

    def tile(self, r, c):
        return r * self.cols + c + 1

    def set_type(self, kind, *ids):
        for i in ids:
            self.types[i] = kind

    def paint(self, x0, y0, w, h, pid=None):
        """Paint the pixel rectangle (x0, y0 from the top) with ``pid`` (default: a new province); returns its id."""
        if pid is None:
            pid, self.next_id = self.next_id, self.next_id + 1
        self.pid[y0:y0 + h, x0:x0 + w] = pid
        return pid

    def region(self, *ids):
        self.groups.append(list(ids))

    def id(self, old):
        """Final (sequential) province id of an original id, after write()."""
        return self.mapping[old]

    def write(self, root: Path) -> Path:
        root = Path(root)
        present = np.unique(self.pid)
        self.mapping = {int(o): n for n, o in enumerate(present.tolist(), 1)}
        lut = np.zeros(int(present.max()) + 1, dtype=np.int64)
        lut[present] = np.arange(1, len(present) + 1)
        pid = lut[self.pid]
        n = len(present)
        types = ["land"] + [self.types.get(int(o), "land") for o in present.tolist()]
        m = root / "map"
        (m / "strategicregions").mkdir(parents=True, exist_ok=True)
        ids = np.arange(n + 1)
        colours = np.stack([ids % 256, ids // 256, np.full(n + 1, 77)], 1).astype(np.uint8)
        Image.fromarray(colours[pid]).save(m / "provinces.bmp")
        sea = np.isin(pid, [i for i in range(1, n + 1) if types[i] == "sea"])
        land = np.isin(pid, [i for i in range(1, n + 1) if types[i] == "land"])
        near = np.zeros_like(sea)
        near[1:] |= sea[:-1]; near[:-1] |= sea[1:]
        near[:, 1:] |= sea[:, :-1]; near[:, :-1] |= sea[:, 1:]
        near[:, 0] |= sea[:, -1]; near[:, -1] |= sea[:, 0]
        coastal = set(np.unique(pid[land & near]).tolist())
        rows = ["0;0;0;0;land;false;unknown;0"]
        for i in range(1, n + 1):
            t = types[i]
            terrain = {"land": "plains", "sea": "ocean", "lake": "lakes"}[t]
            flag = "true" if i in coastal else "false"
            rows.append(f"{i};{i % 256};{i // 256};77;{t};{flag};{terrain};{1 if t == 'land' else 0}")
        (m / "definition.csv").write_text("\n".join(rows) + "\n", encoding="latin-1")
        for name, index in (("terrain.bmp", 0), ("rivers.bmp", 255)):
            im = Image.new("P", (self.W, self.H), index)
            im.putpalette([v for v in range(256) for _ in range(3)])     # a full palette: 8-bit indexed BMP
            im.save(m / name)
        Image.new("L", (self.W, self.H), 96).save(m / "heightmap.bmp")
        Image.new("RGB", (self.W // 2, self.H // 2)).save(m / "world_normal.bmp")
        adj = ["From;To;Type;Through;start_x;start_y;stop_x;stop_y;adjacency_rule_name;Comment"]
        for f, t, kind, thr in self.adjacency:
            adj.append(f"{self.id(f)};{self.id(t)};{kind};{self.id(thr) if thr > 0 else -1};-1;-1;-1;-1;;test")
        adj.append("-1;-1;;-1;-1;-1;-1;-1;-1")
        (m / "adjacencies.csv").write_text("\n".join(adj) + "\n", encoding="latin-1")
        grouped = [[self.id(o) for o in g] for g in self.groups]
        used = {q for g in grouped for q in g}
        regions = grouped + [[q] for q in range(1, n + 1) if q not in used]
        for rid, members in enumerate(regions, 1):
            (m / "strategicregions" / f"{rid}-R{rid}.txt").write_text(
                f"strategic_region = {{\n\tid = {rid}\n\tname = \"R{rid}\"\n\tprovinces = {{\n\t\t"
                + " ".join(str(q) for q in members) + "\n\t}\n\tweather = {\n\t}\n}\n", encoding="utf-8")
        if self.replace_paths:
            (root / "descriptor.mod").write_text(
                "name=\"fixture\"\n" + "".join(f"replace_path=\"{p}\"\n" for p in self.replace_paths), encoding="utf-8")
        return root


def run_validator(root, *args, report=None, timeout=600):
    """Report (list of JSON items, with .rc = exit code) of the staged validator on ``root``. The JSON goes to
    ``report``, default next to ``root`` (only for synthetic fixtures in tmp)."""
    out = Path(report) if report is not None else Path(root).parent / (Path(root).name + "_report.json")
    p = subprocess.run([sys.executable, str(STAGED), str(root), "--json", str(out), *map(str, args)],
                       capture_output=True, text=True, timeout=timeout)
    assert p.returncode in (0, 1) and "Traceback" not in p.stderr, p.stderr
    items = json.loads(out.read_text())
    return Report(items, p.returncode, p.stdout)


class Report(list):
    def __init__(self, items, rc, stdout):
        super().__init__(items)
        self.rc, self.stdout = rc, stdout

    def codes(self, level=None):
        return {i["code"] for i in self if level is None or i["level"] == level}

    def of(self, code, level=None):
        return [i for i in self if i["code"] == code and (level is None or i["level"] == level)]

    def regions(self, code, level=None):
        return {i["region"] for i in self.of(code, level)}
