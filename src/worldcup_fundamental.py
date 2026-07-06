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
import worldcup_sim as W            # noqa: E402  (the independent fundamental engine)
import worldcup_markets as WM       # noqa: E402  (LADDER levels/slots)
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


def fundamental_ladder(groups=None, n_sims=20000, seed=0, group_shrink=GROUP_SHRINK,
                       ko_shrink=KO_SHRINK, rating_sd=RATING_SD, results=None):
    """Independent model-implied probability of reaching each ladder level, keyed by the
    NORMALIZED team name (so it aligns with the market ladder from worldcup_markets). The
    group stage uses `group_shrink` ratings, the knockout the flatter `ko_shrink` ratings.
    `rating_sd` adds per-simulation rating uncertainty (see worldcup_sim.monte_carlo_ladder).
    `results` (played matches) re-forecasts live: ratings update by Elo and completed group games
    are held fixed. With results=None this is identical to the pre-tournament forecast."""
    base, known = apply_results(results)
    L = W.monte_carlo_ladder(groups or GROUPS_2026, ratings(group_shrink, base=base), n_sims=n_sims,
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
    `results` re-forecasts live (same conditioning as fundamental_ladder)."""
    base, known = apply_results(results)
    P = W.monte_carlo_paths(groups or GROUPS_2026, ratings(group_shrink, base=base), n_sims=n_sims,
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
