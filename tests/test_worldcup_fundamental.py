"""Tests for the independent fundamental model (src/worldcup_fundamental.py)."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
F = pytest.importorskip("worldcup_fundamental")
WL = pytest.importorskip("worldcup_live")


def test_team_elo_covers_the_field():
    missing = [t for t in WL.FIELD if t not in F.TEAM_ELO]
    assert missing == [] and len(F.TEAM_ELO) == 48


def test_shrink_flattens_spread_but_keeps_order():
    raw = F.TEAM_ELO
    sh = F.ratings(shrink=0.6)
    top = max(raw, key=raw.get)
    assert max(sh, key=sh.get) == top                                  # favorite unchanged
    assert (max(sh.values()) - min(sh.values())) < (max(raw.values()) - min(raw.values()))


def test_fundamental_ladder_nested_normalized_and_sane_favorite():
    L = F.fundamental_ladder(n_sims=3000, seed=0)
    assert set(L) == {"advance", "reach_R16", "reach_QF", "reach_SF", "reach_F", "win"}
    spain = WL._norm("Spain")
    assert spain in L["win"]                                            # normalized keys (market-aligned)
    for t in L["win"]:                                                  # nested per team
        assert L["advance"][t] >= L["reach_QF"][t] >= L["reach_SF"][t] >= L["reach_F"][t] >= L["win"][t] - 1e-9
    assert abs(sum(L["win"].values()) - 1) < 1e-6                       # win sums to 1 slot
    assert abs(sum(L["advance"].values()) - 32) < 1e-6                  # 32 advance
    assert L["win"][spain] == max(L["win"].values())                   # Spain the model favorite
    assert 0.10 < L["win"][spain] < 0.28                               # shrink keeps it plausible


def test_group_positions_are_normalized_and_sum_to_one():
    pos = F.group_positions(n_sims=1500, seed=0)
    assert WL._norm("Spain") in pos and len(pos) == 48           # normalized keys, whole field
    for t, p in pos.items():
        assert abs(sum(p) - 1.0) < 1e-9 and len(p) == 4          # finishes 1st..4th somewhere


def test_live_results_reforecast_conditions_on_played_games():
    """Folding in played group results moves the forecast: a team that wins all 3 jumps to ~certain
    to advance, and with no results the path is identical to the pre-tournament forecast."""
    teams = WL.GROUPS_2026["A"]
    winner, others = teams[3], [t for t in teams if t != teams[3]]   # the weakest team sweeps
    res = [dict(a=winner, b=o, ga=3, gb=0) for o in others]
    base = F.fundamental_ladder(n_sims=3000, seed=0)
    live = F.fundamental_ladder(n_sims=3000, seed=0, results=res)
    n = WL._norm(winner)
    assert live["advance"][n] > base["advance"][n] + 0.10            # sweeping lifts advance
    assert live["advance"][n] > 0.98                                 # won the group -> through
    assert F.fundamental_ladder(n_sims=1500, seed=0, results=None)["advance"][n] == \
        F.fundamental_ladder(n_sims=1500, seed=0)["advance"][n]      # results=None == default


def _full_group_results():
    """A complete, decisive set of group results: within each group the listed order sweeps (team i
    beats every later team). So the group ranking is exactly GROUPS_2026's listing order."""
    res = []
    for teams in WL.GROUPS_2026.values():
        for i, a in enumerate(teams):
            for b in teams[i + 1:]:
                res.append(dict(a=a, b=b, ga=2, gb=0, stage="group"))
    return res


def test_conditioned_forecast_activates_only_when_groups_complete_and_stays_normalized():
    res = _full_group_results()
    L = F.fundamental_ladder(n_sims=1500, seed=0, results=res)
    assert set(L) == {"advance", "reach_R16", "reach_QF", "reach_SF", "reach_F", "win"}
    assert abs(sum(L["win"].values()) - 1) < 1e-6           # one champion
    assert abs(sum(L["advance"].values()) - 32) < 1e-6      # 32 qualifiers advance
    for t in L["win"]:                                       # nested per team
        assert L["advance"][t] >= L["reach_QF"][t] >= L["reach_SF"][t] >= L["reach_F"][t] >= L["win"][t] - 1e-9
    # a 4th-placed team (didn't qualify) can never reach the knockouts
    dead = WL._norm(next(iter(WL.GROUPS_2026.values()))[3])
    assert L["advance"][dead] == 0.0


def test_conditioned_forecast_honours_played_knockout_results():
    """A team recorded as losing a knockout tie exits there: zero probability beyond that round,
    while its conqueror carries its win through."""
    res = _full_group_results()
    base = F.fundamental_ladder(n_sims=1500, seed=0, results=res)
    # find a real Round-of-32 tie from the seeded bracket, then record the underdog winning it.
    import wc_bracket as WB
    ranked, table = WB.group_table(WL.GROUPS_2026, res)
    seats = F._slot_seats(ranked, WB.best_third_groups(ranked, table))
    a, b = seats[0], seats[1]                                # the top R32 tie
    fav = a if base["reach_R16"].get(WL._norm(a), 0) >= base["reach_R16"].get(WL._norm(b), 0) else b
    dog = b if fav == a else a
    res2 = res + [dict(a=fav, b=dog, ga=0, gb=1, stage="ko")]   # record the underdog winning the tie
    live = F.fundamental_ladder(n_sims=1500, seed=0, results=res2)
    nf, nd = WL._norm(fav), WL._norm(dog)
    assert live["reach_R16"][nf] == 0.0 and live["reach_QF"][nf] == 0.0   # the favourite is out
    assert live["win"][nf] == 0.0
    assert live["reach_R16"][nd] == 1.0                                   # the underdog is through
    base = F.ratings(shrink=1.0, host_bonus=0)
    boosted = F.ratings(shrink=1.0)                                  # default HOST_BONUS
    for h in ("USA", "Canada", "Mexico"):
        assert boosted[h] > base[h] + 50                            # hosts get the home bump
    assert abs(boosted["Spain"] - base["Spain"]) < 1e-9             # a non-host is unchanged


def test_cost_netting_shrinks_edges_toward_zero():
    L = F.fundamental_ladder(n_sims=3000, seed=0)
    mkt = {"win": {WL._norm("Spain"): 0.40, WL._norm("France"): 0.05, WL._norm("Brazil"): 0.55}}
    gross = {r["team"]: r for r in F.book_rows(mkt, model=L, cost=0.0)}
    net = {r["team"]: r for r in F.book_rows(mkt, model=L, cost=0.02)}
    for t in gross:
        assert abs(net[t]["edge"]) <= abs(gross[t]["edge"]) + 1e-9   # never grows
        assert gross[t]["gross"] == net[t]["gross"]                  # the raw signal is preserved


def test_book_rows_are_two_sided_vs_a_market():
    L = F.fundamental_ladder(n_sims=3000, seed=0)
    # a market summing ~to its slot (so de-vig ~ raw); model disagrees on both sides.
    mkt = {"win": {WL._norm("Spain"): 0.40, WL._norm("France"): 0.05, WL._norm("Brazil"): 0.55}}
    rows = F.book_rows(mkt, model=L)
    edges = {r["team"]: r["edge"] for r in rows}
    assert edges[WL._norm("Spain")] < 0                                # model ~19% << 40% -> fade
    assert edges[WL._norm("France")] > 0                               # model ~9% > 5% -> buy


def test_fundamental_paths_keys_are_normalized_and_consistent():
    """fundamental_paths returns the joint-path outcomes keyed by normalized names, with the
    champion distribution matching fundamental_ladder's win marginals."""
    P = F.fundamental_paths(n_sims=2000, seed=0)
    L = F.fundamental_ladder(n_sims=2000, seed=0)
    assert WL._norm("Spain") in P["champions"] and WL._norm("Spain") in P["depth"]
    assert abs(sum(P["champions"].values()) - 1.0) < 1e-9
    for t, d in P["depth"].items():
        assert abs(sum(d) - 1.0) < 1e-9                       # exit-round distribution per team
    # same engine -> champion distribution tracks the ladder's win level (within Monte-Carlo noise).
    for t, p in P["champions"].items():
        assert abs(p - L["win"].get(t, 0.0)) < 0.03
    # finals are normalized name pairs with a probability, most-likely first.
    a, b, prob = P["finals"][0]
    assert a == WL._norm(a) and b == WL._norm(b) and 0 < prob <= 1.0
