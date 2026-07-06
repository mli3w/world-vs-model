"""
worldcup_fundamental.py — the INDEPENDENT fundamental model (Elo) vs the market
==============================================================================
The complement to the zero-knowledge structural book. Instead of deriving a view FROM the
market's prices, this runs the engine's own fundamental simulation (`worldcup_sim`: Elo +
Poisson goals + the verified group/knockout bracket) on REAL, disclosed per-team ratings —
**not** seeded from Polymarket. So it can disagree with the market in a way the structural
model (which is pinned to market prices) never can.

INPUTS (both disclosed, both independent of the betting market):
  - TEAM_ELO  : World Football Elo (eloratings.net, via the Wikipedia data module), as of
                ELO_AS_OF. Real per-team ratings — reproducible, dated, swappable.
  - SHRINK    : raw match-Elo (the 400-pt scale) OVER-concentrates the favorite when compounded
                through the KNOCKOUT (the top team's title prob balloons to ~30%). A single-
                elimination bracket is far higher-variance than the match-Elo implies, so we apply
                a KNOCKOUT-ONLY shrink toward the field mean (KO_SHRINK) — the favorite lands at a
                historically-plausible ~18%. The GROUP stage keeps (near-)raw Elo (a 3-game round-
                robin doesn't over-compound). Both shrinks are DISCLOSED PRIORS from football
                history — NOT calibrated to the market (that would just re-price it).
                NOTE: this does NOT erase the model's group-stage disagreements with the market
                (e.g. raw Elo rating Panama 2nd in its group) — those are REAL, not artifacts.

HONEST FRAMING (read this): a model built on PUBLIC ratings is usually LESS sharp than a
liquid, heavily-traded market. So big model-vs-market disagreements are *more* likely the
model being cruder than the crowd being wrong — "big disagreement != edge". The value is an
honest, transparent second opinion that the live scorecard adjudicates. Research/education only.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np                  # noqa: E402
import worldcup_sim as W            # noqa: E402  (the independent fundamental engine)
import worldcup_markets as WM       # noqa: E402  (LADDER levels/slots)
import wc_bracket as WB             # noqa: E402  (the official 2026 knockout slot table)
from worldcup_live import GROUPS_2026, _norm   # noqa: E402  (verified Final Draw)

ELO_SOURCE = "World Football Elo Ratings (eloratings.net)"
ELO_SOURCE_URL = "https://www.eloratings.net/2026_World_Cup"
ELO_REF_URL = "https://en.wikipedia.org/wiki/World_Football_Elo_Ratings"
ELO_AS_OF = "2026-06-01"
GROUP_SHRINK = 1.0   # group stage: trust Elo as-is (a 3-game round-robin doesn't over-compound)
KO_SHRINK = 0.6      # knockout: single-elimination is far coin-flippier than match-Elo -> flatten
SHRINK = KO_SHRINK   # the headline knob shown on the board (the knockout shrink)

# 2026 is co-hosted by the USA, Canada and Mexico; hosts play most games at home. Home advantage in
# recent international football is worth ~+60 Elo (an expected score ~0.59 vs an equal side). A flat
# disclosed bonus is a deliberate approximation (not every host game is strictly at home).
HOSTS = {"USA", "Canada", "Mexico"}
HOST_BONUS = 60      # Elo points added to each host (disclosed prior, NOT fit to the market)

# Parameter (rating) uncertainty. A public Elo number is a point estimate of an uncertain true
# strength; international ratings carry roughly this much noise. We integrate over it in the Monte
# Carlo so the output reflects FORECAST uncertainty, not just bracket coin-flips (without it the
# favorite reads ~100% to advance and minnows ~0% — falsely precise). Disclosed, NOT market-tuned.
RATING_SD = 70.0     # Elo std-dev of true-strength uncertainty, applied per-simulation

# The per-trade cost (half-spread) used to net displayed edges lives in worldcup_markets
# (WM.HALF_SPREAD / WM.net_edge) so both books share one disclosed number.

# Real per-team World Football Elo (eloratings.net via the Wikipedia data module, 2026-06-01).
TEAM_ELO = {
    "Spain": 2165, "Argentina": 2113, "France": 2081, "England": 2020, "Brazil": 1988,
    "Portugal": 1984, "Colombia": 1977, "Netherlands": 1961, "Ecuador": 1935, "Croatia": 1930,
    "Germany": 1925, "Norway": 1917, "Türkiye": 1906, "Japan": 1906, "Switzerland": 1894,
    "Uruguay": 1892, "Mexico": 1868, "Belgium": 1866, "Senegal": 1866, "Paraguay": 1833,
    "Austria": 1830, "Morocco": 1822, "Canada": 1793, "Australia": 1775, "Scotland": 1770,
    "Iran": 1764, "South Korea": 1756, "Algeria": 1743, "Czechia": 1733, "USA": 1733,
    "Panama": 1733, "Uzbekistan": 1718, "Sweden": 1714, "Egypt": 1699, "Jordan": 1685,
    "Ivory Coast": 1676, "DR Congo": 1655, "Tunisia": 1633, "Iraq": 1608, "Bosnia-Herzegovina": 1591,
    "New Zealand": 1585, "Cape Verde": 1576, "Saudi Arabia": 1566, "Haiti": 1532, "South Africa": 1517,
    "Ghana": 1503, "Curaçao": 1433, "Qatar": 1423,
}


RESULTS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "ledger", "wc_results.json")


def load_results(path=RESULTS_PATH):
    """The played-match ledger (list of {a, b, ga, gb, stage}), or None if absent/empty. Shared by
    the share-image generators so they re-forecast off the SAME live results the board reads."""
    try:
        with open(path) as f:
            return json.load(f) or None
    except (OSError, ValueError):
        return None


def _host_base():
    """Base ratings = real Elo + the host bonus for the three co-hosts (pre-shrink, pre-results)."""
    return {t: e + (HOST_BONUS if t in HOSTS else 0.0) for t, e in TEAM_ELO.items()}


def ratings(shrink=SHRINK, host_bonus=HOST_BONUS, base=None):
    """The disclosed model input: ratings shrunk toward the field mean by `shrink`. Returns
    {team: elo}. shrink=1 is the raw base (over-concentrated); shrink<1 flattens for tournament odds.
    `base` defaults to real Elo + host bonus; a caller can pass a results-updated base (live re-
    forecast). The shrink is applied to whatever `base` is given."""
    src = base if base is not None else {t: e + (host_bonus if t in HOSTS else 0.0)
                                         for t, e in TEAM_ELO.items()}
    mean = sum(src.values()) / len(src)
    return {t: mean + shrink * (e - mean) for t, e in src.items()}


def apply_results(results):
    """Fold PLAYED matches into the model (live re-forecast). Returns (base_ratings, known_group_
    scores): every result Elo-updates both teams (so the knockout uses current form), and GROUP
    matches also condition the group standings so completed results are held fixed, not re-simulated.
    `results` is an iterable of dicts {a, b, ga, gb, stage?} (stage defaults to 'group'). Knockout
    results update ratings but bracket conditioning past the group stage is not yet modelled."""
    base, known = _host_base(), {}
    for r in results or []:
        a, b, ga, gb = r["a"], r["b"], int(r["ga"]), int(r["gb"])
        if a in base and b in base:
            base[a], base[b] = W.elo_update(base[a], base[b], ga, gb)
        if r.get("stage", "group") == "group":
            known[frozenset((a, b))] = {a: ga, b: gb}
    return base, known


def _slot_seats(ranked, third_groups):
    """Real final standings poured into the OFFICIAL Round-of-32 slot table -> the 32 qualifiers in
    bracket (top-to-bottom) order, or None if the best-third contingency can't be resolved."""
    assign = WB.THIRD_ASSIGN.get("".join(sorted(third_groups)))
    if not assign:
        return None

    def team_for(slot):
        kind, who = slot
        if kind == "W":
            return ranked[who][0]
        if kind == "R":
            return ranked[who][1]
        return ranked[assign[WB.COLS.index(who)]][2]

    seats = []
    for _m, a, b in WB.R32:
        seats += [team_for(a), team_for(b)]
    return seats


def _conditioned_forecast(groups, base, results, n_sims, seed, ko_shrink, rating_sd, top_finals):
    """The live knockout forecast once the group stage is DECIDED. Instead of re-simulating the
    tournament from scratch (which keeps handing probability to teams that are already out), it seeds
    the REAL final standings into the official FIFA slot table, advances the ACTUAL winner of every
    knockout tie already played, and samples only the UNPLAYED ties by the (shrunk, results-updated)
    Elo model. So an eliminated team gets exactly the depth it truly reached and zero beyond it, and
    the survivors' odds reflect who is really left. Returns raw display-name dicts
    (levels, depth, champions, finals), or None if the bracket can't be filled (falls back to the
    from-scratch Monte Carlo)."""
    import collections
    ranked, table = WB.group_table(groups, results)
    seats = _slot_seats(ranked, WB.best_third_groups(ranked, table))
    if seats is None:
        return None
    played = WB.ko_winners(results)
    eliminated = set()                                       # teams knocked out (must not advance again)
    for pair, w in played.items():
        eliminated |= set(pair) - {w}
    ko_base = ratings(ko_shrink, base=base)
    teams = [t for ts in groups.values() for t in ts]
    seat_set = set(seats)
    rounds = len(seats).bit_length() - 1                     # 5 for a 32-team bracket
    levels = ("advance", "reach_R16", "reach_QF", "reach_SF", "reach_F", "win")
    cnt = {lv: {t: 0 for t in teams} for lv in levels}
    depth = {t: [0] * (rounds + 2) for t in teams}           # exit-round buckets: group + R32..champ
    champ_cnt = {t: 0 for t in teams}
    finals_cnt = collections.Counter()
    rng = np.random.default_rng(seed)
    for _ in range(n_sims):
        r_k = ({t: ko_base[t] + rng.normal(0.0, rating_sd) for t in ko_base}
               if rating_sd else ko_base)
        alive, wins = list(seats), {t: 0 for t in seats}
        while len(alive) > 1:
            nxt = []
            for i in range(0, len(alive), 2):
                a, b = alive[i], alive[i + 1]
                w = played.get(frozenset((a, b)))            # a decided tie advances the real winner
                if w not in (a, b):
                    if a in eliminated and b not in eliminated:      # already out (lost elsewhere)
                        w = b
                    elif b in eliminated and a not in eliminated:
                        w = a
                    else:
                        w = a if rng.random() < W.expected_score(r_k[a], r_k[b]) else b
                wins[w] += 1
                nxt.append(w)
            alive = nxt
        champ = alive[0]
        for t in seat_set:
            cnt["advance"][t] += 1
        for t, wv in wins.items():
            if wv >= 1: cnt["reach_R16"][t] += 1
            if wv >= 2: cnt["reach_QF"][t] += 1
            if wv >= 3: cnt["reach_SF"][t] += 1
            if wv >= 4: cnt["reach_F"][t] += 1
        cnt["win"][champ] += 1
        for t in teams:
            depth[t][0 if t not in seat_set else min(wins.get(t, 0), rounds) + 1] += 1
        champ_cnt[champ] += 1
        runner = next((t for t, wv in wins.items() if wv == rounds - 1 and t != champ), None)
        if runner is not None:
            finals_cnt[tuple(sorted((champ, runner)))] += 1
    return (
        {lv: {t: cnt[lv][t] / n_sims for t in teams} for lv in levels},
        {t: [c / n_sims for c in depth[t]] for t in teams},
        {t: champ_cnt[t] / n_sims for t in teams},
        [(a, b, c / n_sims) for (a, b), c in finals_cnt.most_common(top_finals)],
    )


def fundamental_ladder(groups=None, n_sims=20000, seed=0, group_shrink=GROUP_SHRINK,
                       ko_shrink=KO_SHRINK, rating_sd=RATING_SD, results=None):
    """Independent model-implied probability of reaching each ladder level, keyed by the
    NORMALIZED team name (so it aligns with the market ladder from worldcup_markets). The
    group stage uses `group_shrink` ratings, the knockout the flatter `ko_shrink` ratings.
    `rating_sd` adds per-simulation rating uncertainty (see worldcup_sim.monte_carlo_ladder).
    `results` (played matches) re-forecasts live: ratings update by Elo and completed group games
    are held fixed. Once the group stage is DECIDED, the knockout is conditioned on played results
    (see _conditioned_forecast) so eliminated teams stop drawing probability. With results=None this
    is identical to the pre-tournament forecast."""
    groups = groups or GROUPS_2026
    base, known = apply_results(results)
    if results and WB.groups_complete(groups, results):
        cond = _conditioned_forecast(groups, base, results, n_sims, seed, ko_shrink, rating_sd, 8)
        if cond is not None:
            return {lvl: {_norm(t): p for t, p in d.items()} for lvl, d in cond[0].items()}
    L = W.monte_carlo_ladder(groups, ratings(group_shrink, base=base), n_sims=n_sims,
                             seed=seed, qualify=2, n_best_third=8,    # 2026 format: top-2 + 8 thirds
                             ko_ratings=ratings(ko_shrink, base=base),
                             known=known or None, rating_sd=rating_sd)
    return {lvl: {_norm(t): p for t, p in d.items()} for lvl, d in L.items()}


def group_positions(groups=None, n_sims=20000, seed=0, group_shrink=GROUP_SHRINK,
                    rating_sd=RATING_SD, results=None):
    """Per-team probability of finishing 1st/2nd/3rd/4th in its group (the group stage trusts raw
    Elo, same as the ladder). Keyed by NORMALIZED team name. Returns {team: [p1, p2, p3, p4]}.
    `results` conditions the standings on completed group games (live re-forecast)."""
    base, known = apply_results(results)
    pos = W.monte_carlo_positions(groups or GROUPS_2026, ratings(group_shrink, base=base),
                                  n_sims=n_sims, seed=seed, known=known or None, rating_sd=rating_sd)
    return {_norm(t): p for t, p in pos.items()}


def fundamental_paths(groups=None, n_sims=20000, seed=0, group_shrink=GROUP_SHRINK,
                      ko_shrink=KO_SHRINK, rating_sd=RATING_SD, results=None, top_finals=8):
    """Joint-path outcomes from the same engine as fundamental_ladder: each team's EXIT-round
    distribution (`depth`), the champion distribution (`champions`), and the most-likely FINAL
    pairings (`finals`). Keyed by NORMALIZED team names so it aligns with the board's ladder.
    `results` re-forecasts live (same conditioning as fundamental_ladder: once the groups are
    decided the knockout paths honour played results, so eliminated teams exit where they truly
    did)."""
    groups = groups or GROUPS_2026
    base, known = apply_results(results)
    if results and WB.groups_complete(groups, results):
        cond = _conditioned_forecast(groups, base, results, n_sims, seed, ko_shrink, rating_sd,
                                     top_finals)
        if cond is not None:
            _lv, depth, champions, finals = cond
            return dict(
                depth={_norm(t): v for t, v in depth.items()},
                champions={_norm(t): v for t, v in champions.items()},
                finals=[(_norm(a), _norm(b), p) for a, b, p in finals],
            )
    P = W.monte_carlo_paths(groups, ratings(group_shrink, base=base), n_sims=n_sims,
                            seed=seed, qualify=2, n_best_third=8,
                            ko_ratings=ratings(ko_shrink, base=base),
                            known=known or None, rating_sd=rating_sd, top_finals=top_finals)
    return dict(
        depth={_norm(t): v for t, v in P["depth"].items()},
        champions={_norm(t): v for t, v in P["champions"].items()},
        finals=[(_norm(a), _norm(b), p) for a, b, p in P["finals"]],
    )


def book_rows(market_ladder, model=None, n_sims=20000, seed=0, cost=0.0):
    """Per-(level, team) rows in worldcup_markets.book() format. `ours` is the FUNDAMENTAL model
    probability; `gross` = model - DE-VIGGED market (apples-to-apples probabilities, so the
    bookmaker's margin doesn't contaminate the comparison); `edge` is that gross edge net of the
    `cost` half-spread (default 0 = gross, so estimator callers see the pure signal; the board
    passes WM.HALF_SPREAD for display, so an edge below the spread reports ~0 — not worth trading);
    `price` is the raw market price you'd pay. Sorted by edge (shorts first)."""
    model = model or fundamental_ladder(n_sims=n_sims, seed=seed)
    rows = []
    for lvl, _slug, slots in WM.LADDER:
        prices = market_ladder.get(lvl, {})
        dv, mp = _devig(prices, slots), model.get(lvl, {})
        for t, price in prices.items():
            ours = mp.get(t)
            if ours is None:
                continue
            gross = round(ours - dv.get(t, float(price)), 4)
            rows.append(dict(level=lvl, team=t, price=round(float(price), 4), ours=round(ours, 4),
                             gross=gross, edge=WM.net_edge(gross, cost) if cost else gross))
    return sorted(rows, key=lambda r: r["edge"])


def _devig(prices, slots):
    s = sum(prices.values()) or 1.0
    return {t: p / s * slots for t, p in prices.items()}


def disagreements(market_ladder, level="win", model=None, top=10, **kw):
    """The biggest fundamental-model-vs-market gaps at a level, comparing the model to the
    DE-VIGGED market (apples-to-apples probabilities). Returns [(team, model, market, edge)]."""
    model = model or fundamental_ladder(**kw)
    slots = dict((lvl, s) for lvl, _g, s in WM.LADDER)[level]
    mkt = _devig(market_ladder.get(level, {}), slots)
    mp = model.get(level, {})
    rows = [(t, mp[t], mkt[t], mp[t] - mkt[t]) for t in mkt if t in mp]
    return sorted(rows, key=lambda r: -abs(r[3]))[:top]


if __name__ == "__main__":
    fl = fundamental_ladder(n_sims=20000)
    disp = {_norm(t): t for t in TEAM_ELO}
    print(f"INDEPENDENT fundamental model — {ELO_SOURCE} as of {ELO_AS_OF}, shrink={SHRINK}")
    print("(research/education only; a public-ratings model is usually less sharp than the market)\n")
    print("top title probabilities:")
    for n in sorted(fl["win"], key=lambda n: -fl["win"][n])[:12]:
        print(f"   {fl['win'][n]*100:5.1f}%  {disp.get(n, n):16}  (advance {fl['advance'][n]*100:3.0f}%)")
