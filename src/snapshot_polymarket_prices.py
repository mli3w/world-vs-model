"""
snapshot_polymarket_prices.py — capture pre-match Polymarket prices for played WC matches
==========================================================================================
For every match in `ledger/wc_results.json`, fetches the historical Polymarket price series for
the three outcomes (team A win / draw / team B win) from the CLOB `/prices-history` endpoint,
finds the latest price BEFORE the match's kickoff time, and stores it in `ledger/wc_match_prices.json`.

Idempotent: matches already snapshotted are skipped. Designed to run on the cron AFTER
auto_feed_results.py so newly-resolved matches get their pre-match prices captured on the next tick.

The result is what the 'as it unfolds' panel uses to score "the market didn't see it coming" upsets —
sharper than the Elo prior because Polymarket is a liquid real-money market with thousands of
participants integrating information our Elo can't see (injuries, form, late team news).

    python src/snapshot_polymarket_prices.py [--force]

`--force` re-fetches every match (drops the cache). Default skips already-cached matches.

Research/education only.
"""
import os
import sys
import json
import re
import argparse
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests                                              # noqa: E402
import worldcup_markets as WM                                # noqa: E402
import auto_feed_results as AFR                              # noqa: E402  (ESPN match-date lookup)

GAMMA = "https://gamma-api.polymarket.com/events"
CLOB_HISTORY = "https://clob.polymarket.com/prices-history"
RESULTS_PATH = os.path.join("ledger", "wc_results.json")
PRICES_PATH = os.path.join("ledger", "wc_match_prices.json")

# All the forms Polymarket might use for each team in either the event title or a market question.
# Order doesn't matter — we try each as a substring match. First entry is the "best" / primary form.
PM_FORMS = {
    "USA": ["United States", "USA"],
    "South Korea": ["South Korea", "Korea Republic", "Korea"],
    "Türkiye": ["Türkiye", "Turkiye", "Turkey"],
    "Czechia": ["Czechia", "Czech Republic"],
    "Ivory Coast": ["Côte d'Ivoire", "Cote d'Ivoire", "Ivory Coast"],
    "Cape Verde": ["Cabo Verde", "Cape Verde"],
    "Iran": ["IR Iran", "Iran"],
    "DR Congo": ["Congo DR", "DR Congo", "DRC", "Democratic Republic"],
    "Bosnia-Herzegovina": ["Bosnia-Herzegovina", "Bosnia and Herzegovina", "Bosnia & Herzegovina", "Bosnia"],
    "Saudi Arabia": ["Saudi Arabia"],
    "Curaçao": ["Curaçao", "Curacao"],
    "South Africa": ["South Africa"],
    "New Zealand": ["New Zealand"],
    "Switzerland": ["Switzerland"],
    "Uzbekistan": ["Uzbekistan"],
}


def _pm_name(team):
    """Our canonical team name → the form Polymarket uses in event TITLES (primary form)."""
    return PM_FORMS.get(team, [team])[0]


def _team_forms(team):
    """All forms we should try when matching a team against Polymarket's market QUESTIONS."""
    return PM_FORMS.get(team, [team])


def _pair_key(a, b):
    """Canonical, order-stable key for a match pair (alphabetised normalised names)."""
    return "__".join(sorted([a.lower(), b.lower()]))


def _load_cache(path=PRICES_PATH):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache, path=PRICES_PATH):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


_ESPN_DATE_CACHE = None                                       # {(a_lc, b_lc): "YYYY-MM-DD"}


def _build_espn_date_lookup():
    """One ESPN pass over the WC window builds a {match_pair → kickoff_date} map. Calling this
    once turns the per-match Polymarket lookup from O(40 dates × 22 matches) → O(22)."""
    global _ESPN_DATE_CACHE
    if _ESPN_DATE_CACHE is not None:
        return _ESPN_DATE_CACHE
    cache = {}
    base = dt.date(2026, 6, 11)
    for d in range(40):
        day = base + dt.timedelta(days=d)
        for n_a, n_b, _ga, _gb, _stage in AFR.fetch_day(day):
            ca = AFR._resolve_team(n_a)
            cb = AFR._resolve_team(n_b)
            if ca and cb:
                key = tuple(sorted([ca.lower(), cb.lower()]))
                cache[key] = day.isoformat()
    _ESPN_DATE_CACHE = cache
    return cache


# Polymarket uses some ISO-3 codes where FIFA differs (Switzerland CHE not SUI, Netherlands NLD not
# NED, Croatia HRV not CRO). We try both forms per team.
PM_CODE_ALT = {
    "sui": ["che", "sui"], "ned": ["nld", "ned"], "cro": ["hrv", "cro"],
    "ger": ["ger", "deu"], "rou": ["rou", "rom"],
}


def _find_event(team_a, team_b, timeout=15):
    """Look up the Polymarket WC event for this pair via a single slug query.

    Polymarket WC slugs are `fifwc-{code_a}-{code_b}-YYYY-MM-DD`. We get the kickoff date from ESPN
    (one batch pre-fetched into _ESPN_DATE_CACHE) and try both orderings + both FIFA/ISO code
    variants for teams where Polymarket diverges from FIFA (e.g. Switzerland CHE vs SUI)."""
    nz = WM.WL._norm
    code_a = (WM.TEAM_CODE.get(nz(team_a)) or "").lower()
    code_b = (WM.TEAM_CODE.get(nz(team_b)) or "").lower()
    if not code_a or not code_b:
        return None
    alts_a = PM_CODE_ALT.get(code_a, [code_a])
    alts_b = PM_CODE_ALT.get(code_b, [code_b])
    date = _build_espn_date_lookup().get(tuple(sorted([team_a.lower(), team_b.lower()])))
    dates_to_try = [date] if date else \
                   [(dt.date(2026, 6, 11) + dt.timedelta(days=i)).isoformat() for i in range(17)]
    for d in dates_to_try:
        for ca in alts_a:
            for cb in alts_b:
                for first, second in ((ca, cb), (cb, ca)):
                    slug = f"fifwc-{first}-{second}-{d}"
                    try:
                        r = requests.get(GAMMA, params={"slug": slug}, timeout=timeout)
                    except Exception:
                        continue
                    if r.status_code != 200:
                        continue
                    data = r.json()
                    if data:
                        return data[0]
    return None


def _outcome_token(market):
    """The YES token id for a market (the first entry in clobTokenIds)."""
    tids = market.get("clobTokenIds")
    if isinstance(tids, str):
        try:
            tids = json.loads(tids)
        except json.JSONDecodeError:
            return None
    if not tids:
        return None
    return tids[0]                                           # YES token


def _classify_markets(event, team_a, team_b):
    """Map the event's three markets to (a_win_token, draw_token, b_win_token). Polymarket questions
    use forms like 'Will Bosnia and Herzegovina win on …' that differ from our team names, so we
    try every known form per team (see PM_FORMS) until one is found as a substring."""
    a_forms = [s.lower() for s in _team_forms(team_a)]
    b_forms = [s.lower() for s in _team_forms(team_b)]
    a_tok = b_tok = d_tok = None
    for m in event.get("markets") or []:
        q = (m.get("question") or "").lower()
        tok = _outcome_token(m)
        if "draw" in q:
            d_tok = tok
        elif any(f in q for f in a_forms):
            a_tok = tok
        elif any(f in q for f in b_forms):
            b_tok = tok
    return a_tok, d_tok, b_tok


def _price_before(token_id, kickoff_ts, timeout=15, lookback_hours=72):
    """Last CLOB price at or before kickoff_ts for the given outcome token."""
    if token_id is None:
        return None
    start = kickoff_ts - lookback_hours * 3600
    try:
        r = requests.get(CLOB_HISTORY, params={"market": token_id, "startTs": start,
                                                "endTs": kickoff_ts, "fidelity": 60},
                         timeout=timeout)
        if r.status_code != 200:
            return None
        history = (r.json() or {}).get("history") or []
        if not history:
            return None
        # Latest data point at or before kickoff
        pre = [h for h in history if h.get("t", 0) <= kickoff_ts]
        if not pre:
            return None
        return float(pre[-1].get("p"))
    except Exception:
        return None


def snapshot_match(team_a, team_b, cache, force=False):
    """Fetch (or look up cached) pre-kickoff Polymarket prices for one match. Returns the entry."""
    key = _pair_key(team_a, team_b)
    if not force and key in cache and cache[key].get("source") == "polymarket":
        return cache[key]
    event = _find_event(team_a, team_b)
    if not event:
        return None
    kickoff_iso = event.get("endDate") or ""
    if not kickoff_iso:
        return None
    try:
        kickoff_ts = int(dt.datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None
    a_tok, d_tok, b_tok = _classify_markets(event, team_a, team_b)
    pa = _price_before(a_tok, kickoff_ts)
    pd = _price_before(d_tok, kickoff_ts)
    pb = _price_before(b_tok, kickoff_ts)
    if pa is None or pb is None or pd is None:
        return None
    # Renormalise (vig is small but explicit) so they sum to 1
    s = pa + pd + pb
    if s <= 0:
        return None
    entry = dict(a=team_a, b=team_b,
                 pa=round(pa / s, 4), pd=round(pd / s, 4), pb=round(pb / s, 4),
                 raw_pa=round(pa, 4), raw_pd=round(pd, 4), raw_pb=round(pb, 4),
                 kickoff=kickoff_iso, asof=dt.datetime.utcnow().isoformat() + "Z",
                 source="polymarket")
    cache[key] = entry
    return entry


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cache pre-match Polymarket prices for played WC matches")
    ap.add_argument("--results", default=RESULTS_PATH)
    ap.add_argument("--cache", default=PRICES_PATH)
    ap.add_argument("--force", action="store_true", help="re-fetch matches already in the cache")
    a = ap.parse_args(argv)

    if not os.path.exists(a.results):
        print(f"[snapshot] no results ledger at {a.results}; nothing to snapshot")
        return 0
    with open(a.results, encoding="utf-8") as f:
        results = json.load(f) or []
    cache = _load_cache(a.cache)
    added = skipped = failed = 0
    for r in results:
        key = _pair_key(r["a"], r["b"])
        if not a.force and key in cache and cache[key].get("source") == "polymarket":
            skipped += 1
            continue
        entry = snapshot_match(r["a"], r["b"], cache, force=a.force)
        if entry:
            added += 1
        else:
            failed += 1
            print(f"[snapshot] failed: {r['a']} vs {r['b']}")
    _save_cache(cache, a.cache)
    print(f"[snapshot] added={added} cached={skipped} failed={failed}  ({len(cache)} total in cache)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
