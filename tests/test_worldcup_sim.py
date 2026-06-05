"""Regression gate for the tournament simulator (src/worldcup_sim.py).

The bracket logic has analytic ground truth (single-elimination title prob = p**rounds)
and the Elo update is zero-sum — both are checked here, plus goals-model realism and
the live-update conditioning.

Run: python -m pytest -q
"""
import os
import sys

import pytest

np = pytest.importorskip("numpy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
W = pytest.importorskip("worldcup_sim")


def test_elo_update_is_zero_sum_and_directional():
    na, nb = W.elo_update(1600.0, 1500.0, 2, 1)
    assert abs((na - 1600.0) + (nb - 1500.0)) < 1e-9      # conserved
    assert na > 1600.0 and nb < 1500.0                    # winner gains, loser loses


def test_elo_upset_moves_more_than_expected_win():
    gain_expected = W.elo_update(1500, 1500, 1, 0)[0] - 1500
    gain_upset = W.elo_update(1300, 1700, 1, 0)[0] - 1300
    assert gain_upset > gain_expected


def test_knockout_title_prob_matches_analytic():
    """A super-team with per-match win prob p in a k-round single elim wins p**k."""
    rng = np.random.default_rng(0)
    p, k = 0.75, 3
    r_field = 1500.0
    r_super = r_field - 400.0 * np.log10(1.0 / p - 1.0)   # expected_score(super, field) = p
    field = [f"T{i}" for i in range(2 ** k - 1)]
    ratings = {t: r_field for t in field}
    ratings["SUPER"] = r_super
    seeds = ["SUPER"] + field
    n = 30000
    emp = sum(W.knockout_champion(seeds, ratings, rng) == "SUPER" for _ in range(n)) / n
    assert abs(emp - p ** k) < 0.02                       # ~5 SE


def test_knockout_run_reports_depth_as_p_to_the_k():
    """knockout_run returns wins per team; a super-team reaches round k with prob p**k."""
    rng = np.random.default_rng(3)
    p = 0.75
    r_field = 1500.0
    r_super = r_field - 400.0 * np.log10(1.0 / p - 1.0)
    field = [f"T{i}" for i in range(7)]
    ratings = {t: r_field for t in field}
    ratings["SUPER"] = r_super
    seeds = ["SUPER"] + field                                 # 8-team bracket, 3 rounds
    n = 30000
    reach = {1: 0, 2: 0, 3: 0}
    for _ in range(n):
        _champ, wins = W.knockout_run(seeds, ratings, rng)
        for k in reach:
            reach[k] += wins["SUPER"] >= k
    for k in (1, 2, 3):
        assert abs(reach[k] / n - p ** k) < 0.02


def test_monte_carlo_ladder_nested_and_sums_to_slots():
    groups = {chr(65 + i): [f"{chr(65+i)}{j}" for j in range(4)] for i in range(8)}
    rng = np.random.default_rng(1)
    ratings = {t: float(rng.normal(1500, 120)) for ts in groups.values() for t in ts}
    L = W.monte_carlo_ladder(groups, ratings, n_sims=4000, seed=1, qualify=2, n_best_third=0)
    for t in L["win"]:                                        # nested ordering holds per team
        assert (L["advance"][t] >= L["reach_QF"][t] >= L["reach_SF"][t]
                >= L["reach_F"][t] >= L["win"][t] - 1e-9)
    assert abs(sum(L["advance"].values()) - 16) < 1e-6        # 16-team knockout slot counts
    assert abs(sum(L["reach_F"].values()) - 2) < 1e-6
    assert abs(sum(L["win"].values()) - 1) < 1e-6


def test_group_positions_sum_to_one_and_rank_by_strength():
    groups = {"A": ["A1", "A2", "A3", "A4"]}
    ratings = {"A1": 1800, "A2": 1650, "A3": 1500, "A4": 1350}   # strictly decreasing strength
    pos = W.monte_carlo_positions(groups, ratings, n_sims=4000, seed=1)
    for t in ratings:
        assert abs(sum(pos[t]) - 1.0) < 1e-9                       # a team finishes somewhere
    assert pos["A1"][0] > pos["A2"][0] > pos["A3"][0] > pos["A4"][0]   # P(1st) tracks strength
    assert pos["A1"][0] > 0.4 and pos["A4"][3] > 0.4              # clear favorite/whipping-boy


def test_seed_order_protects_top_seeds():
    """Standard bracket seeding: each first-round pair sums to n+1, and seeds 1 & 2 sit in
    opposite halves (they can meet only in the final) — so no winner-vs-winner in round one."""
    for n in (4, 8, 16, 32):
        o = W._seed_order(n)
        assert sorted(o) == list(range(1, n + 1))             # a permutation of 1..n
        for i in range(0, n, 2):
            assert o[i] + o[i + 1] == n + 1                   # 1 v n, 2 v n-1, ...
        assert (o.index(1) < n // 2) != (o.index(2) < n // 2)  # 1 and 2 in opposite halves


def test_avoid_group_rematch_separates_same_group_pair():
    groups = {"A": ["A1", "A2"], "B": ["B1", "B2"]}
    out = W._avoid_group_rematch(["A1", "A2", "B1", "B2"], groups)   # A1 v A2 is a same-group pair
    gof = {t: g for g, ts in groups.items() for t in ts}
    for i in range(0, len(out), 2):
        assert gof[out[i]] != gof[out[i + 1]]                 # no same-group first-round pair


def test_rating_uncertainty_widens_the_forecast():
    """Per-sim rating jitter integrates over strength uncertainty: the favorite's title prob
    shrinks toward the field and a minnow's advance prob rises off the floor (less false precision)."""
    groups = {chr(65 + i): [f"{chr(65+i)}{j}" for j in range(4)] for i in range(8)}
    ratings = {t: 1500.0 for ts in groups.values() for t in ts}
    fav = "A0"; ratings[fav] = 1900.0; dog = "B0"; ratings[dog] = 1150.0
    sharp = W.monte_carlo_ladder(groups, ratings, n_sims=4000, seed=1, qualify=2, n_best_third=0)
    fuzzy = W.monte_carlo_ladder(groups, ratings, n_sims=4000, seed=1, qualify=2, n_best_third=0,
                                 rating_sd=150.0)
    assert fuzzy["win"][fav] < sharp["win"][fav]              # favorite pulled toward the field
    assert fuzzy["advance"][dog] > sharp["advance"][dog]      # minnow lifted off the floor


def test_goals_model_is_realistic():
    rng = np.random.default_rng(1)
    n = 5000
    tot = draws = 0
    for _ in range(n):
        ga, gb = W.match_goals(1500, 1500, rng)
        tot += ga + gb
        draws += (ga == gb)
    assert 2.3 < tot / n < 3.1                             # avg total goals
    assert 0.20 < draws / n < 0.34                         # draw rate


def test_results_condition_the_forecast():
    """Once a team wins its group decisively, its advance prob must be ~1."""
    groups = {"A": ["A1", "A2", "A3", "A4"], "B": ["B1", "B2", "B3", "B4"]}
    ratings = {t: 1500.0 for ts in groups.values() for t in ts}
    T = W.Tournament(groups, ratings)
    T.play("A1", "A2", 3, 0)
    T.play("A1", "A3", 2, 0)
    T.play("A1", "A4", 4, 0)
    T.play("A2", "A3", 1, 1)
    T.play("A2", "A4", 2, 0)
    T.play("A3", "A4", 1, 0)
    fc = T.forecast(n_sims=3000, seed=1)
    assert fc["A1"]["advance"] > 0.99                     # won group -> through
    assert fc["A4"]["advance"] < 0.01                     # lost all -> out
    table = T.rank_table("A")
    assert table[0]["team"] == "A1" and table[0]["Pts"] == 9
