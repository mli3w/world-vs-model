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
BRACKET_SCORE = os.path.join(LEDGER, "bracket_score.json")  # the knockout-bracket scorecard
BMA_PATH = os.path.join(LEDGER, "bma.json")               # per-level model weights + ensemble probs
# Every market rung we register a forecast for — the whole knockout ladder, not just the ends, so
# the bracket (who goes how far) is scored round by round. reach_R16 has no Polymarket market.
CLAIM_LEVELS = ("advance", "reach_QF", "reach_SF", "reach_F", "win")
# slots that actually reach each rung, and the bracket-points weight for a correct pick there.
LEVEL_SLOTS = {"advance": 32, "reach_QF": 8, "reach_SF": 4, "reach_F": 2, "win": 1}
BRACKET_WEIGHTS = {"advance": 1, "reach_QF": 4, "reach_SF": 8, "reach_F": 16, "win": 32}
BRACKET_LABELS = {"advance": "Last 32", "reach_QF": "Quarter-finals", "reach_SF": "Semi-finals",
                  "reach_F": "Final", "win": "Champion"}


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
    write_bracket_scorecard()
    write_bma()
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


def add_levels(levels, ladder=None, fundamental=None, power=1.15, date=None):
    """Register forecasts for extra market rungs (e.g. the mid-bracket reach_QF/SF/F) as a dated
    snapshot, skipping any (date, model, level, team) already present. Used to extend an existing
    day's registration to the full knockout ladder without disturbing what's already stamped."""
    ladder = ladder or WM.fetch_ladder()
    fundamental = fundamental if fundamental is not None else WF.fundamental_ladder()
    date = date or dt.date.today().isoformat()
    preds = _load(PRED)
    have = {(p["date"], p["model"], p["level"], p["team"]) for p in preds}
    slot_of = {lvl: s for lvl, _g, s in WM.LADDER}
    new = []
    for lvl in levels:
        prices = ladder.get(lvl, {})
        if not prices or lvl not in slot_of:
            continue
        mkt, zk = _devig(prices, slot_of[lvl]), _zk(prices, slot_of[lvl], power)
        elo = fundamental.get(lvl, {})
        for t in prices:
            base = round(mkt[t], 4)
            if (date, "zero_knowledge", lvl, t) not in have:
                new.append(dict(date=date, model="zero_knowledge", level=lvl, team=t,
                                prob=round(zk[t], 4), market=base, provenance="real", outcome=None))
            fp = elo.get(_norm(t))
            if fp is not None and (date, "elo", lvl, t) not in have:
                new.append(dict(date=date, model="elo", level=lvl, team=t,
                                prob=round(float(fp), 4), market=base, provenance="real", outcome=None))
    if new:
        _write(preds + new, PRED)
        print(f"[register] added {len(new)} forecasts for levels {levels} ({date}) -> {PRED}")
    return len(new)


def bracket_scorecard(preds=None):
    """Score the knockout bracket round by round, market vs each model, from the registered
    forecasts + their resolved outcomes. Two readings: a round-weighted **points** race (a correct
    team that reaches a rung scores that rung's weight) and the per-rung **hit** counts. Each
    'player' picks the top-k teams by its own probability, where k is the rung's slot count."""
    preds = preds if preds is not None else _load(PRED)
    latest = {}                                            # newest forecast per (model, level, team)
    for p in preds:
        k = (p["model"], p["level"], p["team"])
        if k not in latest or p["date"] >= latest[k]["date"]:
            latest[k] = p
    lev = {}                                               # level -> team -> {market, zk, elo, outcome}
    for (model, level, team), p in latest.items():
        d = lev.setdefault(level, {}).setdefault(team, {})
        d[model] = p["prob"]
        d["market"] = p.get("market")
        if p.get("outcome") is not None:
            d["outcome"] = p["outcome"]
    players = ("market", "zero_knowledge", "elo")
    points = {pl: 0 for pl in players}
    rows = []
    for level in CLAIM_LEVELS:
        teams = lev.get(level)
        if not teams:
            continue
        k, w = LEVEL_SLOTS[level], BRACKET_WEIGHTS[level]
        actual = {t for t, d in teams.items() if d.get("outcome") == 1}
        row = dict(level=level, label=BRACKET_LABELS[level], slots=k, weight=w,
                   resolved=bool(actual), picks={}, hits={})
        topk = {}                                          # full top-k set per player (for divergence)
        for pl in players:
            ranked = sorted((t for t in teams if teams[t].get(pl) is not None),
                            key=lambda t: -teams[t][pl])
            topk[pl] = ranked[:k]
            row["picks"][pl] = ranked[:5]                  # keep a few for display
            if actual:
                hit = len(set(ranked[:k]) & actual)
                row["hits"][pl] = hit
                points[pl] += w * hit
        em, mm = set(topk.get("elo", [])), set(topk.get("market", []))
        row["agree"] = len(em & mm)                        # where the model and market's brackets coincide
        row["contested"] = dict(
            model=sorted(em - mm, key=lambda t: -teams[t].get("elo", 0))[:4],
            market=sorted(mm - em, key=lambda t: -teams[t].get("market", 0))[:4])
        rows.append(row)
    win = next((r for r in rows if r["level"] == "win"), None)
    champions = {pl: (win["picks"][pl][0] if win and win["picks"].get(pl) else None)
                 for pl in players} if win else {}
    return dict(as_of=dt.date.today().isoformat(), points=points, levels=rows,
                champions=champions, n_resolved=sum(1 for r in rows if r["resolved"]))


def write_bma(preds=None):
    """Compute and persist Bayesian Model Averaging — per-level weights + ensemble forecasts —
    so the board can render a third 'ensemble' voice alongside the two component models.

    Dormant pre-tournament: with no resolved forecasts the weights stay at 50/50 per level and the
    ensemble equals the simple average. Once results land, weights drift per rung toward whichever
    model is better-calibrated at *that* rung — self-correcting and falsifiable.
    """
    import wc_bma as BMA                                    # local import: keeps register import-light
    preds = preds if preds is not None else _load(PRED)
    # latest forecast per (model, level, team)
    latest = {}
    for p in preds:
        k = (p["model"], p["level"], p["team"])
        if k not in latest or p["date"] >= latest[k]["date"]:
            latest[k] = p
    forecasts = {k: r["prob"] for k, r in latest.items()}
    resolved = [r for r in latest.values() if r.get("outcome") is not None]
    out = BMA.bma(forecasts, resolved)
    # JSON-friendly: tuple keys -> "level::team" strings
    ensemble = {f"{lvl}::{team}": p for (lvl, team), p in out["ensemble"].items()}
    payload = dict(as_of=dt.date.today().isoformat(), n_resolved=out["n_resolved"],
                   models=out["models"], levels=out["levels"],
                   weights=out["weights"], ensemble=ensemble)
    os.makedirs(os.path.dirname(BMA_PATH) or ".", exist_ok=True)
    with open(BMA_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload


def write_bracket_scorecard():
    """Persist the bracket scorecard the board reads."""
    card = bracket_scorecard()
    os.makedirs(os.path.dirname(BRACKET_SCORE) or ".", exist_ok=True)
    with open(BRACKET_SCORE, "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2)
    return card


def resolve(level, outcomes):
    """Settle forecasts at `level` against {team: 0/1}; rescore; settle the frozen books too.

    Books settled: ZK Buy & Hold (CORE) + ZK Active (LIVE) + Elo Buy & Hold (ELO_CORE) +
    Elo Active (ELO_LIVE). Each open position whose team is in `outcomes` flips to
    status="resolved" with realized = shares * (outcome - entry)."""
    preds = _load(PRED)
    n = 0
    for p in preds:
        if p["level"] == level and p.get("outcome") is None and p["team"] in outcomes:
            p["outcome"] = int(outcomes[p["team"]])
            n += 1
    _write(preds, PRED)
    for path in (CORE, LIVE, ELO_CORE, ELO_LIVE):
        rows = _load(path)
        for r in rows:
            if r.get("status") == "open" and r["level"] == level and r["team"] in outcomes:
                r["realized"] = round(r["shares"] * (float(outcomes[r["team"]]) - r["entry"]), 4)
                r["status"] = "resolved"
                r["resolved_at"] = dt.date.today().isoformat()
        _write(rows, path)
    print(f"[register] resolved {n} forecasts at {level}")
    write_bracket_scorecard()
    write_bma()
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
