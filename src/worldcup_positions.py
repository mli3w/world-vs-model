"""
worldcup_positions.py — paper positions, PnL, and the "world vs model" post
==============================================================================
A transparent PAPER portfolio over the World Cup markets so everyone can follow the bets,
the tweaks, and the running PnL. No real capital — this is a published research track record.

Model (binary outcome markets, prices in [0,1]):
  a position holds SIGNED YES-shares (long > 0, short < 0) entered at a price.
  unrealized PnL = shares * (current_price - entry_price)
  realized   PnL = shares * (outcome{0,1} - entry_price)   when the market settles
Dollar-neutral sizing: longs and shorts each get half the gross budget, weighted by edge.

Persisted append-only to ledger/wc_positions.jsonl so daily tweaks accrue into a history.

⚠ Research/education only — not financial advice, not a solicitation, no capital invested.
"""
import os
import sys
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import worldcup_markets as WM       # noqa: E402

POS_PATH = os.path.join("ledger", "wc_positions.jsonl")


def load(path=POS_PATH):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def _save(rows, path=POS_PATH):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def enter(level, team, shares, price, date=None, note="", path=POS_PATH):
    """Open (or tweak via a new line) a paper position: SIGNED YES-shares at `price`."""
    rows = load(path)
    rows.append(dict(id=f"{level}:{team}:{date or dt.date.today().isoformat()}:{len(rows)}",
                     level=level, team=team, shares=round(float(shares), 4),
                     entry=round(float(price), 4), date=date or dt.date.today().isoformat(),
                     note=note, status="open", realized=None))
    _save(rows, path)
    return rows[-1]


def suggest_book(ladder, power=1.15, gross=10.0, top=12):
    """Turn the model's mispricings into a dollar-neutral suggested book: long the most
    underpriced, short the most overpriced, sized by |edge|, each side = gross/2."""
    bk = WM.book(ladder, power=power)
    longs = [r for r in bk if r["edge"] > 0][::-1][:top]
    shorts = [r for r in bk if r["edge"] < 0][:top]
    out = []
    for side, rows in (("long", longs), ("short", shorts)):
        w = sum(abs(r["edge"]) for r in rows) or 1.0
        for r in rows:
            notional = (gross / 2) * abs(r["edge"]) / w
            shares = notional / max(r["price"], 1e-3) * (1 if side == "long" else -1)
            out.append(dict(level=r["level"], team=r["team"], side=side,
                            shares=round(shares, 3), price=r["price"], edge=r["edge"]))
    return out


def enter_book(ladder=None, power=1.15, gross=10.0, top=12, date=None, path=POS_PATH):
    """Enter the suggested book as paper positions (fetches the live ladder if none given)."""
    ladder = ladder or WM.fetch_ladder()
    sug = suggest_book(ladder, power=power, gross=gross, top=top)
    for s in sug:
        enter(s["level"], s["team"], s["shares"], s["price"], date=date,
              note=f"model {s['side']} edge {s['edge']:+.3f}", path=path)
    return sug


def mark(ladder, path=POS_PATH):
    """Mark every open position to the live ladder. Returns per-position + totals."""
    rows = [r for r in load(path) if r["status"] == "open"]
    marks, unreal, gross = [], 0.0, 0.0
    for r in rows:
        cur = ladder.get(r["level"], {}).get(r["team"])
        if cur is None:
            continue
        pnl = r["shares"] * (cur - r["entry"])
        unreal += pnl
        gross += abs(r["shares"] * cur)
        marks.append(dict(level=r["level"], team=r["team"], shares=r["shares"],
                          entry=r["entry"], cur=round(cur, 4), unreal=round(pnl, 4)))
    realized = sum(r["realized"] for r in load(path)
                   if r["status"] == "resolved" and r.get("realized") is not None)
    return dict(marks=sorted(marks, key=lambda m: m["unreal"]),
                unrealized=round(unreal, 4), realized=round(realized, 4),
                total=round(unreal + realized, 4), gross_exposure=round(gross, 4),
                n_open=len(marks))


def resolve(level, outcomes, path=POS_PATH):
    """Settle open positions at `level` against {team: 0/1}. Realizes PnL and closes them."""
    rows = load(path)
    n = 0
    for r in rows:
        if r["status"] != "open" or r["level"] != level:
            continue
        y = outcomes.get(r["team"])
        if y is None:
            continue
        r["realized"] = round(r["shares"] * (float(y) - r["entry"]), 4)
        r["status"] = "resolved"
        r["resolved_at"] = dt.date.today().isoformat()
        n += 1
    _save(rows, path)
    return n


def world_vs_model_post(scan_res=None, power=1.15, path=POS_PATH):
    """A shareable markdown post: what the WORLD (market) thinks vs what the MODEL thinks,
    the structural arbs, and the running paper PnL. Pure structure, no football knowledge."""
    scan_res = scan_res or WM.scan(power=power, verbose=False)
    bk = scan_res["book"]
    longs = [r for r in bk if r["edge"] > 0][::-1][:5]
    shorts = [r for r in bk if r["edge"] < 0][:5]
    lvl = scan_res["levels"]
    m = mark(WM.fetch_ladder(), path) if os.path.exists(path) else None
    L = ["# World Cup 2026 — what the world thinks vs what the model thinks",
         "*Zero football knowledge — only the market's own prices + structure (de-vig, "
         "favorite-longshot, bracket coherence).*", ""]
    L += ["## The model's bets (vs the price you'd pay)",
          "**Underpriced (we'd buy):** " +
          ", ".join(f"{r['team']} {r['level']} ({r['edge']*100:+.1f}%)" for r in longs),
          "", "**Overpriced (we'd fade):** " +
          ", ".join(f"{r['team']} {r['level']} ({r['edge']*100:+.1f}%)" for r in shorts), ""]
    L += ["## The market's hidden vig (prices should sum to the slots)",
          "| round | sums to | should be | overround |", "| --- | --- | --- | --- |"]
    for k, _s, slots in WM.LADDER:
        d = lvl[k]
        L.append(f"| {k} | {d['sum']} | {slots} | **{d['overround_pct']:+.1f}%** |")
    if scan_res["nested"]:
        L += ["", "## Riskless inconsistencies the market is pricing"]
        for t, sh, dp, sp, dpp, gap in scan_res["nested"][:3]:
            L.append(f"- **{t}**: priced to {dp} ({dpp}) *more* than to {sh} ({sp}) — impossible.")
    if m:
        L += ["", "## Running paper PnL (no real capital)",
              f"- open positions: {m['n_open']} · gross {m['gross_exposure']:.1f} · "
              f"unrealized **{m['unrealized']:+.3f}** · realized **{m['realized']:+.3f}** · "
              f"total **{m['total']:+.3f}**"]
    L += ["", "> ⚠️ Research/education only — not financial advice, not a solicitation, no "
          "capital invested. Backtests/paper trades are simulations, not returns."]
    return "\n".join(L)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="World Cup paper positions + post (research only)")
    ap.add_argument("cmd", nargs="?", default="post",
                    choices=["post", "enter", "mark"],
                    help="post = world-vs-model markdown; enter = open the model book as paper "
                         "positions; mark = mark the book to live prices")
    ap.add_argument("--gross", type=float, default=10.0)
    ap.add_argument("--power", type=float, default=1.15)
    a = ap.parse_args(argv)
    if a.cmd == "post":
        print(world_vs_model_post(power=a.power))
    elif a.cmd == "enter":
        sug = enter_book(power=a.power, gross=a.gross)
        print(f"[positions] entered {len(sug)} paper positions (gross {a.gross}) -> {POS_PATH}")
    elif a.cmd == "mark":
        mm = mark(WM.fetch_ladder())
        print(f"[positions] {mm['n_open']} open · unrealized {mm['unrealized']:+.3f} · "
              f"realized {mm['realized']:+.3f} · total {mm['total']:+.3f}")


if __name__ == "__main__":
    main()
