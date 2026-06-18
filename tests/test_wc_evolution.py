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
    ratings = {"Spain": 2157, "Cape Verde": 1578}            # +579 Elo gap is enormous
    results = [{"a": "Spain", "b": "Cape Verde", "ga": 0, "gb": 0, "stage": "group"}]
    ups = E.match_upsets(results, ratings, top=3, min_bits=0.5)
    # Strength-aware draw rate: ~9% at this Elo gap → -log2(0.09) ≈ 3.4 bits of shock,
    # not the ~1.8 bits a flat 28% would give. A Spain draw against Cape Verde IS a top-tier upset.
    assert len(ups) == 1 and ups[0]["kind"] == "draw"
    assert ups[0]["winner"] is None
    assert ups[0]["bits"] > 3.0                              # was: > 1.0 under flat-28% draw rate
    assert ups[0]["pd"] < 0.15                                # draw rate decayed well below 28%


def test_elo_draw_rate_decays_with_strength_gap():
    """The strength-aware draw rate must fall as the Elo gap widens — 28% for equal teams down
    toward a single-digit floor for huge mismatches, where the favourite scores too often for a
    draw to stay realistic. Calibrated against international-football priors."""
    assert abs(E._elo_draw_rate(0) - 0.28) < 1e-9               # equal teams: keep 28%
    assert E._elo_draw_rate(200) < 0.27                          # mild gap: already dropping
    assert E._elo_draw_rate(400) < 0.18                          # big gap: well below 28%
    assert E._elo_draw_rate(600) < 0.12                          # huge gap: roughly halved
    assert E._elo_draw_rate(800) < 0.10                          # extreme: near the floor
    assert E._elo_draw_rate(2000) > 0.05                         # asymptote stays above zero
    # symmetric in sign
    assert abs(E._elo_draw_rate(500) - E._elo_draw_rate(-500)) < 1e-9


def test_match_upsets_skips_unknown_teams():
    results = [{"a": "Atlantis", "b": "Wakanda", "ga": 3, "gb": 1}]
    assert E.match_upsets(results, {"Spain": 2157}) == []


def test_match_upsets_prefers_polymarket_prices_when_provided():
    ratings = {"Australia": 1775, "Türkiye": 1906}              # Elo would say AUS ~28% to win
    results = [{"a": "Australia", "b": "Türkiye", "ga": 2, "gb": 0, "stage": "group"}]
    # Polymarket priced AUS at 18% — sharper than Elo, so the upset surprisal is BIGGER
    prices = {("australia", "türkiye"): (0.18, 0.26, 0.57)}     # alphabetised: A=australia, B=türkiye
    out = E.match_upsets(results, ratings, prices=prices, top=3, min_bits=0.5)
    assert out and out[0]["source"] == "polymarket"
    # Polymarket gave Australia 18% — the actual win is ~log2(1/0.18) ≈ 2.5 bits, not Elo's ~1.8
    assert out[0]["bits"] > 2.0
    assert abs(out[0]["pa"] - 0.18) < 1e-3                       # AUS-win price from Polymarket


def test_match_upsets_falls_back_to_elo_when_no_price():
    ratings = {"Australia": 1775, "Türkiye": 1906}
    results = [{"a": "Australia", "b": "Türkiye", "ga": 2, "gb": 0, "stage": "group"}]
    out = E.match_upsets(results, ratings, prices={}, top=3, min_bits=0.5)   # empty cache
    assert out and out[0]["source"] == "elo"


def test_match_upsets_orients_prices_to_match_row_order():
    # Stored alphabetised (A=australia, B=türkiye, so pa=AUS-win=0.18); if results lists Türkiye
    # as team a, the function should still output pa = T.win = 0.57
    ratings = {"Australia": 1775, "Türkiye": 1906}
    prices = {("australia", "türkiye"): (0.18, 0.26, 0.57)}
    results = [{"a": "Türkiye", "b": "Australia", "ga": 0, "gb": 2, "stage": "group"}]
    out = E.match_upsets(results, ratings, prices=prices, top=3, min_bits=0.5)
    assert out and abs(out[0]["pa"] - 0.57) < 1e-3              # Türkiye-win price now in the pa slot
    assert abs(out[0]["pb"] - 0.18) < 1e-3                       # Australia-win in pb
    assert out[0]["winner"] == "Australia"                       # outcome unchanged: B (Australia) won
