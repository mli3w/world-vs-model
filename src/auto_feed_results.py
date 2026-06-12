"""
auto_feed_results.py — pull settled WC 2026 matches and append to the live results ledger
==========================================================================================
Polls ESPN's public, keyless soccer API for completed 2026 World Cup matches and folds any
not-already-recorded results into `ledger/wc_results.json` via `feed_result.add()` (idempotent
per pairing — running twice is a no-op). Designed to run in the GitHub Actions cron just before
the board build, so the site picks up new results on every refresh without manual intervention.

    python src/auto_feed_results.py [--days N]

Default scans yesterday, today, and tomorrow (UTC) to catch boundary-crossing kickoffs. Errors
silently: an API blip prints to stderr but exits 0 so the cron isn't blocked.

Research/education only.
"""
import os
import sys
import datetime as dt
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests                                              # noqa: E402
import feed_result as F                                      # noqa: E402  (F.add() is idempotent)
import worldcup_markets as WM                                # noqa: E402

ESPN_URL = "http://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"

# ESPN team-name → our canonical FIELD name (covers every form we've seen).
ALIAS = {
    "United States": "USA",
    "Korea Republic": "South Korea", "Republic of Korea": "South Korea",
    "Czech Republic": "Czechia",
    "Cote d'Ivoire": "Ivory Coast", "Côte d'Ivoire": "Ivory Coast",
    "Cabo Verde": "Cape Verde",
    "Curacao": "Curaçao",
    "Turkiye": "Türkiye", "Turkey": "Türkiye",
    "DR Congo": "DR Congo", "DRC": "DR Congo",
    "Democratic Republic of the Congo": "DR Congo",
    "Iran": "Iran", "IR Iran": "Iran",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "Bosnia & Herzegovina": "Bosnia-Herzegovina",
}


def _resolve_team(name):
    """ESPN name → canonical FIELD entry, or None if not in the 48-team field."""
    if not name:
        return None
    cleaned = name.strip()
    if cleaned in WM.WL.FIELD:
        return cleaned
    if cleaned in ALIAS:
        return ALIAS[cleaned]
    nz = WM.WL._norm(cleaned)
    for canonical in WM.WL.FIELD:
        if WM.WL._norm(canonical) == nz:
            return canonical
    return None


def fetch_day(day, timeout=15):
    """Return list of (team_a_name, team_b_name, ga, gb, stage_hint) for fully-time matches.
    `stage_hint` is "group" pre-Round-of-32 and "ko" thereafter (we infer by date)."""
    url = f"{ESPN_URL}?dates={day.strftime('%Y%m%d')}"
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "world-vs-model research"})
        if r.status_code != 200:
            print(f"[auto-feed] ESPN {day}: HTTP {r.status_code}", file=sys.stderr)
            return []
        data = r.json()
    except Exception as e:
        print(f"[auto-feed] ESPN {day}: {e}", file=sys.stderr)
        return []
    out = []
    # Group stage in 2026 runs Jun 11–27; knockout begins Jun 28
    stage = "group" if day <= dt.date(2026, 6, 27) else "ko"
    for ev in data.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        status = ((comp.get("status") or {}).get("type") or {}).get("name", "")
        if status != "STATUS_FULL_TIME":
            continue
        teams = comp.get("competitors") or []
        if len(teams) != 2:
            continue
        try:
            name_a = (teams[0].get("team") or {}).get("displayName")
            name_b = (teams[1].get("team") or {}).get("displayName")
            ga = int(teams[0].get("score") or 0)
            gb = int(teams[1].get("score") or 0)
        except (TypeError, ValueError):
            continue
        out.append((name_a, name_b, ga, gb, stage))
    return out


def run(days=3, today=None):
    """Scan a window of days and feed any settled matches not already recorded.
    Returns (added, skipped, unknown)."""
    today = today or dt.date.today()
    added, skipped, unknown = 0, 0, []
    # Scan from (days-1) days ago through tomorrow, so a kickoff that straddles UTC midnight
    # gets caught regardless of which side of the boundary ESPN files it under.
    for delta in range(-(days - 1), 2):
        day = today + dt.timedelta(days=delta)
        for name_a, name_b, ga, gb, stage in fetch_day(day):
            ca = _resolve_team(name_a)
            cb = _resolve_team(name_b)
            if not ca or not cb:
                unknown.append((name_a, name_b))
                continue
            try:
                F.add(ca, cb, ga, gb, stage=stage)
                added += 1
            except SystemExit:                              # F.add raises on duplicates — idempotent
                skipped += 1
    return added, skipped, unknown


def main(argv=None):
    ap = argparse.ArgumentParser(description="Auto-feed WC 2026 results from ESPN's public API")
    ap.add_argument("--days", type=int, default=3, help="scan window in days back from today")
    a = ap.parse_args(argv)
    added, skipped, unknown = run(days=a.days)
    print(f"[auto-feed] added={added} already-recorded={skipped} unknown-teams={len(unknown)}")
    for na, nb in unknown:
        print(f"  unknown pair: '{na}' vs '{nb}'  (add to ALIAS in auto_feed_results.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
