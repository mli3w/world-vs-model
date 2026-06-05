"""Tests for the ledger stamp (src/worldcup_register.py) — synthetic, no network, temp files."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
R = pytest.importorskip("worldcup_register")
WL = pytest.importorskip("worldcup_live")

LADDER = {"advance": {"A": 0.9, "B": 0.7, "C": 0.5, "D": 0.3},
          "win": {"A": 0.40, "B": 0.30, "C": 0.20, "D": 0.10},
          "reach_QF": {}, "reach_SF": {}, "reach_F": {}}
FUND = {"advance": {WL._norm(t): p for t, p in {"A": .92, "B": .68, "C": .55, "D": .25}.items()},
        "win": {WL._norm(t): p for t, p in {"A": .45, "B": .25, "C": .18, "D": .12}.items()}}


def _paths(tmp):
    R.PRED = os.path.join(tmp, "predictions.jsonl")
    R.SCORE = os.path.join(tmp, "scorecard.json")
    R.CORE = os.path.join(tmp, "wc_core.jsonl")
    R.LIVE = os.path.join(tmp, "wc_live.jsonl")
    R.LEDGER = tmp


def test_snapshot_registers_both_models_and_freezes_books(tmp_path):
    _paths(str(tmp_path))
    card = R.snapshot(ladder=LADDER, fundamental=FUND, date="2026-06-05")
    preds = R._load(R.PRED)
    models = {p["model"] for p in preds}
    assert models == {"zero_knowledge", "elo"}                       # both models registered
    assert all(p["outcome"] is None and p["provenance"] == "real" for p in preds)
    assert all("market" in p for p in preds)                         # captured market baseline
    assert card["n_total"] == 16 and card["n_resolved"] == 0          # 2 models x 2 levels x 4 teams
    assert os.path.exists(R.CORE) and os.path.exists(R.LIVE)          # day-0 books frozen


def test_snapshot_is_immutable_per_date(tmp_path):
    _paths(str(tmp_path))
    R.snapshot(ladder=LADDER, fundamental=FUND, date="2026-06-05")
    n1 = len(R._load(R.PRED))
    R.snapshot(ladder=LADDER, fundamental=FUND, date="2026-06-05")   # same day again
    assert len(R._load(R.PRED)) == n1                                # no double-registration


def test_resolve_scores_brier_and_skill_vs_market(tmp_path):
    _paths(str(tmp_path))
    R.snapshot(ladder=LADDER, fundamental=FUND, date="2026-06-05")
    card = R.resolve("win", {"A": 1, "B": 0, "C": 0, "D": 0})         # A wins the cup
    assert card["n_resolved"] == 8                                   # 2 models x 4 teams at win
    assert "elo" in card["by_model"] and "brier" in card["by_model"]["elo"]
    assert "hit_rate" in card["overall"] and "brier" in card["overall"]
