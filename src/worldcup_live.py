"""
worldcup_live — model vs market, updated as matches progress
==============================================================================
Ties the three pieces together for the 2026 World Cup:
  market  : Polymarket world-cup-winner -> market-implied title probabilities
  model   : worldcup_sim Monte Carlo seeded from those probs -> model-implied probs
  compare : DISLOCATION = model - market (where the bracket draw and the market disagree)

As matches are played, feed scores to the Tournament (worldcup_sim): Elo ratings and
group rank tables update and forecast() re-simulates only the unplayed matches, so both
the probabilities and the substitution structure refresh live.

NOTE: GROUPS_2026 below is the official Final Draw (5 Dec 2025). Both the team SETS and the
within-group POSITION ORDER (slot 1/2/3/4) are verified against the per-group FIFA/Wikipedia
standings tables ("2026 FIFA World Cup Group A".."L"); the position order drives the fixture
schedule, so it must be the official draw slot, not just the right four teams.
"""
import unicodedata

import numpy as np
import pandas as pd

import worldcup_sim as W

# 12 groups of 4 — 2026 Final Draw, in official slot order (position 1/2/3/4 per FIFA).
GROUPS_2026 = {
    "A": ["Mexico", "South Africa", "South Korea", "Czechia"],
    "B": ["Canada", "Bosnia-Herzegovina", "Qatar", "Switzerland"],
    "C": ["Brazil", "Morocco", "Haiti", "Scotland"],
    "D": ["USA", "Paraguay", "Australia", "Türkiye"],
    "E": ["Germany", "Curaçao", "Ivory Coast", "Ecuador"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cape Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "Iraq", "Norway"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "DR Congo", "Uzbekistan", "Colombia"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}
HOSTS = {"USA", "Canada", "Mexico"}
FIELD = [t for ts in GROUPS_2026.values() for t in ts]


def _norm(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace(" ", "").replace("-", "")
    return {"drcongo": "congodr"}.get(s, s)            # market spells it "Congo DR"


def load_market_probs(panel_path="data/cache/worldcup.parquet"):
    """Market-implied title probabilities for the 48-team field (last price, renormalized)."""
    panel = pd.read_parquet(panel_path)
    last = {}
    for col in panel.columns:
        team = col.replace("Will ", "").replace(" win the 2026 FIFA World Cup?", "").strip()
        v = panel[col].ffill().iloc[-1]
        if pd.notna(v):
            last[_norm(team)] = float(v)
    probs = {t: last.get(_norm(t), 0.002) for t in FIELD}   # field teams only
    s = sum(probs.values())
    return {t: p / s for t, p in probs.items()}


def _seed_ratings(market_probs, scale, host_bonus):
    ratings = W.ratings_from_probs(market_probs, scale=scale)
    for h in HOSTS:
        ratings[h] = ratings.get(h, 1500.0) + host_bonus
    return ratings


def calibrate_scale(market_probs, scales=(250, 300, 350, 400, 450, 500, 550),
                    n_sims=3000, host_bonus=60.0):
    """Pick the rating SCALE whose no-result simulation best reproduces the market's
    title-probability spread. This calibrates away the seeding artifact, so any residual
    per-team gap (model - market) is the BRACKET-PATH effect (easy/hard draw), not an
    arbitrary rating scale. Returns (best_scale, sse-in-logprob)."""
    best = (None, np.inf)
    for sc in scales:
        ratings = _seed_ratings(market_probs, sc, host_bonus)
        fc = W.monte_carlo(GROUPS_2026, ratings, n_sims, seed=0, qualify=2, n_best_third=8)
        err = sum((np.log(max(fc[t]["title"], 1e-4)) - np.log(max(market_probs[t], 1e-4))) ** 2
                  for t in FIELD)
        if err < best[1]:
            best = (sc, err)
    return best


def build_tournament(market_probs=None, host_bonus=60.0, scale=None):
    """Tournament seeded from market-implied probs (scale auto-calibrated unless given),
    with a host rating bonus. Pass your own `ratings` to W.Tournament for an INDEPENDENT
    model (then dislocation is a genuine edge, not just bracket-path)."""
    if market_probs is None:
        market_probs = load_market_probs()
    if scale is None:
        scale, _ = calibrate_scale(market_probs, host_bonus=host_bonus)
    ratings = _seed_ratings(market_probs, scale, host_bonus)
    return W.Tournament(GROUPS_2026, ratings), market_probs, scale


def model_substitution(probs, top=10):
    """Model-implied substitution from the multinomial title structure: for one-hot
    title outcomes, corr(1_i, 1_j) = -sqrt(p_i p_j / ((1-p_i)(1-p_j))). The biggest
    favorites are the strongest substitutes (they compete for the same crown)."""
    teams = list(probs)
    out = []
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            pi, pj = probs[teams[i]], probs[teams[j]]
            r = -np.sqrt(pi * pj / max((1 - pi) * (1 - pj), 1e-9))
            out.append((teams[i], teams[j], round(float(r), 3)))
    out.sort(key=lambda e: e[2])
    return out[:top]


def run_report(n_sims=8000, seed=0):
    T, market, scale = build_tournament()
    fc = T.forecast(n_sims=n_sims, seed=seed, qualify=2, n_best_third=8)
    model = {t: fc[t]["title"] for t in FIELD}

    rows = sorted(FIELD, key=lambda t: model[t], reverse=True)
    print("=" * 72)
    print("WORLD CUP 2026 — MODEL vs MARKET (title probability)")
    print(f"market-seeded, scale calibrated to {scale} so the model matches the market's")
    print(f"overall spread; residual dislocation = BRACKET-PATH (group difficulty), not edge.")
    print(f"{n_sims} sims; host bonus on {', '.join(sorted(HOSTS))}")
    print("=" * 72)
    print(f"{'team':16} {'market':>7} {'model':>7} {'disloc':>8}  advance")
    for t in rows[:14]:
        d = model[t] - market[t]
        print(f"{t:16} {market[t]*100:6.1f}% {model[t]*100:6.1f}% {d*100:+7.1f}%  {fc[t]['advance']*100:5.1f}%")

    disloc = sorted(FIELD, key=lambda t: model[t] - market[t])
    print("\nMost UNDER-priced by market (model >> market):")
    for t in [x for x in disloc[::-1] if model[x] - market[x] > 0][:5]:
        print(f"   {t:16} market {market[t]*100:4.1f}%  model {model[t]*100:4.1f}%  ({(model[t]-market[t])*100:+.1f}%)")
    print("Most OVER-priced by market (model << market):")
    for t in [x for x in disloc if model[x] - market[x] < 0][:5]:
        print(f"   {t:16} market {market[t]*100:4.1f}%  model {model[t]*100:4.1f}%  ({(model[t]-market[t])*100:+.1f}%)")

    print("\nMODEL-implied substitution (who competes for the crown), top pairs:")
    for a, b, r in model_substitution(model, top=6):
        print(f"   {r:+.2f}   {a} <-> {b}")
    print("(compare to MARKET substitution from relationships.run_real: England<->France -0.31)")
    print("=" * 72)
    return dict(market=market, model=model, forecast=fc)


if __name__ == "__main__":
    run_report()
