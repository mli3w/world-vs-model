"""
wc_active.py — the Active book's rotation rules (sell / realize / switch), cost-gated
=====================================================================================
The Buy & Hold book enters once at day 0 and never trades again. The **Active** book is
re-evaluated daily and rotates — but only when the move clears its costs. This module is the
explicit rule set, kept pure and testable so the difference between the two books is auditable.

Every leg holds SIGNED YES-shares (long > 0, short < 0) entered at a price. Let

    fair      = the model's current fair probability for that outcome
    price     = the current market price
    aligned   = (fair - price) * sign(shares)     (> 0 ⇒ the position is still favourable)
    buffer    = the per-trade cost gate (one half-spread); a round trip costs ~2·buffer

Diagnostic state for one leg (the `buffer` band gives **hysteresis** so we don't whipsaw a leg
that wobbles around fair, paying the spread each way):

    HOLD         aligned >  buffer           the gap that justified the trade is still open
    TAKE_PROFIT  −buffer ≤ aligned ≤ buffer   converged to fair — the edge has played out
    CUT          aligned < −buffer            decisively against us — the thesis is broken

What we actually *do* with those states (two deliberate design choices that keep churn low):

  * **CUT → close now (stop-loss).** Holding a leg the model now thinks loses just realises a
    bigger loss at settlement, so we exit early even though it costs a spread.
  * **TAKE_PROFIT → ride it to its (free) resolution, NOT a paid early exit.** A converged leg
    has ~zero edge left; closing it just pays a spread to sit in cash. We only close a converged
    (or still-favourable) leg early to **rotate** into a clearly better edge — never to bank a
    profit that settlement will pay us for free.
  * **ROTATE** a held leg for a candidate only when the improvement beats the round trip:
    edge_cand − aligned_held > 2·cost + buffer.

Capital discipline: freed capital is redeployed into a **same-side** candidate (a freed long is
replaced by a long, a short by a short), so the book stays dollar-neutral by construction.

Research/education only — paper book, no capital invested.
"""

HOLD, TAKE_PROFIT, CUT, ROTATE = "hold", "take_profit", "cut", "rotate"


def aligned_edge(shares, fair, price):
    """Signed edge in the direction of the position (>0 = still favourable)."""
    return (fair - price) * (1.0 if shares >= 0 else -1.0)


def side_of(shares):
    return "LONG" if shares >= 0 else "SHORT"


def classify_leg(leg, fair, price, buffer):
    """Diagnostic state HOLD / TAKE_PROFIT / CUT for one leg (with the ±buffer hysteresis band)."""
    a = aligned_edge(leg["shares"], fair, price)
    if a < -buffer:
        return CUT
    if a <= buffer:
        return TAKE_PROFIT
    return HOLD


def should_rotate(edge_held, edge_cand, cost, buffer):
    """Swap a held leg for a candidate only if the improvement beats the round-trip cost.

    `edge_held`/`edge_cand` are the *aligned* (favourable, ≥0) edges. A round trip (close the old
    leg, open the new one) costs ~2·cost; the buffer keeps us from churning on noise.
    """
    return (edge_cand - edge_held) > (2.0 * cost + buffer)


def plan_rebalance(open_legs, fairs, prices, candidates, cost, buffer):
    """Produce a rebalance plan from the rules. Pure: no I/O, no PnL side effects.

    open_legs   : [{level, team, shares, entry}, ...]
    fairs       : {(level, team): fair_prob}            the model's current fair
    prices      : {(level, team): market_price}         current market
    candidates  : [{level, team, side, edge, price}]    fresh favourable edges (edge>0), `side`
                  is "LONG"/"SHORT"; excludes outcomes already held.
    cost, buffer: the half-spread and the cost gate.

    Returns dict(close=[...], open=[...], hold=[...]). Each `open` carries `funds` = the (level,
    team) of the leg whose freed capital it takes, so the apply step can size it dollar-for-dollar.
    """
    held = {(l["level"], l["team"]) for l in open_legs}
    pools = {"LONG": [], "SHORT": []}
    for c in candidates:
        if (c["level"], c["team"]) in held:
            continue
        pools.setdefault(c.get("side", "LONG"), []).append(c)
    for s in pools:
        pools[s].sort(key=lambda c: -abs(c["edge"]))
    used = {"LONG": 0, "SHORT": 0}
    close, hold, opens = [], [], []

    def _take(side, leg):
        """Pop the best unused same-side candidate; record an open funded by `leg`."""
        if used[side] < len(pools[side]):
            c = pools[side][used[side]]
            used[side] += 1
            opens.append(dict(level=c["level"], team=c["team"], side=side, edge=abs(c["edge"]),
                              entry=prices.get((c["level"], c["team"]), c.get("price")),
                              funds=(leg["level"], leg["team"])))
            return True
        return False

    for leg in open_legs:
        k = (leg["level"], leg["team"])
        fair, price = fairs.get(k), prices.get(k)
        if fair is None or price is None:
            hold.append(leg)
            continue
        a = aligned_edge(leg["shares"], fair, price)
        side = side_of(leg["shares"])
        if classify_leg(leg, fair, price, buffer) == CUT:        # stop-loss: always exit
            close.append({**leg, "reason": CUT, "exit": price})
            _take(side, leg)
            continue
        # HOLD or converged: only leave early to rotate into a clearly better same-side edge
        held_edge = max(a, 0.0)
        nxt = pools[side][used[side]] if used[side] < len(pools[side]) else None
        if nxt and should_rotate(held_edge, abs(nxt["edge"]), cost, buffer):
            close.append({**leg, "reason": ROTATE, "exit": price})
            _take(side, leg)
        else:
            hold.append(leg)
    return dict(close=close, open=opens, hold=hold)


def _stake_of(row):
    """Capital at risk of a leg = |shares| · cost-per-share at entry."""
    cps = row["entry"] if row["shares"] >= 0 else (1 - row["entry"])
    return abs(row["shares"]) * cps


def apply_rebalance(live_rows, fairs, prices, candidates, cost, buffer, date):
    """Turn a rebalance plan into APPEND-ONLY ledger rows (the audit trail stays intact).

    Closes (cut / rotate) flip a leg to status='closed' with realized PnL at the exit price; each
    freed leg funds one same-side 'rotate-in' leg, sized to the same capital at risk. Returns
    (new_rows, summary). Pre-tournament, with prices ≈ entries, every leg HOLDs → a no-op.
    """
    open_legs = [r for r in live_rows if r.get("status") == "open"]
    plan = plan_rebalance(open_legs, fairs, prices, candidates, cost, buffer)
    closed = {(c["level"], c["team"]): c["reason"] for c in plan["close"]}
    stake_by_key = {(r["level"], r["team"]): _stake_of(r) for r in open_legs}
    out = []
    for r in live_rows:
        k = (r["level"], r["team"])
        if r.get("status") == "open" and k in closed:
            exit_p = prices.get(k, r["entry"])
            out.append({**r, "status": "closed", "realized": round(r["shares"] * (exit_p - r["entry"]), 4),
                        "resolved_at": date, "exit": round(exit_p, 4), "close_reason": closed[k]})
        else:
            out.append(r)
    for o in plan["open"]:
        stake = stake_by_key.get(o.get("funds"), 0.0)
        sgn = 1 if o["side"] == "LONG" else -1
        entry = o["entry"]
        cps = entry if sgn > 0 else (1 - entry)
        out.append(dict(id=f"{o['level']}:{o['team']}:{date}", level=o["level"], team=o["team"],
                        shares=round(stake / max(cps, 1e-3) * sgn, 4), entry=round(entry, 4),
                        date=date, note=f"rotate-in · edge {o['edge']:+.3f}", status="open", realized=None))
    return out, dict(closed=len(plan["close"]), opened=len(plan["open"]), held=len(plan["hold"]))
