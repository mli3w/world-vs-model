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


def test_classify_hold_take_cut():
    long_leg = {"shares": 10}
    # gap still wide open -> HOLD
    assert A.classify_leg(long_leg, fair=0.60, price=0.50, buffer=BUF) == A.HOLD
    # price converged to fair (within the buffer) -> TAKE_PROFIT
    assert A.classify_leg(long_leg, fair=0.505, price=0.50, buffer=BUF) == A.TAKE_PROFIT
    # model flipped: fair now below price -> CUT
    assert A.classify_leg(long_leg, fair=0.45, price=0.50, buffer=BUF) == A.CUT
    # symmetric for a short
    short_leg = {"shares": -10}
    assert A.classify_leg(short_leg, fair=0.40, price=0.50, buffer=BUF) == A.HOLD
    assert A.classify_leg(short_leg, fair=0.495, price=0.50, buffer=BUF) == A.TAKE_PROFIT
    assert A.classify_leg(short_leg, fair=0.55, price=0.50, buffer=BUF) == A.CUT


def test_should_rotate_needs_to_beat_round_trip():
    cost = 0.01
    # tiny improvement does not beat the ~2c round trip + buffer
    assert not A.should_rotate(edge_held=0.05, edge_cand=0.06, cost=cost, buffer=BUF)
    # a big improvement does
    assert A.should_rotate(edge_held=0.02, edge_cand=0.10, cost=cost, buffer=BUF)


def test_plan_closes_played_out_and_redeploys():
    legs = [
        {"level": "win", "team": "Spain", "shares": 10, "entry": 0.15},     # converged -> take_profit
        {"level": "win", "team": "Brazil", "shares": 10, "entry": 0.10},    # flipped  -> cut
        {"level": "win", "team": "France", "shares": 10, "entry": 0.12},    # still good -> hold
    ]
    fairs = {("win", "Spain"): 0.155, ("win", "Brazil"): 0.07, ("win", "France"): 0.20}
    prices = {("win", "Spain"): 0.15, ("win", "Brazil"): 0.10, ("win", "France"): 0.12}
    cands = [{"level": "win", "team": "England", "edge": 0.08, "price": 0.09},
             {"level": "win", "team": "Germany", "edge": 0.06, "price": 0.07}]
    plan = A.plan_rebalance(legs, fairs, prices, cands, cost=0.01, buffer=BUF)
    closed = {(c["team"], c["reason"]) for c in plan["close"]}
    assert ("Spain", A.TAKE_PROFIT) in closed
    assert ("Brazil", A.CUT) in closed
    assert {l["team"] for l in plan["hold"]} == {"France"}
    # two legs freed -> two best candidates opened
    assert [o["team"] for o in plan["open"]] == ["England", "Germany"]
    assert plan["open"][0]["entry"] == 0.09                  # opened at the current market price


def test_nothing_churns_when_all_legs_hold():
    legs = [{"level": "win", "team": "Spain", "shares": 10, "entry": 0.15}]
    fairs = {("win", "Spain"): 0.25}                          # still a fat edge
    prices = {("win", "Spain"): 0.15}
    cands = [{"level": "win", "team": "England", "edge": 0.16, "price": 0.10}]  # bigger, but...
    plan = A.plan_rebalance(legs, fairs, prices, cands, cost=0.01, buffer=BUF)
    # held edge is 0.10; candidate 0.16; improvement 0.06 > 2c+buf(0.03) -> rotate IS warranted
    assert any(c["reason"] == "rotate" for c in plan["close"])
    # but if the candidate is only marginally better, we hold
    plan2 = A.plan_rebalance(legs, fairs, prices,
                             [{"level": "win", "team": "England", "edge": 0.115, "price": 0.10}],
                             cost=0.01, buffer=BUF)
    assert plan2["hold"] and not plan2["close"]


def test_apply_is_noop_when_prices_equal_entries():
    # day-0 state: price == entry, so each leg's edge is still its original (wide) edge -> all HOLD
    live = [{"level": "win", "team": "Spain", "shares": 10.0, "entry": 0.15, "status": "open", "realized": None}]
    fairs = {("win", "Spain"): 0.25}                        # model fair well above price -> still good
    prices = {("win", "Spain"): 0.15}
    new, summ = A.apply_rebalance(live, fairs, prices, candidate_book=[], cost=0.01, buffer=BUF, date="2026-06-28")
    assert summ == {"closed": 0, "opened": 0, "held": 1}
    assert new == live                                      # append-only ledger untouched


def test_apply_closes_and_rotates_append_only():
    live = [{"level": "win", "team": "Spain", "shares": 10.0, "entry": 0.15, "status": "open", "realized": None}]
    fairs = {("win", "Spain"): 0.155}                       # converged to price -> take-profit
    prices = {("win", "Spain"): 0.15}
    cands = [{"level": "win", "team": "England", "edge": 0.08, "price": 0.10}]
    new, summ = A.apply_rebalance(live, fairs, prices, cands, cost=0.01, buffer=BUF, date="2026-06-28")
    assert summ == {"closed": 1, "opened": 1, "held": 0}
    spain = next(r for r in new if r["team"] == "Spain")
    assert spain["status"] == "closed" and spain["close_reason"] == A.TAKE_PROFIT
    eng = next(r for r in new if r["team"] == "England")
    assert eng["status"] == "open" and eng["entry"] == 0.10  # opened at the current market
