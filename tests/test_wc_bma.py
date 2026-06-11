"""Tests for Bayesian Model Averaging (src/wc_bma.py)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import wc_bma as B  # noqa: E402

MODELS = ["zk", "elo"]
LEVELS = ["advance", "win"]


def _forecasts(zk_w_spain=0.20, elo_w_spain=0.18):
    """A tiny pair-of-models forecast set we can vary per test."""
    return {
        ("zk", "advance", "Spain"): 0.95, ("elo", "advance", "Spain"): 0.97,
        ("zk", "advance", "Saudi"): 0.20, ("elo", "advance", "Saudi"): 0.10,
        ("zk", "win", "Spain"): zk_w_spain, ("elo", "win", "Spain"): elo_w_spain,
    }


def test_no_resolved_data_means_equal_weights():
    out = B.bma(_forecasts(), resolved=[])
    for level in LEVELS:
        for m in MODELS:
            assert abs(out["weights"][level][m] - 0.5) < 1e-6   # nothing learned -> 50/50


def test_better_model_at_a_level_gets_more_weight_at_that_level():
    # ELO nails advance: 5 forecasts at probs 0.95-0.99 all hit (outcome=1). ZK forecasts at 0.6.
    resolved = []
    for team, o in [("Spain", 1), ("Argentina", 1), ("France", 1), ("England", 1), ("Brazil", 1)]:
        resolved.append({"model": "elo", "level": "advance", "team": team, "prob": 0.95, "outcome": o})
        resolved.append({"model": "zk", "level": "advance", "team": team, "prob": 0.60, "outcome": o})
    out = B.bma(_forecasts(), resolved=resolved)
    assert out["weights"]["advance"]["elo"] > out["weights"]["advance"]["zk"]
    # the WIN level still has no resolved data -> stays ~50/50
    assert abs(out["weights"]["win"]["elo"] - 0.5) < 0.05


def test_ensemble_is_a_weighted_average():
    # Force ZK to have a clearly better record at win to drive its weight high
    resolved = []
    for i in range(20):
        resolved.append({"model": "zk", "level": "win", "team": f"T{i}", "prob": 0.05, "outcome": 0})
        resolved.append({"model": "elo", "level": "win", "team": f"T{i}", "prob": 0.30, "outcome": 0})
    out = B.bma(_forecasts(zk_w_spain=0.30, elo_w_spain=0.10), resolved=resolved)
    w_zk = out["weights"]["win"]["zk"]
    w_elo = out["weights"]["win"]["elo"]
    assert w_zk > w_elo                                    # ZK was better calibrated
    expected = w_zk * 0.30 + w_elo * 0.10
    assert abs(out["ensemble"][("win", "Spain")] - expected) < 1e-3


def test_per_level_weights_are_independent():
    # ZK is great at advance, terrible at win — should reflect in per-level weights
    resolved = []
    for i in range(10):
        resolved.append({"model": "zk", "level": "advance", "team": f"T{i}", "prob": 0.95, "outcome": 1})
        resolved.append({"model": "elo", "level": "advance", "team": f"T{i}", "prob": 0.55, "outcome": 1})
        resolved.append({"model": "zk", "level": "win", "team": f"T{i}", "prob": 0.50, "outcome": 0})
        resolved.append({"model": "elo", "level": "win", "team": f"T{i}", "prob": 0.10, "outcome": 0})
    out = B.bma(_forecasts(), resolved=resolved)
    assert out["weights"]["advance"]["zk"] > out["weights"]["advance"]["elo"]
    assert out["weights"]["win"]["elo"] > out["weights"]["win"]["zk"]


def test_weights_sum_to_one_per_level():
    out = B.bma(_forecasts(), resolved=[])
    for level, w in out["weights"].items():
        assert abs(sum(w.values()) - 1.0) < 1e-6


def test_ensemble_omits_models_that_dont_forecast_a_team():
    # Only ZK has a forecast for a specific outcome; the ensemble should equal ZK there (renormalised)
    fc = {("zk", "win", "Spain"): 0.20}                    # no Elo prob for this slot
    out = B.bma(fc, resolved=[])
    assert abs(out["ensemble"][("win", "Spain")] - 0.20) < 1e-6
