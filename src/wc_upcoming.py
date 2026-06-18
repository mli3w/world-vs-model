"""
wc_upcoming.py — preview the next 24-72h of WC matches: where do model & market disagree?
==========================================================================================
The "as it unfolds" panel is retrospective: how the model moved, what shocked us. This module
is its forward-looking complement. For every WC fixture in a window starting from `today`,
we fetch:

    • Polymarket's CURRENT live prices (the market's call right now), and
    • Our model's pre-match prior (raw Elo + host bonus + strength-aware draw rate),

and rank by **maximum disagreement** — the matches where the transparent model's call diverges
most from a liquid real-money market. Publishing the calls BEFORE kickoff is the accountability
move: the match resolves the disagreement publicly, no retroactive narrative.

Writes `ledger/wc_upcoming.json`. Run on the cron before the board build (the board reads
this cache to render the panel without doing live HTTP itself).

    python src/wc_upcoming.py [--window 3] [--top 6] [--min-gap 0.05]

Research/education only.
"""
import os
import sys
import json
import argparse
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests                                                # noqa: E402
import worldcup_fundamental as WF                              # noqa: E402
import worldcup_markets as WM                                  # noqa: E402
import wc_evolution as EV                                      # noqa: E402
import snapshot_polymarket_prices as SPP                       # noqa: E402
import auto_feed_results as AFR                                # noqa: E402

GAMMA = "https://gamma-api.polymarket.com/events"
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
OUT_PATH = os.path.join("ledger", "wc_upcoming.json")


def _espn_upcoming(today, window_days):
    """Pull WC fixtures from ESPN with status pre/scheduled inside [today, today+window]."""
    out = []
    for d_off in range(window_days + 1):
        day = (today + dt.timedelta(days=d_off)).strftime("%Y%m%d")
        try:
            r = requests.get(ESPN_BASE, params={"dates": day}, timeout=10)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        for ev in r.json().get("events", []):
            comp = (ev.get("competitions") or [{}])[0]
            status = comp.get("status", {}).get("type", {}).get("state", "")
            if status not in ("pre", "scheduled"):
                continue
            teams = comp.get("competitors", [])
            if len(teams) < 2:
                continue
            n0 = teams[0].get("team", {}).get("displayName", "")
            n1 = teams[1].get("team", {}).get("displayName", "")
            ta = AFR._resolve_team(n0)
            tb = AFR._resolve_team(n1)
            if not ta or not tb:
                continue
            date_iso = day[:4] + "-" + day[4:6] + "-" + day[6:]
            out.append({"a": ta, "b": tb, "date": date_iso})
    return out


def _yes_price(market):
    """The YES-side price for a Polymarket binary market. outcomePrices is a JSON-encoded list."""
    op = market.get("outcomePrices")
    if isinstance(op, str):
        try:
            op = json.loads(op)
        except (ValueError, TypeError):
            op = None
    if isinstance(op, list) and op:
        try:
            return float(op[0])
        except (ValueError, TypeError):
            pass
    # Fallback: lastTradePrice or bestBid
    for k in ("lastTradePrice", "bestBid"):
        v = market.get(k)
        if v is not None:
            try:
                return float(v)
            except (ValueError, TypeError):
                pass
    return None


def _fetch_current(team_a, team_b, date, timeout=10):
    """Polymarket's CURRENT (pa, pd, pb) for one upcoming match, normalised so the three sum to
    1.0. Returns None if we can't find the event or any side is missing."""
    nz = WM.WL._norm
    ca = (WM.TEAM_CODE.get(nz(team_a)) or "").lower()
    cb = (WM.TEAM_CODE.get(nz(team_b)) or "").lower()
    if not ca or not cb:
        return None
    alts_a = SPP.PM_CODE_ALT.get(ca, [ca])
    alts_b = SPP.PM_CODE_ALT.get(cb, [cb])
    for a in alts_a:
        for b in alts_b:
            for first, second in ((a, b), (b, a)):
                slug = f"fifwc-{first}-{second}-{date}"
                try:
                    r = requests.get(GAMMA, params={"slug": slug}, timeout=timeout)
                except Exception:
                    continue
                if r.status_code != 200:
                    continue
                data = r.json()
                if not data:
                    continue
                ev = data[0]
                a_forms = [s.lower() for s in SPP._team_forms(team_a)]
                b_forms = [s.lower() for s in SPP._team_forms(team_b)]
                pa = pd = pb = None
                for m in ev.get("markets") or []:
                    q = (m.get("question") or "").lower()
                    yp = _yes_price(m)
                    if yp is None:
                        continue
                    if "draw" in q:
                        pd = yp
                    elif any(f in q for f in a_forms):
                        pa = yp
                    elif any(f in q for f in b_forms):
                        pb = yp
                if pa is None or pd is None or pb is None:
                    return None
                s = pa + pd + pb
                if s <= 0:
                    return None
                return pa / s, pd / s, pb / s
    return None


def _elo_prior(team_a, team_b):
    """Model's match prior: raw eloratings.net + USA/Canada/Mexico host bonus, then
    pa = P(A | no draw) * (1 - dr), where dr = strength-aware draw rate. Same model used for
    the retrospective upsets panel — the disagreement is on the same footing."""
    base = WF._host_base()
    ra, rb = base.get(team_a), base.get(team_b)
    if ra is None or rb is None:
        return None
    pa_nd = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
    dr = EV._elo_draw_rate(ra - rb)
    return pa_nd * (1 - dr), dr, (1 - pa_nd) * (1 - dr)


def disagreements(today=None, window_days=3, top=6, min_gap=0.05):
    """Top-`top` upcoming matches by max |model − market| disagreement (per-outcome). Each entry
    records both priors so the panel can show the actual numbers, plus which outcome the gap
    is on (`a_win`/`draw`/`b_win`) and whether the model is over/under-pricing the market.
    Matches with no Polymarket market (or the model has no Elo for one side) are skipped."""
    today = today or dt.date.today()
    out = []
    for fix in _espn_upcoming(today, window_days):
        market = _fetch_current(fix["a"], fix["b"], fix["date"])
        if market is None:
            continue
        model = _elo_prior(fix["a"], fix["b"])
        if model is None:
            continue
        pa_x, pd_x, pb_x = market
        pa_m, pd_m, pb_m = model
        deltas = [("a_win", pa_m - pa_x), ("draw", pd_m - pd_x), ("b_win", pb_m - pb_x)]
        which, signed = max(deltas, key=lambda d: abs(d[1]))
        if abs(signed) < min_gap:
            continue
        out.append(dict(
            a=fix["a"], b=fix["b"], date=fix["date"],
            pa_m=round(pa_m, 4), pd_m=round(pd_m, 4), pb_m=round(pb_m, 4),
            pa_x=round(pa_x, 4), pd_x=round(pd_x, 4), pb_x=round(pb_x, 4),
            gap=round(abs(signed), 4), signed_gap=round(signed, 4), which=which,
        ))
    out.sort(key=lambda r: -r["gap"])
    return out[:top]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Cache the next-few-days WC matches' model↔market disagreements")
    ap.add_argument("--out", default=OUT_PATH)
    ap.add_argument("--window", type=int, default=3,
                    help="days ahead to scan (default: 3)")
    ap.add_argument("--top", type=int, default=6,
                    help="max disagreements to keep (default: 6)")
    ap.add_argument("--min-gap", type=float, default=0.05, dest="min_gap",
                    help="minimum |model − market| to surface (default: 0.05 = 5pp)")
    a = ap.parse_args(argv)
    rows = disagreements(window_days=a.window, top=a.top, min_gap=a.min_gap)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"as_of": dt.datetime.utcnow().isoformat() + "Z",
                   "window_days": a.window, "matches": rows}, f, indent=2)
    print(f"[upcoming] wrote {len(rows)} matches to {a.out}  (window={a.window}d, gap≥{a.min_gap})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
