"""
wc_active.py — the Active book's rotation rules (sell / realize / switch), cost-gated
=====================================================================================
The Buy & Hold book enters once at day 0 and never trades again. The **Active** book is
re-evaluated daily and rotates — but only when the move clears its costs. This module is the
explicit rule set, kept pure and testable so the difference between the two books is auditable.

Every leg holds SIGNED YES-shares (long > 0, short < 0) entered at a price. Let

    fair      = the model's current fair probability for that outcome
    price     = the current market price
    edge      = fair - price                      (signed, in YES space)
    aligned   = edge * sign(shares)               (> 0 ⇒ the position is still favourable)
    buffer    = the per-trade cost gate (one half-spread); a round trip costs ~2·buffer

Decisions (each must clear the buffer, because churning the spread bleeds the edge):

  HOLD         aligned  >  buffer          the gap that justified the trade is still open
  TAKE_PROFIT  0 ≤ aligned ≤ buffer        price converged to fair — thesis played out, bank it
  CUT          aligned  <  0               edge flipped sign — the reason to hold is gone
  RESOLVED     the round happened          forced realization at the {0,1} outcome (handled in resolve)

Switching: freed capital (from TAKE_PROFIT / CUT / RESOLVED) is redeployed into the freshest
edges that clear the buffer. When capital is fully deployed, we **rotate** a held leg for a
candidate only if the improvement beats the round trip:  edge_cand − edge_held > 2·cost + buffer.

Research/education only — paper book, no capital invested.
"""

HOLD, TAKE_PROFIT, CUT = "hold", "take_profit", "cut"


def aligned_edge(shares, fair, price):
    """Signed edge in the direction of the position (>0 = still favourable)."""
    return (fair - price) * (1.0 if shares >= 0 else -1.0)


def classify_leg(leg, fair, price, buffer):
    """Decide HOLD / TAKE_PROFIT / CUT for one open leg given its current fair & price.

    `leg` needs at least {shares}. Returns one of the module constants.
    """
    a = aligned_edge(leg["shares"], fair, price)
    if a < 0:
        return CUT                      # thesis flipped — the model now disagrees with the position
    if a <= buffer:
        return TAKE_PROFIT              # converged to fair — no edge left worth the spread
    return HOLD                         # gap still open and bigger than the cost to trade it


def should_rotate(edge_held, edge_cand, cost, buffer):
    """Swap a held leg for a candidate only if the improvement beats the round-trip cost.

    `edge_held`/`edge_cand` are the *aligned* (favourable, ≥0) edges. A round trip (close the
    old leg, open the new one) costs ~2·cost; we add the buffer so we don't churn on noise.
    """
    return (edge_cand - edge_held) > (2.0 * cost + buffer)


def plan_rebalance(open_legs, fairs, prices, candidates, cost, buffer):
    """Produce a rebalance plan from the rules. Pure: no I/O, no PnL side effects.

    open_legs   : [{level, team, shares, entry}, ...]   (current open positions)
    fairs       : {(level, team): fair_prob}            (the model's current fair)
    prices      : {(level, team): market_price}         (current market)
    candidates  : [{level, team, edge, ...}, ...]       fresh edges (aligned/favourable, edge>0),
                  excluding outcomes already held; sorted best-first by the caller or here.
    cost, buffer: the half-spread and the cost gate.

    Returns dict(close=[...], open=[...], hold=[...]) where each close carries its reason. The
    caller turns this into ledger writes (realize at price, open new legs).
    """
    held_keys = {(l["level"], l["team"]) for l in open_legs}
    cands = sorted((c for c in candidates if (c["level"], c["team"]) not in held_keys),
                   key=lambda c: -abs(c["edge"]))

    close, hold = [], []
    for leg in open_legs:
        k = (leg["level"], leg["team"])
        fair, price = fairs.get(k), prices.get(k)
        if fair is None or price is None:
            hold.append(leg)
            continue
        decision = classify_leg(leg, fair, price, buffer)
        if decision == HOLD:
            # consider rotating this held leg for a clearly better candidate
            held_e = aligned_edge(leg["shares"], fair, price)
            if cands and should_rotate(held_e, abs(cands[0]["edge"]), cost, buffer):
                close.append({**leg, "reason": "rotate", "exit": price})
                # the freed slot is taken by the best candidate below
            else:
                hold.append(leg)
        else:
            close.append({**leg, "reason": decision, "exit": price})

    n_freed = len(close)                        # one freed slot per closed leg (equal-slot model)
    opens = [dict(level=c["level"], team=c["team"], edge=c["edge"],
                  entry=prices.get((c["level"], c["team"]), c.get("price")))
             for c in cands[:n_freed]]
    return dict(close=close, open=opens, hold=hold)


def _stake_of(row):
    """Capital at risk of a held leg = |shares| · cost-per-share at entry."""
    cps = row["entry"] if row["shares"] >= 0 else (1 - row["entry"])
    return abs(row["shares"]) * cps


def apply_rebalance(live_rows, fairs, prices, candidate_book, cost, buffer, date):
    """Turn a rebalance plan into APPEND-ONLY ledger rows (the audit trail stays intact).

    Closes (take-profit / cut / rotate) flip a leg to status='closed' with realized PnL at the exit
    price; each freed leg funds one new 'rotate-in' leg, sized to the same capital at risk. Returns
    (new_rows, summary). Pre-tournament, with prices ≈ entries, every leg HOLDs and this is a no-op.
    """
    open_legs = [r for r in live_rows if r.get("status") == "open"]
    plan = plan_rebalance(open_legs, fairs, prices, candidate_book, cost, buffer)
    closed = {(c["level"], c["team"]): c["reason"] for c in plan["close"]}
    out, freed_stakes = [], []
    for r in live_rows:
        k = (r["level"], r["team"])
        if r.get("status") == "open" and k in closed:
            exit_p = prices.get(k, r["entry"])
            freed_stakes.append(_stake_of(r))
            out.append({**r, "status": "closed", "realized": round(r["shares"] * (exit_p - r["entry"]), 4),
                        "resolved_at": date, "exit": round(exit_p, 4), "close_reason": closed[k]})
        else:
            out.append(r)
    for o, stake in zip(plan["open"], freed_stakes):
        side = 1 if o["edge"] >= 0 else -1
        entry = o["entry"]
        cps = entry if side > 0 else (1 - entry)
        out.append(dict(id=f"{o['level']}:{o['team']}:{date}", level=o["level"], team=o["team"],
                        shares=round(stake / max(cps, 1e-3) * side, 4), entry=round(entry, 4),
                        date=date, note=f"rotate-in · edge {o['edge']:+.3f}", status="open", realized=None))
    return out, dict(closed=len(plan["close"]), opened=len(plan["open"]), held=len(plan["hold"]))
