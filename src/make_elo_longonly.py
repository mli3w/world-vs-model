"""
make_elo_longonly.py — a hypothetical "follow the probable path" Elo book
=========================================================================
The tracked Elo book (ledger/wc_elo_core.jsonl) sizes positions by |model − market|
edge and takes both LONGs and SHORTs. That construction bled ~-$372: edge-sizing
loads up on longshot LONGs (huge *relative* edge, tiny absolute probability) and
SHORTs teams the model's own bracket actually favours.

This freezes a SIMPLER, more standard alternative from the SAME frozen day-0 Elo
forecast — no look-ahead:

  • LONG only. No shorts. (Back the teams the model likes; don't fade anyone.)
  • Rank-gated: at each rung, long the top-K teams by Elo probability
    (reach_QF→8, reach_SF→4, reach_F→2, win→2). This is "follow the most
    probable bracket path."
  • Conviction-weighted: stake ∝ Elo probability, scaled to a $1,000 paper bankroll.
  • Half-spread cost baked into the entry (you pay the ask), same as the tracked books.

DATA / PROVENANCE (honest):
  • Day-0 Elo probabilities: WF.fundamental_ladder(results=None) — the exact
    pre-tournament projection, reproducible, zero look-ahead.
  • Day-0 market prices: the frozen entry prices in the tracked Elo book where it
    took a position. For the top favourites the tracked book did NOT trade (Spain,
    France, Netherlands at QF; Spain at SF; Spain/Argentina at F/win), we use the
    Elo probability as the market proxy — justified because "no trade" means the
    model-vs-market gap was smaller than the half-spread, i.e. market ≈ model there.
    This proxy is disclosed in each such position's note.

    python src/make_elo_longonly.py [--bankroll 1000] [--force]

Writes ledger/wc_elo_longonly.jsonl (positions status="open"; auto_resolve.py settles
them alongside the other books). Idempotent unless --force.

Research/education only.
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import worldcup_fundamental as WF                            # noqa: E402
import worldcup_markets as WM                                # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ELO_CORE = os.path.join(ROOT, "ledger", "wc_elo_core.jsonl")
OUT = os.path.join(ROOT, "ledger", "wc_elo_longonly.jsonl")
DAY0 = "2026-06-05"                                           # the day-0 registration date

# Rank-gate K per rung = number of slots (win uses 2 so the runner-up finalist is included).
SLOTS = {"reach_QF": 8, "reach_SF": 4, "reach_F": 2, "win": 2}


def build(bankroll=1000.0, cost=None, out=OUT, force=False):
    if os.path.exists(out) and not force:
        print(f"[longonly] {out} exists — immutable (use --force to rebuild)")
        return 0
    cost = WM.HALF_SPREAD if cost is None else cost

    # Day-0 Elo forecast (pre-tournament, no results).
    fund = WF.fundamental_ladder(n_sims=20000, seed=0, results=None)
    # Frozen day-0 market prices from the tracked Elo book (teams it traded).
    tracked = [json.loads(l) for l in open(ELO_CORE, encoding="utf-8") if l.strip()]
    entries = {(r["level"], r["team"]): r["entry"] for r in tracked}

    picks = []                                               # (level, team, prob, market, proxied)
    for level, k in SLOTS.items():
        ranked = sorted(fund.get(level, {}).items(), key=lambda x: -x[1])[:k]
        for team, prob in ranked:
            mkt = entries.get((level, team))
            proxied = mkt is None
            if proxied:
                mkt = prob                                   # no trade ⟹ market ≈ model
            picks.append((level, team, prob, mkt, proxied))

    total_prob = sum(p for _l, _t, p, _m, _x in picks) or 1.0
    rows = []
    for level, team, prob, mkt, proxied in picks:
        stake = bankroll * prob / total_prob
        eff_entry = min(mkt + cost, 0.999)                   # pay the ask
        shares = round(stake / eff_entry, 1)
        src = "market≈model proxy" if proxied else "frozen day-0 market"
        rows.append(dict(
            id=f"{level}:{team}:{DAY0}", level=level, team=team,
            shares=shares, entry=round(eff_entry, 4), date=DAY0,
            note=f"day-0 Elo long-only · rank top-{SLOTS[level]} · conv ∝ p={prob:.2f} · {src}",
            status="open", realized=None))

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    gross = sum(abs(r["shares"] * r["entry"]) for r in rows)
    print(f"[longonly] froze {len(rows)} LONG positions (gross ${gross:.0f}) -> {out}")
    for r in rows:
        print(f"    LONG {r['level']:9s} {r['team']:14s} @ {r['entry']*100:>5.1f}%")
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Freeze the hypothetical Elo long-only book")
    ap.add_argument("--bankroll", type=float, default=1000.0)
    ap.add_argument("--force", action="store_true", help="rebuild even if the ledger exists")
    a = ap.parse_args(argv)
    build(bankroll=a.bankroll, force=a.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
