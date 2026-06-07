"""Tests for the knockout-bracket scorecard (src/worldcup_register.py::bracket_scorecard)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import worldcup_register as R  # noqa: E402


def _p(model, level, team, prob, market, outcome=None):
    return dict(date="2026-06-05", model=model, level=level, team=team,
                prob=prob, market=market, outcome=outcome)


def test_champions_read_pre_resolution():
    preds = [_p("elo", "win", "Spain", 0.30, 0.20), _p("elo", "win", "Brazil", 0.10, 0.28),
             _p("zero_knowledge", "win", "Spain", 0.25, 0.20),
             _p("zero_knowledge", "win", "Brazil", 0.12, 0.28)]
    card = R.bracket_scorecard(preds)
    assert card["champions"]["elo"] == "Spain"          # model's top pick
    assert card["champions"]["market"] == "Brazil"      # market's top pick (by the market column)
    assert card["points"] == {"market": 0, "zero_knowledge": 0, "elo": 0}   # nothing resolved yet
    assert card["n_resolved"] == 0


def test_points_award_round_weight_on_resolution():
    # win (slots 1, weight 32): actual champion = Spain
    preds = [_p("elo", "win", "Spain", 0.30, 0.20, outcome=1),
             _p("elo", "win", "Brazil", 0.10, 0.28, outcome=0),
             _p("zero_knowledge", "win", "Spain", 0.25, 0.20, outcome=1),
             _p("zero_knowledge", "win", "Brazil", 0.12, 0.28, outcome=0)]
    card = R.bracket_scorecard(preds)
    assert card["points"]["elo"] == 32                  # elo's top pick Spain won -> +32
    assert card["points"]["zero_knowledge"] == 32
    assert card["points"]["market"] == 0                # market's top pick was Brazil -> miss
    assert card["n_resolved"] == 1


def test_reach_level_counts_set_overlap():
    # reach_F (slots 2, weight 16): actual finalists = {Spain, France}
    rows = []
    for team, e, m, o in [("Spain", 0.6, 0.5, 1), ("France", 0.5, 0.45, 1),
                          ("Brazil", 0.4, 0.6, 0), ("England", 0.3, 0.3, 0)]:
        rows.append(_p("elo", "reach_F", team, e, m, outcome=o))
    card = R.bracket_scorecard(rows)
    f = next(r for r in card["levels"] if r["level"] == "reach_F")
    # elo's top-2 by prob = Spain, France == actual -> 2 hits * 16 = 32
    assert f["hits"]["elo"] == 2
    assert card["points"]["elo"] == 32
    # market's top-2 by market column = Brazil(0.6), Spain(0.5) -> 1 hit (Spain) * 16 = 16
    assert f["hits"]["market"] == 1
    assert card["points"]["market"] == 16
