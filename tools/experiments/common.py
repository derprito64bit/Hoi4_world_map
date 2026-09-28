"""Shared helpers: machine paths, safe file writing, text round-tripping, hashing.

Machine paths come from the environment variables ``HOI4_GAME_DIR`` and
``HOI4_USER_DIR``. When a variable is unset, the ``env`` block of the
repository's ``.claude/settings.local.json`` (gitignored, machine-local) is read
as a fallback. Nothing else is hard-coded.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_ROOT = REPO_ROOT / "build" / "experiments"
SETTINGS_LOCAL = REPO_ROOT / ".claude" / "settings.local.json"
TOOL_TAG = "p00b-experiment-kit"


class KitError(RuntimeError):
    """A build or install step failed loudly (bad input, missing anchor, unsafe path...)."""


# ---------------------------------------------------------------- machine paths
def _settings_env(settings_path: Path = SETTINGS_LOCAL) -> dict:
    try:
        with open(settings_path, encoding="utf-8") as fh:
            env = json.load(fh).get("env", {})
        return env if isinstance(env, dict) else {}
    except (OSError, ValueError):
        return {}


def machine_path(var: str, settings_path: Path = SETTINGS_LOCAL) -> Path | None:
    """Value of an env var (e.g. HOI4_GAME_DIR), else the settings.local.json fallback, else None."""
    val = os.environ.get(var) or _settings_env(settings_path).get(var)
    if not val or "<you>" in val:
        return None
    return Path(val)


def game_dir() -> Path | None:
    p = machine_path("HOI4_GAME_DIR")
    return p if p and (p / "map" / "provinces.bmp").is_file() else None


def user_dir() -> Path | None:
    return machine_path("HOI4_USER_DIR")


# ---------------------------------------------------------------- safe paths
def is_within(child: Path, parent: Path) -> bool:
    """True if child resolves to parent or a path below it (symlinks resolved)."""
    c, p = Path(child).resolve(), Path(parent).resolve()
    return c == p or p in c.parents


def safe_join(base: Path, rel: str) -> Path:
    """base / rel, refusing absolute paths and anything that escapes base."""
    relp = Path(rel)
    if relp.is_absolute() or relp.drive or any(part == ".." for part in relp.parts):
        raise KitError(f"unsafe relative path {rel!r}")
    out = Path(base) / relp
    if not is_within(out, base):
        raise KitError(f"{rel!r} escapes {base}")
    return out


def reset_dir(path: Path, root: Path = BUILD_ROOT) -> Path:
    """Delete and recreate an output folder; only ever below the build root."""
    path = Path(path)
    if not is_within(path, root) or path.resolve() == Path(root).resolve():
        raise KitError(f"refusing to reset {path}: not strictly inside {root}")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def write_bytes(base: Path, rel: str, data: bytes) -> Path:
    out = safe_join(base, rel)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        fh.write(data)
    return out


# ---------------------------------------------------------------- text
def decode(b: bytes) -> str:
    """Lossless bytes -> str (UTF-8 with surrogateescape; a BOM stays as U+FEFF)."""
    return b.decode("utf-8", "surrogateescape")


def encode(s: str) -> bytes:
    return s.encode("utf-8", "surrogateescape")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_tree(folder: Path) -> dict:
    """{relative posix path: sha256} for every file below folder, sorted."""
    folder = Path(folder)
    out = {}
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            with open(p, "rb") as fh:
                out[p.relative_to(folder).as_posix()] = hashlib.sha256(fh.read()).hexdigest()
    return out


def ee_project():
    """The skill's projection module (never copied: imported from .claude/skills/.../scripts)."""
    import importlib
    import sys
    scripts = REPO_ROOT / ".claude" / "skills" / "hoi4-map-modding" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return importlib.import_module("ee_project")


def fmt2(v: float) -> str:
    """Two-decimal number as vanilla writes positions (avoids '-0.00')."""
    s = f"{float(v):.2f}"
    return "0.00" if s == "-0.00" else s
