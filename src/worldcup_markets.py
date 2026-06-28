"""
worldcup_markets.py — the FULL World Cup market surface (the nested ladder)
==============================================================================
Polymarket lists the 2026 World Cup as several MUTUALLY-CONSISTENT events, not just the
winner. Per team there is a nested ladder of "how far do you go":

    advance to knockout  >=  reach QF  >=  reach SF  >=  reach final  >=  win

and each LEVEL has a known number of SLOTS, so the prices in that level must sum to it:

    win = 1   final = 2   semifinal = 4   quarterfinal = 8   advance(knockout) = 32

That gives two zero-football-knowledge structural signals on REAL, separately-traded markets:
  - NESTED:    P(deeper round) must be <= P(shallower round) for each team (else riskless arb).
  - LEVEL-SUM: each level's prices should sum to its slot count (the per-level overround/vig).
Plus a CONTINENT aggregation check: P(continent wins) must equal the sum of its teams' win probs.

This 5-level ladder is 240 markets (vs the 48 winner-only we traded before) — 5x the breadth
for a market-neutral long/short book, and where the cleanest structural edges live.

⚠ Research/education only — not financial advice, not a solicitation, no capital invested.
"""
import os
import sys
import json

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import worldcup_live as WL          # noqa: E402  (FIELD, GROUPS_2026, _norm)
import consistency as C             # noqa: E402

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
# level -> (event slug, number of slots the prices must sum to), shallow -> deep
LADDER = [
    ("advance",  "world-cup-team-to-advance-to-knockout-stages", 32),
    ("reach_QF", "world-cup-nation-to-reach-quarterfinals",        8),
    ("reach_SF", "world-cup-nation-to-reach-semifinals",           4),
    ("reach_F",  "world-cup-nation-to-reach-final",                2),
    ("win",      "world-cup-winner",                               1),
]
CONTINENT_EVENT = "which-continent-will-win-the-world-cup"
# approximate calendar date each LEVEL's market is fully decided (2026 schedule; final Jul 19).
ROUND_RESOLVES = {"advance": "Jun 27", "reach_QF": "Jul 7", "reach_SF": "Jul 11",
                  "reach_F": "Jul 15", "win": "Jul 19"}

# the 48-team field -> continental confederation label (matches the continent market names)
_CONT = {
    "Europe": ["Czechia", "Switzerland", "Bosnia-Herzegovina", "Scotland", "Türkiye", "Germany",
               "Netherlands", "Sweden", "Belgium", "Spain", "France", "Norway", "Austria",
               "Portugal", "England", "Croatia"],
    "South America": ["Brazil", "Paraguay", "Ecuador", "Uruguay", "Argentina", "Colombia"],
    "North America": ["Mexico", "Canada", "Haiti", "USA", "Curaçao", "Panama"],
    "Africa": ["South Africa", "Morocco", "Ivory Coast", "Tunisia", "Egypt", "Cape Verde",
               "Senegal", "Algeria", "DR Congo", "Ghana"],
    "Asia": ["South Korea", "Qatar", "Australia", "Japan", "Iran", "Saudi Arabia", "Iraq",
             "Jordan", "Uzbekistan"],
    "Oceania": ["New Zealand"],
}
TEAM_CONTINENT = {WL._norm(t): c for c, ts in _CONT.items() for t in ts}

# emoji flag per team (keyed by the SAME normalized name) — purely cosmetic for the board.
_FLAG = {
    "Czechia": "🇨🇿", "Switzerland": "🇨🇭", "Bosnia-Herzegovina": "🇧🇦",
    "Scotland": "🏴\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f",
    "Türkiye": "🇹🇷", "Germany": "🇩🇪", "Netherlands": "🇳🇱", "Sweden": "🇸🇪", "Belgium": "🇧🇪",
    "Spain": "🇪🇸", "France": "🇫🇷", "Norway": "🇳🇴", "Austria": "🇦🇹", "Portugal": "🇵🇹",
    "England": "🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f", "Croatia": "🇭🇷",
    "Brazil": "🇧🇷", "Paraguay": "🇵🇾", "Ecuador": "🇪🇨", "Uruguay": "🇺🇾", "Argentina": "🇦🇷",
    "Colombia": "🇨🇴", "Mexico": "🇲🇽", "Canada": "🇨🇦", "Haiti": "🇭🇹", "USA": "🇺🇸",
    "Curaçao": "🇨🇼", "Panama": "🇵🇦", "South Africa": "🇿🇦", "Morocco": "🇲🇦", "Ivory Coast": "🇨🇮",
    "Tunisia": "🇹🇳", "Egypt": "🇪🇬", "Cape Verde": "🇨🇻", "Senegal": "🇸🇳", "Algeria": "🇩🇿",
    "DR Congo": "🇨🇩", "Ghana": "🇬🇭", "South Korea": "🇰🇷", "Qatar": "🇶🇦", "Australia": "🇦🇺",
    "Japan": "🇯🇵", "Iran": "🇮🇷", "Saudi Arabia": "🇸🇦", "Iraq": "🇮🇶", "Jordan": "🇯🇴",
    "Uzbekistan": "🇺🇿", "New Zealand": "🇳🇿",
}
TEAM_FLAG = {WL._norm(t): f for t, f in _FLAG.items()}

# Per-team reference info: (ISO 3166-1 code for the flag IMAGE, FIFA men's rank, World Cup titles).
# Ranks are an APPROXIMATE snapshot — update from inside.fifa.com/fifa-world-ranking/men (see
# FIFA_RANK_AS_OF). Titles are historical fact. Emoji flags don't render on Windows / many platforms,
# so the board uses real flag images keyed by these ISO codes (flagcdn.com), with the emoji as alt.
FIFA_RANK_AS_OF = "Jul 2025 (approx.)"
FIFA_RANKING_URL = "https://inside.fifa.com/fifa-world-ranking/men"
_INFO = {  # name: (iso, rank, titles)
    "Argentina": ("ar", 1, 3), "Spain": ("es", 2, 1), "France": ("fr", 3, 2), "England": ("gb-eng", 4, 1),
    "Brazil": ("br", 5, 5), "Portugal": ("pt", 6, 0), "Netherlands": ("nl", 7, 0), "Belgium": ("be", 8, 0),
    "Germany": ("de", 9, 4), "Croatia": ("hr", 10, 0), "Morocco": ("ma", 11, 0), "Colombia": ("co", 12, 0),
    "Uruguay": ("uy", 13, 2), "USA": ("us", 14, 0), "Mexico": ("mx", 15, 0), "Switzerland": ("ch", 16, 0),
    "Senegal": ("sn", 17, 0), "Japan": ("jp", 18, 0), "Iran": ("ir", 19, 0), "South Korea": ("kr", 20, 0),
    "Australia": ("au", 21, 0), "Ecuador": ("ec", 22, 0), "Austria": ("at", 23, 0), "Norway": ("no", 24, 0),
    "Sweden": ("se", 25, 0), "Egypt": ("eg", 26, 0), "Panama": ("pa", 27, 0), "Canada": ("ca", 28, 0),
    "Ivory Coast": ("ci", 29, 0), "Qatar": ("qa", 30, 0), "Algeria": ("dz", 31, 0), "Tunisia": ("tn", 32, 0),
    "Czechia": ("cz", 33, 0), "Scotland": ("gb-sct", 34, 0), "Paraguay": ("py", 35, 0), "Türkiye": ("tr", 36, 0),
    "Saudi Arabia": ("sa", 37, 0), "DR Congo": ("cd", 38, 0), "Uzbekistan": ("uz", 39, 0), "Iraq": ("iq", 40, 0),
    "Jordan": ("jo", 41, 0), "Ghana": ("gh", 42, 0), "South Africa": ("za", 43, 0), "Cape Verde": ("cv", 44, 0),
    "Bosnia-Herzegovina": ("ba", 45, 0), "Curaçao": ("cw", 46, 0), "Haiti": ("ht", 47, 0), "New Zealand": ("nz", 48, 0),
}
TEAM_INFO = {WL._norm(t): v for t, v in _INFO.items()}
FLAG_CDN = "https://flagcdn.com"


def flag(team_norm):
    """Emoji flag for a normalized team key ('' if unknown) — used as image alt / fallback."""
    return TEAM_FLAG.get(WL._norm(team_norm), "")


def info(team_norm):
    """(iso, rank, titles) for a team ('', None, 0 if unknown)."""
    return TEAM_INFO.get(WL._norm(team_norm), ("", None, 0))


# FIFA 3-letter team codes (for compact bracket nodes, matching the broadcast style).
_FIFA = {
    "Spain": "ESP", "Argentina": "ARG", "France": "FRA", "England": "ENG", "Brazil": "BRA",
    "Portugal": "POR", "Netherlands": "NED", "Belgium": "BEL", "Germany": "GER", "Croatia": "CRO",
    "Morocco": "MAR", "Colombia": "COL", "Uruguay": "URU", "USA": "USA", "Mexico": "MEX",
    "Switzerland": "SUI", "Senegal": "SEN", "Japan": "JPN", "Iran": "IRN", "South Korea": "KOR",
    "Australia": "AUS", "Ecuador": "ECU", "Austria": "AUT", "Norway": "NOR", "Sweden": "SWE",
    "Egypt": "EGY", "Panama": "PAN", "Canada": "CAN", "Ivory Coast": "CIV", "Qatar": "QAT",
    "Algeria": "ALG", "Tunisia": "TUN", "Czechia": "CZE", "Scotland": "SCO", "Paraguay": "PAR",
    "Türkiye": "TUR", "Saudi Arabia": "KSA", "DR Congo": "COD", "Uzbekistan": "UZB", "Iraq": "IRQ",
    "Jordan": "JOR", "Ghana": "GHA", "South Africa": "RSA", "Cape Verde": "CPV",
    "Bosnia-Herzegovina": "BIH", "New Zealand": "NZL", "Curaçao": "CUW", "Haiti": "HAI",
}
TEAM_CODE = {WL._norm(t): c for t, c in _FIFA.items()}


def code(team_norm):
    """FIFA 3-letter code for a normalized team key (uppercased name prefix if unknown)."""
    n = WL._norm(team_norm)
    return TEAM_CODE.get(n, (next((d for d in WL.FIELD if WL._norm(d) == n), n)[:3]).upper())


def flag_img(team_norm, size="20x15"):
    """A cross-platform flag IMAGE (flagcdn.com) — emoji flags don't render on Windows. `size`
    must be a flagcdn-supported dimension (e.g. 20x15, 24x18); the 2x retina source doubles it.
    Falls back to the emoji (as alt) and to nothing if the team is unknown."""
    iso, _r, _t = info(team_norm)
    em = flag(team_norm)
    if not iso:
        return em
    w, h = (int(x) for x in size.split("x"))
    return (f'<img class=flag src="{FLAG_CDN}/{w}x{h}/{iso}.png" '
            f'srcset="{FLAG_CDN}/{w*2}x{h*2}/{iso}.png 2x" '
            f'width={w} height={h} alt="{em}" loading=lazy decoding=async>')


def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (world-vs-model research)"})
    return s


_FIELD_NORMED = frozenset(WL._norm(t) for t in WL.FIELD)


def fetch_event_prices(slug, session=None):
    """{normalized groupItemTitle -> current YES price} for one Gamma event (one call).

    A RESOLVED outcome quotes exactly 0 (eliminated) or 1 (clinched). We KEEP both — including a
    resolved 0 — so a position on an eliminated team marks to 0 (a short then sits at MAX profit)
    instead of silently vanishing: an absent team reads as a blank "—" everywhere downstream
    (`worldcup_board._marked_rows`). Only a market with no quote at all (never traded, no
    outcomePrices and no lastTradePrice) is dropped — that's missing data, not a real 0.

    Phantom-team filter: Polymarket's "winner" event still carries a handful of pre-qualifier
    placeholder rows ("Team AG", "Team AH", etc.) left over from before CONCACAF / OFC / playoff
    paths resolved. They quote at 0 and showed up as ghost rows on the board. We drop anything
    not in the canonical 48-team FIELD."""
    s = session or _session()
    evs = s.get(f"{GAMMA}/events", params=dict(slug=slug), timeout=30).json()
    out = {}
    for m in (evs[0].get("markets", []) if evs else []):
        name = m.get("groupItemTitle") or (m.get("question") or "")
        if not name:
            continue
        nz = WL._norm(name)
        if nz not in _FIELD_NORMED:
            continue                                    # phantom / placeholder row (not a real team)
        op = m.get("outcomePrices")
        try:                                            # a real quote (incl. a resolved 0 or 1)
            yes = float(json.loads(op)[0]) if isinstance(op, str) else float(op[0])
        except Exception:                               # no outcomePrices -> fall back to last trade
            lt = m.get("lastTradePrice")
            if lt is None:
                continue                                # never traded, no price at all -> not a 0 mark
            yes = float(lt)
        out[nz] = yes
    return out


def fetch_ladder(session=None):
    """{level -> {team -> price}} for all five nested events (5 calls)."""
    s = session or _session()
    return {lvl: fetch_event_prices(slug, s) for lvl, slug, _ in LADDER}


def _downsample(series, k):
    """Evenly-spaced k points from a series (keeps the first and last), for a compact sparkline."""
    n = len(series)
    if n <= k:
        return [round(float(p), 4) for p in series]
    idx = [round(i * (n - 1) / (k - 1)) for i in range(k)]
    return [round(float(series[i]), 4) for i in idx]


def fetch_win_history(session=None, points=24, fidelity=1440):
    """Per-team WIN-price HISTORY for sparklines: {team_norm: [p, ...]} downsampled to ~`points`.
    Reads each team's YES CLOB token from the winner event, then one prices-history call per token.
    Returns {} on any failure (the board degrades to no sparkline) — never raises."""
    s = session or _session()
    try:
        evs = s.get(f"{GAMMA}/events", params=dict(slug="world-cup-winner"), timeout=30).json()
    except Exception:
        return {}
    out = {}
    for m in (evs[0].get("markets", []) if evs else []):
        name, tid = m.get("groupItemTitle") or "", m.get("clobTokenIds")
        if not name or not tid:
            continue
        try:
            yes = (json.loads(tid) if isinstance(tid, str) else tid)[0]
            h = s.get(f"{CLOB}/prices-history",
                      params=dict(market=yes, interval="max", fidelity=fidelity),
                      timeout=20).json().get("history", [])
            ser = [float(pt["p"]) for pt in h if "p" in pt]
        except Exception:
            continue
        if len(ser) >= 2:
            out[WL._norm(name)] = _downsample(ser, points)
    return out


def fetch_win_liquidity(session=None):
    """Per-team WIN-market tradeability gauge: {team_norm: {vol, liq}} in USD, from the winner
    event's CLOB fields (total traded volume + current order-book liquidity). {} on failure —
    never raises. A thin market (low liquidity) is one a punter can't actually trade at size."""
    s = session or _session()
    try:
        evs = s.get(f"{GAMMA}/events", params=dict(slug="world-cup-winner"), timeout=30).json()
    except Exception:
        return {}
    out = {}
    for m in (evs[0].get("markets", []) if evs else []):
        name = m.get("groupItemTitle") or ""
        if not name:
            continue

        def _f(k):
            try:
                return float(m.get(k) or 0)
            except (TypeError, ValueError):
                return 0.0
        out[WL._norm(name)] = dict(vol=round(_f("volumeClob")), liq=round(_f("liquidityClob")))
    return out


def level_sums(ladder):
    """Per-level sum of prices vs the known slot count (the per-level overround)."""
    out = {}
    for lvl, _slug, slots in LADDER:
        sm = float(sum(ladder.get(lvl, {}).values()))
        out[lvl] = dict(sum=round(sm, 3), slots=slots,
                        overround_pct=round((sm / slots - 1) * 100, 2) if slots else None,
                        n=len(ladder.get(lvl, {})))
    return out


def nested_scan(ladder, tol=0.005):
    """Riskless inconsistencies: P(deeper round) > P(shallower round) for a team.
    Returns [(team, shallow_level, deep_level, shallow_p, deep_p, gap), ...]."""
    order = [lvl for lvl, _s, _n in LADDER]                  # shallow -> deep
    viol = []
    for i in range(len(order) - 1):
        shallow, deep = ladder.get(order[i], {}), ladder.get(order[i + 1], {})
        for t in deep:
            if t in shallow and deep[t] > shallow[t] + tol:
                viol.append((t, order[i], order[i + 1], round(shallow[t], 3),
                             round(deep[t], 3), round(deep[t] - shallow[t], 3)))
    return sorted(viol, key=lambda v: -v[5])


def continent_check(win_prices, session=None):
    """The continent market must equal the SUM of its teams' win probs (an aggregation
    no-arb). Returns {continent: dict(market, team_sum, gap)} using de-vigged inputs."""
    s = session or _session()
    cont_mkt = fetch_event_prices(CONTINENT_EVENT, s)
    cont_mkt = C.devig(cont_mkt, "proportional") if cont_mkt else {}
    win = C.devig(win_prices, "proportional")
    team_sum = {}
    for t, p in win.items():
        c = TEAM_CONTINENT.get(t)
        if c:
            team_sum[c] = team_sum.get(c, 0.0) + p
    out = {}
    for c, mp in cont_mkt.items():
        ts = next((v for k, v in team_sum.items() if WL._norm(k) == WL._norm(c)), None)
        if ts is not None:
            out[c] = dict(market=round(mp, 3), team_sum=round(ts, 3), gap=round(mp - ts, 3))
    return out


# A flat per-trade cost (half the bid-ask) for netting displayed edges. Polymarket spreads are wide
# and depth thin (break-even capacity ~ $0), so a gross edge below the spread is not real. ~1
# cent is a typical tick. Disclosed, conservative; estimators stay GROSS — netting is a display knob.
HALF_SPREAD = 0.01


def net_edge(edge, cost=HALF_SPREAD):
    """Shrink a gross edge toward zero by the half-spread (never flips its sign): an edge smaller
    than the cost to trade it is reported as ~0 (not actionable)."""
    if edge > 0:
        return round(max(edge - cost, 0.0), 4)
    return round(min(edge + cost, 0.0), 4)


def book(ladder, power=1.15, cost=0.0):
    """Long/short edges across ALL levels. Within each level we de-vig to its slot count and
    apply the favorite-longshot shape correction, then compare to the price you'd PAY.
    Returns a flat list of dict(level, team, price, ours, gross, edge), most-mispriced first.
    `gross` is the raw model−price edge; `edge` is that net of the `cost` half-spread (default 0
    = gross, so estimator callers see the pure signal; the board passes HALF_SPREAD for display)."""
    rows = []
    for lvl, _slug, slots in LADDER:
        prices = ladder.get(lvl, {})
        if not prices:
            continue
        share = {t: max(p, 1e-9) ** power for t, p in prices.items()}
        z = sum(share.values()) or 1.0
        ours = {t: share[t] / z * slots for t in prices}    # sums to `slots`
        for t in prices:
            o = min(ours[t], 0.999)
            gross = round(o - prices[t], 4)
            rows.append(dict(level=lvl, team=t, price=round(prices[t], 4), ours=round(o, 4),
                             gross=gross, edge=net_edge(gross, cost) if cost else gross))
    return sorted(rows, key=lambda r: r["edge"])


def scan(power=1.15, top=10, session=None, verbose=True):
    """One-call live scan of the whole ladder: level overrounds, nested arbs, continent check,
    and the top long/short bets across 240 markets. Returns the structured result."""
    s = session or _session()
    ladder = fetch_ladder(s)
    res = dict(levels=level_sums(ladder), nested=nested_scan(ladder),
               continent=continent_check(ladder.get("win", {}), s), book=book(ladder, power))
    if verbose:
        print("=" * 76)
        print("WORLD CUP 2026 — full nested-ladder scan (zero football knowledge, research only)")
        print("=" * 76)
        print("per-level overround (prices should sum to the slot count):")
        for lvl, _s, slots in LADDER:
            L = res["levels"][lvl]
            print(f"   {lvl:9} {L['n']:>2} mkts  sum {L['sum']:>6} / {slots:<2} slots  "
                  f"overround {L['overround_pct']:+.1f}%")
        print(f"\nNESTED arbitrage candidates (P(deeper) > P(shallower) — riskless if real): "
              f"{len(res['nested'])}")
        for t, sh, dp, sp, dpp, gap in res["nested"][:6]:
            print(f"   {t:14} {dp}({dpp}) > {sh}({sp})   gap {gap:+.3f}")
        print("\nCONTINENT aggregation (market vs sum of its teams' win probs):")
        for c, d in sorted(res["continent"].items(), key=lambda kv: -abs(kv[1]["gap"]))[:6]:
            print(f"   {c:15} market {d['market']*100:5.1f}%  team-sum {d['team_sum']*100:5.1f}%  "
                  f"gap {d['gap']*100:+5.1f}%")
        bk = res["book"]
        print(f"\nTop SHORTS across all levels (overpriced):")
        for r in bk[:top]:
            print(f"   {r['edge']*100:+6.2f}%  {r['level']:9} {r['team']:14} pay {r['price']*100:5.1f}%")
        print(f"Top LONGS across all levels (underpriced):")
        for r in bk[::-1][:top]:
            print(f"   {r['edge']*100:+6.2f}%  {r['level']:9} {r['team']:14} pay {r['price']*100:5.1f}%")
        print(f"\nbook spans {len(bk)} markets across {len(LADDER)} levels.")
        print("⚠ research/education only — not financial advice, not a solicitation, no capital invested.")
    return res


if __name__ == "__main__":
    scan()
