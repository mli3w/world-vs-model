"""
auto_resolve.py — settle resolvable market rungs against the live results ledger
================================================================================
Runs on every cron tick AFTER auto_feed_results.py (results in) and BEFORE the
board build (so the scorecard, bracket-score, BMA and the books all reflect
the latest resolutions).

  advance   -> resolvable once all 72 group games are recorded; advancers =
               top-2 of each group + the 8 best thirds (Pts, GD, GF tiebreakers).
  reach_R16 -> not a Polymarket rung, skip
  reach_QF  -> resolvable once all 16 R32 ties are recorded (each winner reaches QF).
  reach_SF  -> resolvable once all 8 R16 ties are recorded.
  reach_F   -> resolvable once both QF→SF transitions are recorded.
  win       -> resolvable once the final is recorded.

Idempotent: a rung whose predictions already have outcome != None is skipped;
worldcup_register.resolve() also only touches predictions where outcome is None.

  python src/auto_resolve.py [--dry-run]

Research/education only.
"""
import os
import sys
import json
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import worldcup_fundamental as WF                            # noqa: E402
import worldcup_register as WR                               # noqa: E402
from worldcup_live import _norm as _WL_NORM                  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "ledger", "wc_results.json")


def _group_table(results):
    """Final group standings (Pts / GD / GF) per team for completed groups."""
    team_to_group = {t: g for g, ts in WF.GROUPS_2026.items() for t in ts}
    table = defaultdict(lambda: {"Pts": 0, "GF": 0, "GA": 0, "P": 0})
    for r in results:
        if r.get("stage", "group") != "group":
            continue
        a, b, ga, gb = r["a"], r["b"], r["ga"], r["gb"]
        if a not in team_to_group or b not in team_to_group:
            continue
        for t, gf, ga_ in ((a, ga, gb), (b, gb, ga)):
            table[t]["P"] += 1
            table[t]["GF"] += gf
            table[t]["GA"] += ga_
        if ga > gb:   table[a]["Pts"] += 3
        elif gb > ga: table[b]["Pts"] += 3
        else:         table[a]["Pts"] += 1; table[b]["Pts"] += 1
    return table


def _advancers_from_results(results):
    """Compute the 32 teams that advance from the group stage: top-2 per group +
    8 best thirds (sorted by Pts → GD → GF across all 12 third-placers).
    Returns (advanced_set, eliminated_set) — both keyed by team display name."""
    table = _group_table(results)
    if not all(min(table[t]["P"] for t in ts) >= 3 for ts in WF.GROUPS_2026.values()):
        return None                                          # group stage not done yet
    advanced, eliminated, thirds = set(), set(), []
    for g, teams in WF.GROUPS_2026.items():
        standing = sorted([(t, table[t]) for t in teams],
                           key=lambda x: (-x[1]["Pts"],
                                          -(x[1]["GF"] - x[1]["GA"]),
                                          -x[1]["GF"]))
        advanced.update([standing[0][0], standing[1][0]])
        thirds.append(standing[2])
        eliminated.add(standing[3][0])
    thirds.sort(key=lambda x: (-x[1]["Pts"], -(x[1]["GF"]-x[1]["GA"]), -x[1]["GF"]))
    for t, _ in thirds[:8]:                                  # 8 best thirds advance
        advanced.add(t)
    for t, _ in thirds[8:]:                                  # bottom 4 eliminated
        eliminated.add(t)
    return advanced, eliminated


def _outcomes_at_advance(advanced, eliminated):
    """{normalised team key -> 0/1} for the predictions ledger. ALL 48 teams must be
    in the dict so SHORT bets on eliminated teams settle to 0 (max profit) too."""
    out = {}
    for t in advanced:
        out[_WL_NORM(t)] = 1
    for t in eliminated:
        out[_WL_NORM(t)] = 0
    return out


def resolve_advance(dry_run=False):
    """Resolve the 'advance' rung if all 72 group games are in. Idempotent."""
    if not os.path.exists(RESULTS):
        print("[auto-resolve] no results ledger — nothing to do")
        return 0
    with open(RESULTS, encoding="utf-8") as f:
        results = json.load(f) or []
    info = _advancers_from_results(results)
    if info is None:
        print(f"[auto-resolve] group stage not complete ({len(results)} group matches) — skip")
        return 0
    advanced, eliminated = info
    outcomes = _outcomes_at_advance(advanced, eliminated)
    print(f"[auto-resolve] advance: {len(advanced)} advanced, {len(eliminated)} eliminated, "
          f"{len(outcomes)} outcomes ready")
    if dry_run:
        print("[auto-resolve] --dry-run; not writing")
        return 0
    WR.resolve("advance", outcomes)
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Settle resolvable Polymarket rungs against results")
    ap.add_argument("--dry-run", action="store_true", help="compute outcomes, don't write")
    a = ap.parse_args(argv)
    n = resolve_advance(dry_run=a.dry_run)
    # Future: when knockout rounds resolve, add resolve_qf(), resolve_sf(), etc.
    print(f"[auto-resolve] resolved {n} rung(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
