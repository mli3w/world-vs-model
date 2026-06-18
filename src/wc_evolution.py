"""
wc_evolution.py — "as it unfolds": forecast moves + surprise ranking (dormant until results)
============================================================================================
The bracket scorecard freezes a *pre-tournament* call. This module is the live companion: once
games are played it shows (a) how the model has **changed its mind** since kickoff and (b) the
**biggest shocks** so far, with who — model or market — saw them coming. Both stay empty until
results land, so the panel is dormant pre-tournament.

Pure functions over plain dicts/lists so they're trivially testable; the board does the I/O.

  surprisal(p)  = −log2(p) in bits — how astonished a forecaster who said `p` should be when the
                  event happens. A 50/50 that lands is 1 bit; a 1-in-8 that lands is 3 bits.

Research/education only.
"""
import math

EPS = 1e-9


def surprisal(p):
    """Bits of surprise for an event a forecaster gave probability `p` (clamped)."""
    return -math.log2(min(max(p, EPS), 1 - EPS))


def forecast_moves(frozen, live, top=6, min_delta=0.02):
    """How far the live forecast has moved from the frozen (kickoff) one, per team.

    `frozen`/`live`: {team: probability} for one rung (e.g. 'win'). Returns the biggest movers
    (|Δ| ≥ min_delta), each {team, frozen, live, delta}, sorted by absolute move.
    """
    out = []
    for t, fp in frozen.items():
        if t in live:
            d = live[t] - fp
            if abs(d) >= min_delta:
                out.append(dict(team=t, frozen=fp, live=live[t], delta=d))
    out.sort(key=lambda r: -abs(r["delta"]))
    return out[:top]


def _elo_draw_rate(elo_diff, base=0.28, floor=0.06, scale=420.0):
    """Draw rate as a function of |Elo gap| (international football empirical).

    A flat 28% draw rate dramatically *understates* how shocking a draw is when the favourite is
    massively rated above the underdog — Spain (~2160) vs Cape Verde (~1580) draws far less than
    28% of the time in practice, because Spain scores enough to convert the draw into a win in
    most games where they don't lose. So as the Elo gap widens, the prior draw probability should
    fall off, asymptoting to a small floor (≈6%) for huge mismatches. The Gaussian decay around
    a ~420-Elo scale is calibrated so that: gap=0→28%, gap=200→24%, gap=400→15%, gap=600→9%.
    """
    return floor + (base - floor) * math.exp(-(abs(elo_diff) / scale) ** 2)


def match_upsets(results, ratings, prices=None, top=6, min_bits=0.8):
    """Rank played MATCHES by how surprising the result was.

    `results`: list of {a, b, ga, gb} (team names + final scoreline).
    `ratings`: dict team_name -> Elo rating. Pre-match Elo prior:
                P(A wins | no draw) = 1 / (1 + 10^((Elo_b − Elo_a)/400)),
              with a strength-aware draw rate (see `_elo_draw_rate`) — bigger Elo gap → lower
              draw probability — and the rest split by Elo.
    `prices` : optional dict {(a_lc, b_lc): (pa, pd, pb)} of pre-match POLYMARKET prices.
              When a match's pair is in the dict, that overrides the Elo prior and the upset is
              tagged with source="polymarket"; otherwise we fall back to Elo. `(a_lc, b_lc)` is
              the lowercase, alphabetised pair tuple.
    """
    prices = prices or {}
    out = []
    for r in results:
        a, b = r.get("a"), r.get("b")
        ra, rb = ratings.get(a), ratings.get(b)
        try:
            ga, gb = int(r.get("ga")), int(r.get("gb"))
        except (TypeError, ValueError):
            continue
        # Prefer Polymarket pre-match prices if we have them; else fall back to Elo.
        key = tuple(sorted([(a or "").lower(), (b or "").lower()]))
        pm = prices.get(key)
        if pm is not None and a and b:
            # Stored as (pa, pd, pb) with a in alphabetical order — re-orient to the result row's a/b
            stored_a, stored_b = key                           # alphabetical
            spa, spd, spb = pm
            if (a or "").lower() == stored_a:
                pa, pd, pb = spa, spd, spb
            else:
                pa, pd, pb = spb, spd, spa
            source = "polymarket"
        elif ra is not None and rb is not None:
            pa_nd = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
            dr = _elo_draw_rate(ra - rb)
            pa = pa_nd * (1 - dr)
            pb = (1 - pa_nd) * (1 - dr)
            pd = dr
            source = "elo"
        else:
            continue                                          # no prior for this match at all

        if ga > gb:
            kind, prob, winner = "A_win", pa, a
        elif gb > ga:
            kind, prob, winner = "B_win", pb, b
        else:
            kind, prob, winner = "draw", pd, None
        bits = surprisal(prob)
        if bits < min_bits:
            continue
        out.append(dict(a=a, b=b, ga=ga, gb=gb, winner=winner, kind=kind,
                        pa=round(pa, 4), pb=round(pb, 4), pd=round(pd, 4),
                        actual_prob=round(prob, 4), bits=round(bits, 2),
                        source=source, stage=r.get("stage", "group")))
    out.sort(key=lambda x: -x["bits"])
    return out[:top]


def surprises(resolved, top=6, min_bits=1.3):
    """Rank resolved outcomes by how astonishing they were (to model & market together).

    `resolved`: list of {level, team, model, market, outcome} where outcome ∈ {0,1} and model /
    market are the *frozen* probabilities that the team reaches that rung. An **upset** is a team
    that got there against the odds (outcome 1, low prob); a **flop** is a favourite that didn't
    (outcome 0, high prob). `called_better` is whoever was *less* surprised (the sharper forecast).
    Returns the top shocks above `min_bits` of combined surprise.
    """
    out = []
    for r in resolved:
        o, mp, kp = r.get("outcome"), r.get("model"), r.get("market")
        if o is None or mp is None:
            continue
        kp = mp if kp is None else kp                          # fall back to model if no market base
        ms = surprisal(mp if o == 1 else 1 - mp)
        ks = surprisal(kp if o == 1 else 1 - kp)
        combined = (ms + ks) / 2
        if combined < min_bits:
            continue
        out.append(dict(level=r["level"], team=r["team"], outcome=int(o),
                        kind=("upset" if o == 1 else "flop"),
                        model=mp, market=kp, model_bits=round(ms, 2), market_bits=round(ks, 2),
                        combined=round(combined, 2),
                        called_better=("model" if ms < ks - 1e-9 else
                                       "market" if ks < ms - 1e-9 else "tie")))
    out.sort(key=lambda r: -r["combined"])
    return out[:top]
