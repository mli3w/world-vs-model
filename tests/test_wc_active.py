"""Tests for the Active book's rotation rules (src/wc_active.py)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import wc_active as A  # noqa: E402

BUF = 0.01


def test_aligned_edge_sign():
    assert A.aligned_edge(+10, fair=0.6, price=0.5) > 0      # long, underpriced -> favourable
    assert A.aligned_edge(-10, fair=0.4, price=0.5) > 0      # short, overpriced -> favourable
    assert A.aligned_edge(+10, fair=0.4, price=0.5) < 0      # long but now overpriced -> against


def test_classify_has_a_hysteresis_band():
    long_leg = {"shares": 10}
    assert A.classify_leg(long_leg, fair=0.60, price=0.50, buffer=BUF) == A.HOLD          # wide edge
    assert A.classify_leg(long_leg, fair=0.505, price=0.50, buffer=BUF) == A.TAKE_PROFIT  # converged
    assert A.classify_leg(long_leg, fair=0.498, price=0.50, buffer=BUF) == A.TAKE_PROFIT  # tiny flip -> NOT cut
    assert A.classify_leg(long_leg, fair=0.45, price=0.50, buffer=BUF) == A.CUT           # clearly against
    short_leg = {"shares": -10}
    assert A.classify_leg(short_leg, fair=0.40, price=0.50, buffer=BUF) == A.HOLD
    assert A.classify_leg(short_leg, fair=0.55, price=0.50, buffer=BUF) == A.CUT


def test_should_rotate_needs_to_beat_round_trip():
    assert not A.should_rotate(edge_held=0.05, edge_cand=0.06, cost=0.01, buffer=BUF)
    assert A.should_rotate(edge_held=0.02, edge_cand=0.10, cost=0.01, buffer=BUF)


def test_converged_leg_rides_to_resolution_without_a_candidate():
    legs = [{"level": "win", "team": "Spain", "shares": 10, "entry": 0.15}]
    fairs = {("win", "Spain"): 0.151}                       # converged (~flat)
    prices = {("win", "Spain"): 0.15}
    plan = A.plan_rebalance(legs, fairs, prices, candidates=[], cost=0.01, buffer=BUF)
    assert plan["hold"] and not plan["close"]               # no paid early exit to sit in cash


def test_cut_always_closes_as_stop_loss():
    legs = [{"level": "win", "team": "Spain", "shares": 10, "entry": 0.15}]
    fairs = {("win", "Spain"): 0.05}                        # model now hates it -> cut
    prices = {("win", "Spain"): 0.15}
    plan = A.plan_rebalance(legs, fairs, prices, candidates=[], cost=0.01, buffer=BUF)
    assert [c["reason"] for c in plan["close"]] == [A.CUT]
    assert not plan["open"]                                 # no candidate -> go to cash


def test_redeploy_is_same_side_dollar_neutral():
    legs = [{"level": "win", "team": "Spain", "shares": 10, "entry": 0.15}]   # a LONG
    fairs = {("win", "Spain"): 0.03}; prices = {("win", "Spain"): 0.15}       # cut
    cands = [{"level": "win", "team": "Brazil", "side": "SHORT", "edge": 0.20, "price": 0.60},
             {"level": "win", "team": "England", "side": "LONG", "edge": 0.05, "price": 0.09}]
    plan = A.plan_rebalance(legs, fairs, prices, cands, cost=0.01, buffer=BUF)
    assert len(plan["open"]) == 1
    assert plan["open"][0]["team"] == "England" and plan["open"][0]["side"] == "LONG"  # not the bigger short


def test_rotate_only_for_a_clearly_better_same_side_edge():
    legs = [{"level": "win", "team": "Spain", "shares": 10, "entry": 0.15}]
    fairs = {("win", "Spain"): 0.30}; prices = {("win", "Spain"): 0.15}       # held edge 0.15
    marginal = [{"level": "win", "team": "England", "side": "LONG", "edge": 0.16, "price": 0.10}]
    assert A.plan_rebalance(legs, fairs, prices, marginal, 0.01, BUF)["hold"]   # 0.16-0.15 < 0.03 -> hold
    big = [{"level": "win", "team": "England", "side": "LONG", "edge": 0.20, "price": 0.10}]
    plan = A.plan_rebalance(legs, fairs, prices, big, 0.01, BUF)
    assert [c["reason"] for c in plan["close"]] == [A.ROTATE]


def test_apply_is_noop_when_prices_equal_entries():
    live = [{"level": "win", "team": "Spain", "shares": 10.0, "entry": 0.15, "status": "open", "realized": None}]
    fairs = {("win", "Spain"): 0.25}; prices = {("win", "Spain"): 0.15}
    new, summ = A.apply_rebalance(live, fairs, prices, candidates=[], cost=0.01, buffer=BUF, date="2026-06-28")
    assert summ == {"closed": 0, "opened": 0, "held": 1}
    assert new == live                                      # append-only ledger untouched


def test_apply_rotates_append_only_and_sizes_to_freed_capital():
    live = [{"level": "win", "team": "Spain", "shares": 10.0, "entry": 0.15, "status": "open", "realized": None}]
    fairs = {("win", "Spain"): 0.151}; prices = {("win", "Spain"): 0.15}       # converged
    cands = [{"level": "win", "team": "England", "side": "LONG", "edge": 0.08, "price": 0.10}]
    new, summ = A.apply_rebalance(live, fairs, prices, cands, cost=0.01, buffer=BUF, date="2026-06-28")
    assert summ == {"closed": 1, "opened": 1, "held": 0}
    spain = next(r for r in new if r["team"] == "Spain")
    assert spain["status"] == "closed" and spain["close_reason"] == A.ROTATE
    eng = next(r for r in new if r["team"] == "England")
    # freed capital = |10|*0.15 = 1.5; at 0.10 entry -> 15 shares, long
    assert eng["status"] == "open" and eng["entry"] == 0.10 and eng["shares"] == 15.0
