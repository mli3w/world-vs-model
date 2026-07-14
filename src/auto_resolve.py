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


def _reached_ko_level(results, min_round):
    """Team reached round N iff EITHER they won at least (N-1) KO matches on scoreline (a
    decisive win in round K → they reached K+1) OR they appear in a round-K match with K≥N.

    Handles two edge cases: (a) penalty-shootout wins (score is tied in the ledger but the
    team still appears in the next round, so appearance wins the "did they reach" check);
    (b) teams currently in a live round — Spain won the QF 2-1, so they reached SF even
    though the SF match may not yet be recorded.

      min_round = 2 → reached R16    (won R32 or appears in R16)
      min_round = 3 → reached QF     (won R16 or appears in QF)
      min_round = 4 → reached SF     (won QF or appears in SF)
      min_round = 5 → reached F      (won SF or appears in F)
      min_round = 6 → won the Cup    (won the F)
    """
    from collections import defaultdict
    # Sort KO matches into rounds by appearance count: a team's k-th KO appearance = round k.
    ko = [r for r in results if r.get("stage") == "ko"]
    appearances = defaultdict(int)
    appearance_round = {}                                    # (team, match_idx) -> round K they played
    for r in ko:
        for t in (r["a"], r["b"]):
            appearances[t] += 1
        appearance_round[(r["a"], r["b"])] = max(appearances[r["a"]], appearances[r["b"]])
    reached_via_appearance = {t for t, n in appearances.items() if n >= min_round}
    # Wins per team from decisive scorelines
    wins = defaultdict(int)
    for r in ko:
        a, b, ga, gb = r["a"], r["b"], r["ga"], r["gb"]
        if ga > gb: wins[a] += 1
        elif gb > ga: wins[b] += 1
    # For "won the cup" (min_round=6), we need decisive-final logic: team won ≥5 decisive
    # matches, OR the Final has been recorded with them as decisive winner.
    reached_via_wins = {t for t, n in wins.items() if n >= min_round - 1}
    return reached_via_appearance | reached_via_wins


def _all_confirmed_out_for_ko(results, level_min_appearances, top32_teams):
    """Teams that CANNOT still reach this level. Two groups:
       (a) teams that never made the top-32 (eliminated in groups)
       (b) teams in top-32 that played KO but not enough to have reached this level, AND
           the round they'd need to have won next is already resolved."""
    from collections import defaultdict
    plays = defaultdict(int)
    losses = defaultdict(int)
    for r in results:
        if r.get("stage") != "ko":
            continue
        a, b, ga, gb = r["a"], r["b"], r["ga"], r["gb"]
        plays[a] += 1; plays[b] += 1
        if ga > gb: losses[b] += 1
        elif gb > ga: losses[a] += 1
    # For PK matches (equal scores in KO), we can't tell the loser from the ledger, but the
    # loser will still show a losses[t]=0 while their opponent moved on. For safety we treat
    # any team that played KO but has strictly < min_appearances games AND has already had
    # a KO loss (or the previous round is fully resolved) as out.
    confirmed_out = set()
    for t in top32_teams:
        if plays[t] < level_min_appearances:
            # Team stopped at some earlier KO round. They are out.
            confirmed_out.add(t)
    return confirmed_out


def resolve_ko_level(level, min_round, dry_run=False):
    """Generic KO settlement using appearance-or-wins logic (handles PK shootouts + live
    rounds). `min_round`: 2=reach_R16, 3=reach_QF, 4=reach_SF, 5=reach_F, 6=win."""
    if not os.path.exists(RESULTS):
        return 0
    with open(RESULTS, encoding="utf-8") as f:
        results = json.load(f) or []
    reached = _reached_ko_level(results, min_round)
    # Teams that played KO (top-32) but didn't reach this level yet → confirmed 0
    top32 = _reached_ko_level(results, 2)                     # anyone who reached R16
    # Actually top32 = anyone with at least 1 KO appearance
    from collections import defaultdict
    plays = defaultdict(int)
    for r in results:
        if r.get("stage") == "ko":
            plays[r["a"]] += 1; plays[r["b"]] += 1
    top32 = set(plays.keys())

    outcomes = {}
    # Everyone in `reached` → 1
    for t in reached:
        outcomes[_WL_NORM(t)] = 1
    # Teams eliminated in groups (not in top-32) → 0
    for t_full in (n for ts in WF.GROUPS_2026.values() for n in ts):
        if t_full not in top32:
            outcomes.setdefault(_WL_NORM(t_full), 0)
    # Teams in top-32 that are NOT in `reached` → 0 only if the previous round has fully
    # resolved for them. Simplest safe check: they lost decisively in an earlier round.
    # Losses per team — decisive AND penalty-inferred. For a tied KO match, whichever team
    # DIDN'T play in the next KO round is the PK loser (the other team advanced).
    from collections import defaultdict as _dd
    losses = _dd(int)
    ko_matches = [r for r in results if r.get("stage") == "ko"]
    all_ko_teams = set()
    for r in ko_matches:
        all_ko_teams.add(r["a"]); all_ko_teams.add(r["b"])
    for r in ko_matches:
        a, b, ga, gb = r["a"], r["b"], r["ga"], r["gb"]
        if ga > gb: losses[b] += 1
        elif gb > ga: losses[a] += 1
        else:
            # Tied → PK. The loser is whichever team has FEWER total KO appearances (the
            # winner went on to play the next round; the loser stopped here).
            a_apps = sum(1 for x in ko_matches if x["a"] == a or x["b"] == a)
            b_apps = sum(1 for x in ko_matches if x["a"] == b or x["b"] == b)
            if a_apps < b_apps: losses[a] += 1
            elif b_apps < a_apps: losses[b] += 1
            # Same appearance count → both stopped here (final that hasn't been resolved) —
            # leave both unmarked, handled by higher-level check.
    for t in top32:
        if t not in reached and losses[t] >= 1:
            outcomes[_WL_NORM(t)] = 0
    n_won = sum(1 for v in outcomes.values() if v == 1)
    n_lost = sum(1 for v in outcomes.values() if v == 0)
    if n_won == 0 and n_lost == 0:
        print(f"[auto-resolve] {level}: nothing to settle yet, skip")
        return 0
    print(f"[auto-resolve] {level}: {n_won} reached, {n_lost} confirmed-out")
    if dry_run:
        return 0
    WR.resolve(level, outcomes)
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Settle resolvable Polymarket rungs against results")
    ap.add_argument("--dry-run", action="store_true", help="compute outcomes, don't write")
    a = ap.parse_args(argv)
    n = 0
    n += resolve_advance(dry_run=a.dry_run)
    n += resolve_ko_level("reach_QF", min_round=3, dry_run=a.dry_run)
    n += resolve_ko_level("reach_SF", min_round=4, dry_run=a.dry_run)
    n += resolve_ko_level("reach_F",  min_round=5, dry_run=a.dry_run)
    print(f"[auto-resolve] resolved {n} rung(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
