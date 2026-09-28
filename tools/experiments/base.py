"""Experiment interface and shared check helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .common import BUILD_ROOT, sha256_tree, user_dir
from .texts import descriptor

BASE_WARN = {"DEF_SEA_CONTINENT", "BBOX_LARGE", "STATE_NONCONTIGUOUS", "RIVERS_ON_SEA", "RIVERS_THICK",
             "STATE_CATEGORY_DUP"}
META_FILES = {"descriptor.mod", "README.txt"}


@dataclass
class Ctx:
    game: Path | None
    vanilla: object | None               # vanilla.Vanilla
    repo_root: Path
    build_root: Path = BUILD_ROOT
    user: Path | None = field(default_factory=user_dir)


@dataclass
class Expected:
    errors: set = field(default_factory=set)
    warns: set = field(default_factory=lambda: set(BASE_WARN))
    text: str = ""


class Experiment:
    exp_id = "EXP-00"
    title = ""
    priority = 0          # build order (EXP-07 last)

    def build_ids(self, ctx: Ctx) -> list:
        raise NotImplementedError

    def title_for(self, build_id: str) -> str:
        return self.title

    def replace_paths(self, build_id: str) -> list:
        return []

    def expected(self, build_id: str) -> Expected:
        return Expected()

    # build writes the mod content (map files etc.) and returns info for the README
    def build(self, ctx: Ctx, build_id: str, out: Path) -> dict:
        raise NotImplementedError

    def readme(self, ctx: Ctx, build_id: str, info: dict) -> str:
        raise NotImplementedError

    # check returns a list of problems (empty = only the intended property differs)
    def check(self, ctx: Ctx, build_id: str, out: Path) -> list:
        raise NotImplementedError

    def descriptor(self, build_id: str) -> str:
        return descriptor(build_id, self.title_for(build_id), self.replace_paths(build_id))


def check_file_set(out: Path, expected_rel: set) -> list:
    """Problems if the mod folder holds anything but the expected files (+ descriptor, README)."""
    have = set(sha256_tree(out))
    want = set(expected_rel) | META_FILES
    probs = []
    if have - want:
        probs.append(f"unexpected files: {sorted(have - want)[:10]}")
    if want - have:
        probs.append(f"missing files: {sorted(want - have)[:10]}")
    return probs


def check_descriptor(exp: Experiment, build_id: str, out: Path) -> list:
    p = out / "descriptor.mod"
    if not p.is_file() or p.read_text(encoding="utf-8") != exp.descriptor(build_id):
        return ["descriptor.mod differs from the expected text"]
    return []


def lines_diff(a: list, b: list):
    """(removed, added) multisets between two line lists, order-insensitive."""
    from collections import Counter
    ca, cb = Counter(a), Counter(b)
    return ca - cb, cb - ca
