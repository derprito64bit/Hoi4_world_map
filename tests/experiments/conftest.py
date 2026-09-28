"""Shared fixtures for the P00b experiment-kit tests.

Most tests use tiny synthetic maps and need no game install. Tests marked with
the ``game`` fixture are skipped when HOI4_GAME_DIR (or the settings.local.json
fallback) does not point at a HOI4 install.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from experiments.common import game_dir  # noqa: E402
from experiments.mapdata import Definition  # noqa: E402

GAME = game_dir()


@pytest.fixture(scope="session")
def game():
    if GAME is None:
        pytest.skip("HOI4 game dir not found (HOI4_GAME_DIR)")
    return GAME


@pytest.fixture(scope="session")
def ctx(game):
    from experiments.base import Ctx
    from experiments.vanilla import Vanilla
    return Ctx(game=game, vanilla=Vanilla(game), repo_root=REPO)


def make_definition(types, coastal=None, terrain=None):
    """Definition rows for IDs 0..len(types)-1 (types[0] ignored)."""
    rows = [["0", "0", "0", "0", "land", "false", "unknown", "0"]]
    for i in range(1, len(types)):
        t = types[i]
        rows.append([str(i), str((i * 37) % 256), str((i * 91) % 256), str(i // 256 + 1), t,
                     "true" if coastal and coastal[i] else "false",
                     terrain[i] if terrain else {"land": "plains", "sea": "ocean", "lake": "lakes"}[t],
                     "1" if t == "land" else "0"])
    return Definition(rows=rows, trailing_newline=False)


@pytest.fixture
def tiny_map():
    """64 x 96 map without X-crossings (wrap included): sea band on top (IDs 1-3), four land
    provinces (4-7) below, a lake (8) inside province 7."""
    H, W = 64, 96
    pid = np.zeros((H, W), dtype=np.int32)
    pid[:16, :] = 1
    pid[:16, 30:60], pid[:16, 60:90] = 2, 3
    pid[16:40, :48], pid[16:40, 48:] = 4, 5
    pid[40:, :] = 6
    pid[40:, 30:70] = 7
    pid[50:54, 60:66] = 8
    types = ["", "sea", "sea", "sea", "land", "land", "land", "land", "lake"]
    return pid, make_definition(types)
