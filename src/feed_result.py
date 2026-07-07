"""
feed_result.py — record a played match so the model re-forecasts (matchday convenience)
========================================================================================
One painless command instead of hand-editing JSON:

    python src/feed_result.py BRA CRO 2 1            # group match (Brazil 2-1 Croatia)
    python src/feed_result.py ARG FRA 3 2 --stage ko # a knockout result
    python src/feed_result.py --list                 # show everything recorded so far

Teams accept the FIFA 3-letter code (BRA) or the exact name (Brazil). The match is appended to
`ledger/wc_results.json`; the next board rebuild folds it into the **live Elo re-forecast** (and
completed group games are then held fixed in the group sim). Resolving the pre-registered
predictions + books for Brier scoring is a separate, less-frequent step (`worldcup_register.resolve`),
done when a whole group or round finishes.

Research/education only — not financial advice, not a solicitation, no capital invested.
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import worldcup_markets as WM            # noqa: E402  (FIFA codes)
from worldcup_live import FIELD, _norm   # noqa: E402  (the 48-team field)

RESULTS = os.path.join("ledger", "wc_results.json")
_CODE2NAME = {c: n for n, c in WM._FIFA.items()}    # FIFA 3-letter code -> canonical name


def _resolve(token):
    """Map a FIFA code or a name to the canonical field name; fail loudly on an unknown team."""
    t = (token or "").strip()
    if t.upper() in _CODE2NAME:
        return _CODE2NAME[t.upper()]
    for d in FIELD:
        if _norm(d) == _norm(t):
            return d
    raise SystemExit(f"[feed] unknown team '{token}' — use a FIFA code (e.g. BRA) or the exact name")


def _load(path=RESULTS):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or []
    except (FileNotFoundError, ValueError):
        return []


def add(team_a, team_b, ga, gb, stage="group", adv=None, path=RESULTS):
    """Append a played match (full team names) to the results file. Idempotent per (pairing, stage).
    `adv` records who advanced when a knockout tie is level after extra time and decided on
    penalties — with ga == gb the score alone can't say who went through, so the ledger stores the
    advancer and the model drops the loser accordingly."""
    a, b = _resolve(team_a), _resolve(team_b)
    if a == b:
        raise SystemExit("[feed] a team can't play itself")
    w = _resolve(adv) if adv is not None else None
    if w is not None and w not in (a, b):
        raise SystemExit(f"[feed] advancer '{adv}' must be one of {a} / {b}")
    rows = _load(path)
    if any(frozenset((r["a"], r["b"])) == frozenset((a, b)) and r.get("stage", "group") == stage
           for r in rows):
        raise SystemExit(f"[feed] {a} v {b} ({stage}) already recorded — edit {path} by hand to change it")
    row = dict(a=a, b=b, ga=int(ga), gb=int(gb), stage=stage)
    if w is not None:
        row["adv"] = w
    rows.append(row)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    tail = f"  ({w} adv on pens)" if w is not None else ""
    print(f"[feed] recorded {a} {int(ga)}-{int(gb)} {b} ({stage}){tail} -> {path}  ({len(rows)} matches total)")
    return rows


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("--list", "list"):
        rows = _load()
        if not rows:
            print("[feed] no results recorded yet.")
        for r in rows:
            print(f"  {r['a']} {r['ga']}-{r['gb']} {r['b']}  ({r.get('stage', 'group')})")
        return
    ap = argparse.ArgumentParser(description="Record a World Cup result (research only)")
    ap.add_argument("teamA", help="FIFA code (BRA) or exact name (Brazil)")
    ap.add_argument("teamB", help="FIFA code or exact name")
    ap.add_argument("ga", type=int, help="goals for teamA")
    ap.add_argument("gb", type=int, help="goals for teamB")
    ap.add_argument("--stage", default="group", choices=["group", "ko"],
                    help="group (default) conditions the group sim; ko updates ratings only")
    ap.add_argument("--adv", default=None,
                    help="for a knockout tie level after ET: the team that advanced on penalties")
    a = ap.parse_args(argv)
    add(a.teamA, a.teamB, a.ga, a.gb, a.stage, adv=a.adv)


if __name__ == "__main__":
    main()
