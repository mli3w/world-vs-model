"""Tests for the ESPN-driven auto-feeder (src/auto_feed_results.py)."""
import os
import sys
import json
import datetime as dt

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
A = pytest.importorskip("auto_feed_results")
F = pytest.importorskip("feed_result")


def test_resolve_team_handles_aliases_and_fuzzy_names():
    assert A._resolve_team("USA") == "USA"
    assert A._resolve_team("United States") == "USA"            # ESPN-specific alias
    assert A._resolve_team("Korea Republic") == "South Korea"   # FIFA-style
    assert A._resolve_team("Czech Republic") == "Czechia"
    assert A._resolve_team("Bosnia and Herzegovina") == "Bosnia-Herzegovina"
    assert A._resolve_team("Côte d'Ivoire") == "Ivory Coast"
    assert A._resolve_team("Cabo Verde") == "Cape Verde"
    assert A._resolve_team("Turkey") == "Türkiye"
    assert A._resolve_team("not a country") is None


def test_run_is_idempotent_per_pairing(monkeypatch, tmp_path):
    # conftest.py chdirs us into tmp_path; feed_result writes to ./ledger/wc_results.json
    ledger = tmp_path / "ledger" / "wc_results.json"

    def fake_fetch(day, timeout=15):
        if day == dt.date(2026, 6, 11):
            return [("Mexico", "South Africa", 2, 0, "group")]
        return []
    monkeypatch.setattr(A, "fetch_day", fake_fetch)

    added, skipped, unknown = A.run(days=2, today=dt.date(2026, 6, 11))
    assert added == 1 and skipped == 0 and unknown == []
    rows = json.loads(ledger.read_text())
    assert len(rows) == 1 and rows[0]["a"] == "Mexico" and rows[0]["ga"] == 2

    added2, skipped2, _ = A.run(days=2, today=dt.date(2026, 6, 11))
    assert added2 == 0 and skipped2 == 1                        # idempotent on the second run


def test_run_with_no_full_time_matches_is_a_noop(monkeypatch, tmp_path):
    ledger = tmp_path / "ledger" / "wc_results.json"
    monkeypatch.setattr(A, "fetch_day", lambda day, timeout=15: [])
    added, _, _ = A.run(days=3, today=dt.date(2026, 6, 11))
    assert added == 0 and not ledger.exists()


def test_run_flags_unknown_teams_without_crashing(monkeypatch, tmp_path):
    monkeypatch.setattr(A, "fetch_day", lambda day, timeout=15:
                        [("Atlantis", "Wakanda", 3, 1, "group")] if day == dt.date(2026, 6, 11) else [])
    added, _, unknown = A.run(days=2, today=dt.date(2026, 6, 11))
    assert added == 0 and unknown == [("Atlantis", "Wakanda")]


def test_full_scan_backfills_a_matchday_a_narrow_window_would_miss(monkeypatch, tmp_path):
    """The default (days=None) rescans from the tournament start, so an R32 result played a week ago
    that was never recorded gets backfilled — the 3-day window would have lost it for good."""
    def fake_fetch(day, timeout=15):
        return [("Germany", "Paraguay", 0, 1, "ko")] if day == dt.date(2026, 6, 29) else []
    monkeypatch.setattr(A, "fetch_day", fake_fetch)
    today = dt.date(2026, 7, 6)                                 # a week after the match
    assert A.run(days=3, today=today)[0] == 0                   # narrow window never reaches Jun 29
    added, _, unknown = A.run(today=today)                      # full-tournament scan backfills it
    assert added == 1 and unknown == []
    rows = json.loads((tmp_path / "ledger" / "wc_results.json").read_text())
    assert dict(a="Germany", b="Paraguay", ga=0, gb=1, stage="ko") in rows


def test_stage_hint_switches_to_ko_after_jun_27(monkeypatch, tmp_path):
    seen_stages = []

    def fake_fetch(day, timeout=15):
        seen_stages.append("group" if day <= dt.date(2026, 6, 27) else "ko")
        return []
    monkeypatch.setattr(A, "fetch_day", fake_fetch)
    A.run(days=1, today=dt.date(2026, 6, 28))                  # day after KO turn
    assert "ko" in seen_stages
