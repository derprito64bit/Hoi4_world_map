"""Shared setup for the P00d hybrid-projection tests (no game install, no network needed)."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

from projection import hybrid  # noqa: E402

LAMBDAS = hybrid.LAMBDA_B_CANDIDATES
RAMPS = (hybrid.DEFAULT_RAMP, 1.0, 0.25)


@pytest.fixture(params=LAMBDAS, ids=lambda v: f"lb{v:g}")
def lambda_b(request):
    return request.param


@pytest.fixture(params=RAMPS, ids=lambda v: f"r{v:g}")
def ramp(request):
    return request.param
