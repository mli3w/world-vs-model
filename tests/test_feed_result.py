"""Tests for the matchday results helper (src/feed_result.py)."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
F = pytest.importorskip("feed_result")


def test_resolve_accepts_codes_and_names():
    assert F._resolve("BRA") == "Brazil"
    assert F._resolve("bra") == "Brazil"
    assert F._resolve("Brazil") == "Brazil"
    with pytest.raises(SystemExit):
        F._resolve("ZZZ")


def test_add_appends_full_names_and_is_idempotent(tmp_path):
    p = str(tmp_path / "wc_results.json")
    rows = F.add("BRA", "CRO", 2, 1, path=p)
    assert rows == [dict(a="Brazil", b="Croatia", ga=2, gb=1, stage="group")]
    F.add("ARG", "FRA", 3, 2, stage="ko", path=p)
    assert len(F._load(p)) == 2
    with pytest.raises(SystemExit):                       # same pairing again is rejected
        F.add("Croatia", "Brazil", 0, 0, path=p)
    assert len(F._load(p)) == 2                           # unchanged


def test_a_team_cannot_play_itself(tmp_path):
    with pytest.raises(SystemExit):
        F.add("BRA", "Brazil", 1, 0, path=str(tmp_path / "r.json"))
