"""Tests for src/wc_upcoming.py — the forward-looking model↔market disagreement preview."""
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import wc_upcoming as U  # noqa: E402


def test_yes_price_parses_json_string():
    """outcomePrices arrives as a JSON-encoded string list — must be parsed, not treated as text."""
    assert abs(U._yes_price({"outcomePrices": '["0.62", "0.38"]'}) - 0.62) < 1e-9


def test_yes_price_parses_native_list():
    assert abs(U._yes_price({"outcomePrices": [0.62, 0.38]}) - 0.62) < 1e-9


def test_yes_price_falls_back_to_last_trade_price():
    """When outcomePrices is missing, lastTradePrice is the next-best signal of the YES side."""
    assert abs(U._yes_price({"lastTradePrice": 0.71}) - 0.71) < 1e-9


def test_yes_price_falls_back_to_best_bid():
    assert abs(U._yes_price({"bestBid": 0.18}) - 0.18) < 1e-9


def test_yes_price_returns_none_when_no_signal():
    assert U._yes_price({}) is None
    assert U._yes_price({"outcomePrices": ""}) is None
    assert U._yes_price({"outcomePrices": "not-json"}) is None


def test_elo_prior_returns_normalised_three_probs():
    """The model prior must sum to ~1.0 across (a-win, draw, b-win) so the disagreement is
    measured on the same probability scale as the market's outcomePrices."""
    pa, pd, pb = U._elo_prior("Spain", "Cape Verde")
    assert abs((pa + pd + pb) - 1.0) < 1e-9
    assert pa > pb                                              # Spain is the favourite
    assert pd < 0.15                                            # strength-aware draw rate kicks in


def test_elo_prior_returns_none_for_unknown_team():
    assert U._elo_prior("Atlantis", "Spain") is None
    assert U._elo_prior("Spain", "Wakanda") is None


def test_disagreements_handles_no_market_gracefully(monkeypatch, tmp_path):
    """When ESPN returns no upcoming fixtures (off-season, between rounds), the result is the
    empty list — NOT an exception, so the board panel shows nothing rather than breaking."""
    monkeypatch.setattr(U, "_espn_upcoming", lambda today, window_days: [])
    out = U.disagreements(window_days=3, top=6, min_gap=0.05)
    assert out == []


def test_disagreements_skips_matches_without_polymarket_market(monkeypatch):
    """If Polymarket has no market for an upcoming fixture (the 4 MD1 misses, for example),
    we silently skip it rather than emit a model-only row — apples-to-apples disagreement only."""
    monkeypatch.setattr(U, "_espn_upcoming",
                        lambda today, window_days: [{"a": "Spain", "b": "Cape Verde", "date": "2026-06-15"}])
    monkeypatch.setattr(U, "_fetch_current", lambda a, b, d: None)
    out = U.disagreements(window_days=3, top=6, min_gap=0.05)
    assert out == []


def test_disagreements_surfaces_match_with_big_gap(monkeypatch):
    """A real disagreement (model 38% USA, market 61% USA) must appear in the output, ranked by
    absolute gap, with the correct outcome (a_win) flagged."""
    monkeypatch.setattr(U, "_espn_upcoming",
                        lambda today, window_days: [{"a": "USA", "b": "Australia", "date": "2026-06-19"}])
    # mock market: 61% USA / 21% draw / 18% AUS (matches what Polymarket was showing)
    monkeypatch.setattr(U, "_fetch_current", lambda a, b, d: (0.61, 0.21, 0.18))
    out = U.disagreements(window_days=3, top=6, min_gap=0.05)
    assert len(out) == 1
    row = out[0]
    assert row["a"] == "USA" and row["b"] == "Australia"
    assert row["which"] == "a_win"                              # USA-win is where they disagree most
    assert row["gap"] > 0.15                                    # ~23pp disagreement
    assert row["pa_x"] > row["pa_m"]                            # market more bullish than model


def test_disagreements_filters_below_min_gap(monkeypatch):
    """Matches where market and model agree (within tolerance) must NOT clutter the preview."""
    # Equal teams + market matches Elo's ~36/28/36 split closely → tiny gap
    monkeypatch.setattr(U, "_espn_upcoming",
                        lambda today, window_days: [{"a": "France", "b": "England", "date": "2026-06-18"}])
    # mock: market = (0.40, 0.28, 0.32) — model will be close to this for similar Elos
    monkeypatch.setattr(U, "_fetch_current", lambda a, b, d: (0.40, 0.28, 0.32))
    out = U.disagreements(window_days=3, top=6, min_gap=0.20)  # huge floor — even big-gap matches drop
    assert out == []                                            # nothing meets the floor
