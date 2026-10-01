"""Fixtures for the P00e tests of the staged validator; the helpers live in staging_helpers.py (a unique
module name, so they never collide with tests/experiments/conftest.py)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from staging_helpers import game_dir  # noqa: E402


@pytest.fixture(scope="session")
def game():
    g = game_dir()
    if g is None:
        pytest.skip("HOI4 game dir not found (HOI4_GAME_DIR)")
    return g
