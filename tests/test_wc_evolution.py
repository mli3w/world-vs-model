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
    assert E.match_upsets([], {}) == []


def test_match_upsets_surface_underdog_wins_and_drop_expected_results():
    ratings = {
        "Australia": 1775, "Türkiye": 1906,            # +131 gap → ~32%/40%/28% with draws
        "Germany": 1925, "Curaçao": 1433,              # +492 → favourite ~93%, near-zero surprise
        "France": 2081, "Senegal": 1866,               # +215 → favourite ~55%, draws ~28%
    }
    results = [
        {"a": "Australia", "b": "Türkiye", "ga": 2, "gb": 0, "stage": "group"},   # underdog win
        {"a": "Germany",   "b": "Curaçao", "ga": 7, "gb": 1, "stage": "group"},    # expected blowout
        {"a": "France",    "b": "Senegal", "ga": 3, "gb": 1, "stage": "group"},    # favourite win
    ]
    ups = E.match_upsets(results, ratings, top=5, min_bits=0.8)
    teams = [(u["a"], u["b"]) for u in ups]
    assert ("Australia", "Türkiye") in teams                # surfaces the upset
    assert ("Germany", "Curaçao") not in teams              # boring blowout filtered out
    # the underdog win should have the highest surprisal bits among returned
    au = next(u for u in ups if u["a"] == "Australia")
    assert au["kind"] == "A_win" and au["bits"] > 1.0       # >1 bit of surprise
    assert au["winner"] == "Australia"


def test_match_upsets_handles_draws_correctly():
    ratings = {"Spain": 2157, "Cape Verde": 1578}            # +579 → ~95%/3%/28% allocation
    # A score draw is genuinely shocking when Elo gap is huge — 28% draw rate but the gap is enormous
    results = [{"a": "Spain", "b": "Cape Verde", "ga": 0, "gb": 0, "stage": "group"}]
    ups = E.match_upsets(results, ratings, top=3, min_bits=0.5)
    # Draw was given ~28% pre-match = ~1.8 bits; should surface
    assert len(ups) == 1 and ups[0]["kind"] == "draw"
    assert ups[0]["winner"] is None
    assert ups[0]["bits"] > 1.0


def test_match_upsets_skips_unknown_teams():
    results = [{"a": "Atlantis", "b": "Wakanda", "ga": 3, "gb": 1}]
    assert E.match_upsets(results, {"Spain": 2157}) == []
