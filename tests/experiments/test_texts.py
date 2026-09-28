"""README and descriptor texts."""
import re

import pytest

from conftest import REPO
from experiments.texts import CANNOT_PROVE, descriptor, readme

TOCHECK = REPO / "to-check" / "2026-09-28_rendering-countries-canvas.md"


def test_cannot_prove_matches_to_check_file():
    if not TOCHECK.is_file():
        pytest.skip("to-check file not present")
    text = TOCHECK.read_text(encoding="utf-8")
    for exp, line in CANNOT_PROVE.items():
        assert line in text, f"{exp}: limitation text drifted from {TOCHECK.name}"
    # every limitation row of the to-check file is covered
    rows = re.findall(r"^\| (EXP-0\d) \| ([^|]+) \|\s*$", text, re.M)
    for exp, line in rows:
        assert CANNOT_PROVE[exp] == line.strip()


def test_descriptor_keys_and_replace_path():
    d = descriptor("EXP-07", "gap", ["history/states"], path="C:/x/build/experiments/EXP-07")
    assert 'name="P00b EXP-07 gap"' in d and 'supported_version="1.19.*"' in d
    assert 'replace_path="history/states"' in d and 'path="C:/x/build/experiments/EXP-07"' in d
    assert "tags={" in d


def test_readme_sections(tmp_path):
    r = readme("EXP-05-2to1", "trees", prop="only trees.bmp", why="why", launch="launch", steps=["do x"],
               send=["send y"], expected="no finding", cannot=["EXP-05"], user_dir=tmp_path)
    for part in ("THE ONE THING THIS TEST CHANGES", "STEPS", "WHAT TO SEND BACK", "EXPECTED OFFLINE VALIDATOR FINDING",
                 "WHAT THIS TEST CANNOT PROVE", "install.py EXP-05-2to1", "--uninstall", "logs/error.log",
                 CANNOT_PROVE["EXP-05"]):
        assert part in r, part
    assert r.rstrip().endswith(CANNOT_PROVE["EXP-05"])
