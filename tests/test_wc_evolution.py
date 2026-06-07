"""Tests for the 'as it unfolds' layer (src/wc_evolution.py)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import wc_evolution as E  # noqa: E402


def test_surprisal_is_log2_bits():
    assert abs(E.surprisal(0.5) - 1.0) < 1e-9          # a coin-flip that lands = 1 bit
    assert abs(E.surprisal(0.125) - 3.0) < 1e-9        # a 1-in-8 that lands = 3 bits
    assert E.surprisal(1.0) < 1e-6                       # a sure thing = ~0 bits


def test_forecast_moves_ranks_biggest_swings():
    frozen = {"Spain": 0.17, "Morocco": 0.03, "Germany": 0.11, "Brazil": 0.10}
    live = {"Spain": 0.15, "Morocco": 0.16, "Germany": 0.02, "Brazil": 0.105}   # Morocco surges, Ger crashes
    mv = E.forecast_moves(frozen, live, top=3, min_delta=0.02)
    assert [m["team"] for m in mv] == ["Morocco", "Germany", "Spain"]            # by |delta|
    assert mv[0]["delta"] > 0 and mv[1]["delta"] < 0
    assert all(abs(m["delta"]) >= 0.02 for m in mv)
    # Brazil moved only +0.005 -> filtered out
    assert "Brazil" not in [m["team"] for m in mv]


def test_surprises_surface_upsets_and_flops_not_expected_results():
    resolved = [
        {"level": "advance", "team": "SaudiArabia", "model": 0.18, "market": 0.15, "outcome": 1},  # upset
        {"level": "win", "team": "Brazil", "model": 0.12, "market": 0.14, "outcome": 0},            # mild, expected-ish
        {"level": "reach_QF", "team": "Germany", "model": 0.80, "market": 0.78, "outcome": 0},      # favourite flop
        {"level": "advance", "team": "Spain", "model": 0.97, "market": 0.96, "outcome": 1},          # boring, expected
    ]
    s = E.surprises(resolved, top=10, min_bits=1.3)
    teams = [r["team"] for r in s]
    assert "SaudiArabia" in teams and "Germany" in teams       # the shocks surface
    assert "Spain" not in teams                                 # an expected advance is not a surprise
    sa = next(r for r in s if r["team"] == "SaudiArabia")
    assert sa["kind"] == "upset" and sa["called_better"] == "model"   # model gave it the higher chance
    ger = next(r for r in s if r["team"] == "Germany")
    assert ger["kind"] == "flop"


def test_dormant_when_no_results():
    assert E.forecast_moves({}, {}) == []
    assert E.surprises([]) == []
