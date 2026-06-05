"""
worldcup_register.py — stamp the public ledger (the falsifiable, out-of-sample track record)
============================================================================================
Snapshots, at one moment in time, BOTH models' forecasts and the de-vigged MARKET baseline for
every team, freezes the day-0 paper books, and writes an initial scorecard. The forecasts are
timestamped BEFORE the matches and scored later (Brier + skill-vs-market) by `resolve` as results
land — the credibility proof a skeptic can recompute.

Append-only and immutable: re-running on a NEW date adds a fresh dated snapshot (forecast
evolution); it never edits a past one. The board reads the scorecard (the credibility strip) and
the frozen books (the tracked PnL). The daily Pages rebuild does NOT re-register — a stamp is frozen.

Research/education only — not financial advice, not a solicitation, no capital invested.
"""
import os
import sys
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import worldcup_markets as WM       # noqa: E402
import worldcup_fundamental as WF   # noqa: E402
import worldcup_board as B          # noqa: E402  (the conviction-weighted sizing)
from worldcup_live import _norm     # noqa: E402

LEDGER = "ledger"
PRED = os.path.join(LEDGER, "predictions.jsonl")   # the falsifiable forecasts (the real record)
SCORE = os.path.join(LEDGER, "scorecard.json")     # the resolved summary the board's strip reads
CORE = os.path.join(LEDGER, "wc_core.jsonl")        # frozen zero-knowledge Buy & Hold book
LIVE = os.path.join(LEDGER, "wc_live.jsonl")        # frozen zero-knowledge Active book
ELO_CORE = os.path.join(LEDGER, "wc_elo_core.jsonl")  # frozen informed (Elo) Buy & Hold book
ELO_LIVE = os.path.join(LEDGER, "wc_elo_live.jsonl")  # frozen informed (Elo) Active book
CLAIM_LEVELS = ("advance", "win")                   # the levels we register a forecast for


def _devig(prices, slots):
    s = sum(prices.values()) or 1.0
    return {t: p / s * slots for t, p in prices.items()}


def _zk(prices, slots, power=1.15):
    """The zero-knowledge model's per-level forecast: favorite-longshot power correction."""
    sh = {t: max(p, 1e-9) ** power for t, p in prices.items()}
    z = sum(sh.values()) or 1.0
    return {t: min(sh[t] / z * slots, 0.999) for t in prices}


def _load(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _write(rows, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def snapshot(ladder=None, fundamental=None, power=1.15, bankroll=1000.0, date=None):
    """Register a dated snapshot of both models' forecasts + the market baseline, and freeze the
    day-0 books. Idempotent per date (won't double-register a day). Returns the scorecard dict."""
    ladder = ladder or WM.fetch_ladder()
    fundamental = fundamental if fundamental is not None else WF.fundamental_ladder()
    date = date or dt.date.today().isoformat()
    preds = _load(PRED)
    if any(p.get("date") == date for p in preds):
        print(f"[register] a snapshot for {date} already exists — leaving it immutable.")
    else:
        slot_of = {lvl: s for lvl, _g, s in WM.LADDER}
        new = []
        for lvl in CLAIM_LEVELS:
            prices = ladder.get(lvl, {})
            if not prices:
                continue
            mkt, zk = _devig(prices, slot_of[lvl]), _zk(prices, slot_of[lvl], power)
            elo = fundamental.get(lvl, {})
            for t in prices:
                base = round(mkt[t], 4)
                new.append(dict(date=date, model="zero_knowledge", level=lvl, team=t,
                                prob=round(zk[t], 4), market=base, provenance="real", outcome=None))
                fp = elo.get(_norm(t))
                if fp is not None:
                    new.append(dict(date=date, model="elo", level=lvl, team=t,
                                    prob=round(float(fp), 4), market=base, provenance="real", outcome=None))
        _write(preds + new, PRED)
        print(f"[register] wrote {len(new)} forecasts for {date} -> {PRED}")
    _freeze_books(ladder, fundamental, power, bankroll, date)
    return write_scorecard()


def _freeze_books(ladder, fundamental, power, bankroll, date):
    """Freeze each day-0 paper book to its ledger file ONCE (skips any that already exist, so they
    stay immutable). Buy & Hold and Active start identical; they diverge once results are fed in."""
    def _rows(book, tag):
        return [dict(id=f"{t['level']}:{t['team']}:{date}", level=t["level"], team=t["team"],
                     shares=t["shares"], entry=t["entry"], date=date,
                     note=f"day-0 {tag} {t['side'].lower()} · edge {t['edge']:+.3f}",
                     status="open", realized=None) for t in book]
    if not os.path.exists(CORE):
        r = _rows(B.sized_book(ladder, bankroll=bankroll, power=power), "structural")
        _write(r, CORE); _write(r, LIVE)
        print(f"[register] froze {len(r)} zero-knowledge positions -> {CORE} + {LIVE}")
    if fundamental and not os.path.exists(ELO_CORE):
        efrows = [x for x in WF.book_rows(ladder, model=fundamental, cost=WM.HALF_SPREAD)
                  if x["level"] != "advance"]
        r = _rows(B.sized_book(ladder, bankroll=bankroll, rows=efrows), "Elo")
        _write(r, ELO_CORE); _write(r, ELO_LIVE)
        print(f"[register] froze {len(r)} Elo positions -> {ELO_CORE} + {ELO_LIVE}")


def write_scorecard():
    """(Re)write the scorecard from the predictions ledger. Pre-resolution it just reports the
    number of registered claims; once forecasts settle it adds Brier + skill-vs-market."""
    preds = _load(PRED)
    claims = {(p["model"], p["level"], p["team"]) for p in preds}
    resolved = [p for p in preds if p.get("outcome") is not None]
    card = dict(as_of=dt.date.today().isoformat(), n_total=len(claims),
                n_resolved=len(resolved), overall={}, by_model={})
    if resolved:
        bm = sum((p["market"] - p["outcome"]) ** 2 for p in resolved) / len(resolved)
        for model in ("zero_knowledge", "elo"):
            ps = [p for p in resolved if p["model"] == model]
            if not ps:
                continue
            b = sum((p["prob"] - p["outcome"]) ** 2 for p in ps) / len(ps)
            hit = sum(1 for p in ps
                      if (p["prob"] > p["market"]) == (p["outcome"] > p["market"])) / len(ps)
            card["by_model"][model] = dict(brier=round(b, 4), skill_vs_market=round(bm - b, 4),
                                           hit_rate=round(hit, 3), n=len(ps))
        # the strip's flat fields use the informed (Elo) model, our headline
        head = card["by_model"].get("elo") or next(iter(card["by_model"].values()))
        card["overall"] = dict(hit_rate=head["hit_rate"], lift=head["skill_vs_market"],
                               brier=head["brier"])
    os.makedirs(LEDGER, exist_ok=True)
    with open(SCORE, "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2)
    return card


def resolve(level, outcomes):
    """Settle forecasts at `level` against {team: 0/1}; rescore; settle the frozen books too."""
    preds = _load(PRED)
    n = 0
    for p in preds:
        if p["level"] == level and p.get("outcome") is None and p["team"] in outcomes:
            p["outcome"] = int(outcomes[p["team"]])
            n += 1
    _write(preds, PRED)
    for path in (CORE, LIVE):
        rows = _load(path)
        for r in rows:
            if r.get("status") == "open" and r["level"] == level and r["team"] in outcomes:
                r["realized"] = round(r["shares"] * (float(outcomes[r["team"]]) - r["entry"]), 4)
                r["status"] = "resolved"
                r["resolved_at"] = dt.date.today().isoformat()
        _write(rows, path)
    print(f"[register] resolved {n} forecasts at {level}")
    return write_scorecard()


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Stamp / rescore the World Cup ledger (research only)")
    ap.add_argument("cmd", nargs="?", default="snapshot", choices=["snapshot", "scorecard"])
    a = ap.parse_args(argv)
    card = snapshot() if a.cmd == "snapshot" else write_scorecard()
    print(f"[register] scorecard: {card['n_total']} claims registered, {card['n_resolved']} resolved")


if __name__ == "__main__":
    main()
