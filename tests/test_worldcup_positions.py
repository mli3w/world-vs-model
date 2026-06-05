"""Tests for the paper positions + PnL tracker (src/worldcup_positions.py) — data-free."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
WP = pytest.importorskip("worldcup_positions")

LADDER = {"win": {"fav": 0.40, "dog": 0.02}, "reach_F": {}, "reach_SF": {},
          "reach_QF": {}, "advance": {}}


def test_enter_mark_resolve_pnl(tmp_path):
    path = str(tmp_path / "pos.jsonl")
    WP.enter("win", "fav", 10, 0.40, path=path)        # long the favorite
    WP.enter("win", "dog", -10, 0.02, path=path)       # short the longshot
    m = WP.mark(LADDER, path=path)
    assert m["n_open"] == 2 and m["unrealized"] == 0.0  # marked at entry == current
    n = WP.resolve("win", {"fav": 1, "dog": 0}, path=path)
    assert n == 2
    m2 = WP.mark(LADDER, path=path)
    assert m2["n_open"] == 0
    # fav: 10*(1-0.40)=+6.0 ; dog short: -10*(0-0.02)=+0.2 ; total +6.2
    assert abs(m2["realized"] - 6.2) < 1e-6


def test_suggest_book_is_dollar_neutral():
    ladder = {"win": {"a": 0.50, "b": 0.30, "c": 0.05, "d": 0.02},
              "reach_F": {}, "reach_SF": {}, "reach_QF": {}, "advance": {}}
    sug = WP.suggest_book(ladder, power=1.3, gross=10.0, top=2)
    longs = [s for s in sug if s["side"] == "long"]
    shorts = [s for s in sug if s["side"] == "short"]
    assert longs and shorts
    ln = sum(abs(s["shares"] * s["price"]) for s in longs)
    sn = sum(abs(s["shares"] * s["price"]) for s in shorts)
    assert abs(ln - 5.0) < 1.0 and abs(sn - 5.0) < 1.0   # each side ~ gross/2


def test_post_renders_with_stubbed_scan(tmp_path):
    scan_res = dict(
        levels={k: dict(sum=s, slots=sl, overround_pct=round((s/sl-1)*100, 1), n=1)
                for (k, _slug, sl), s in zip(WP.WM.LADDER, [31.8, 8.5, 4.5, 2.49, 1.03])},
        nested=[("japan", "reach_SF", "reach_F", 0.05, 0.065, 0.015)],
        continent={}, book=[dict(level="win", team="France", price=0.17, ours=0.19, edge=0.02),
                            dict(level="advance", team="Qatar", price=0.27, ours=0.23, edge=-0.04)])
    md = WP.world_vs_model_post(scan_res=scan_res, path=str(tmp_path / "none.jsonl"))
    assert "what the world thinks vs what the model thinks" in md
    assert "France" in md and "Qatar" in md and "japan" in md.lower()
    assert "+24.5%" in md                                 # the reach-final overround headline
