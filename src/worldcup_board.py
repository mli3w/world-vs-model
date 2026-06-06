"""
worldcup_board.py — the public "World vs Model" board (a self-contained HTML page)
==============================================================================
Renders the 2026 World Cup like the classic one-page forecast table, but every probability is
shown TWICE: what the WORLD (de-vigged market) thinks vs what the MODEL thinks, plus the edge.
Below it: the paper BOOK — each ticket sized from a fixed $bankroll, conviction-weighted
(bigger model edge -> bigger stake), dollar-neutral, capped per trade. Plus the structural
tells (per-round hidden vig, riskless nested inconsistencies).

Zero football knowledge — only the market's own prices + structure (de-vig, favorite-longshot,
bracket coherence). One self-contained .html, no JS deps, fully shareable / screenshot-able.

⚠ Research/education only — not financial advice, not a solicitation, no capital invested.
Paper PnL is a simulation, not investment returns.

Usage:  python src/worldcup_board.py [--bankroll 1000] [--out worldcup_board.html]
"""
import os
import re
import sys
import html
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import worldcup_markets as WM       # noqa: E402
import worldcup_positions as WP     # noqa: E402
import worldcup_fundamental as WF   # noqa: E402  (the independent Elo model)
import wc_bracket as WB             # noqa: E402  (FIFA's official 2026 knockout slot table)
import consistency as C             # noqa: E402

LEVEL_LABEL = [("advance", "Advance"), ("reach_QF", "Reach QF"), ("reach_SF", "Reach SF"),
               ("reach_F", "Reach Final"), ("win", "Win Cup")]
LV_IDX = {lvl: i for i, (lvl, _l) in enumerate(LEVEL_LABEL)}   # chronological order for sorting
CORE_LEDGER = os.path.join("ledger", "wc_core.jsonl")     # zero-knowledge Buy & Hold (held)
LIVE_LEDGER = os.path.join("ledger", "wc_live.jsonl")     # zero-knowledge Active (matchday timeline)
ELO_CORE_LEDGER = os.path.join("ledger", "wc_elo_core.jsonl")   # informed (Elo) Buy & Hold
ELO_LIVE_LEDGER = os.path.join("ledger", "wc_elo_live.jsonl")   # informed (Elo) Active
SCORECARD = os.path.join("ledger", "scorecard.json")      # the public, resolved-out-of-sample record
RESULTS_PATH = os.path.join("ledger", "wc_results.json")  # played matches -> live Elo re-forecast

# the live site (GitHub Pages). Used for ABSOLUTE og:image / og:url — social scrapers (LinkedIn in
# particular) won't resolve a relative image, so the share card needs the full URL.
SITE_URL = "https://mli3w.github.io/world-vs-model"
AUTHOR_NAME = "Marcus Liew"
AUTHOR_URL = "https://www.linkedin.com/in/marcusliewjy/"

# Optional fan-poll backend (Cloudflare Worker, see poll-worker/). When set, the board renders a
# bottom-left "Who wins?" bubble that reads/writes the live tally; when empty, the bubble is omitted
# so nothing half-built ships. Set via env (WVM_POLL_ENDPOINT) or paste the workers.dev URL here.
POLL_ENDPOINT = os.environ.get("WVM_POLL_ENDPOINT", "").strip().rstrip("/")


def load_results(path=RESULTS_PATH):
    """Played-match results for the live re-forecast, or None if the file is absent (pre-tournament).
    Format: a JSON list of {a, b, ga, gb, stage?} (team names as in the field; stage defaults group)."""
    import json
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data or None
    except (FileNotFoundError, ValueError):
        return None
KICKOFF = dt.date(2026, 6, 11)                            # 2026 World Cup group-stage kickoff

# The brand mark: a split "world vs model" emblem — a teal half-ball (the market) meeting blue
# data bars (the model), ringed in violet (the "vs"). Inline SVG so the page stays self-contained.
# Favicon: a SIMPLIFIED echo of the Canva emblem (teal ball-half + blue ascending bars, circular)
# tuned to read at 16px in a browser tab — the detailed PNG emblem turns to mush that small.
BRAND_ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
              "%3Crect width='32' height='32' rx='7' fill='%23101a30'/%3E"
              "%3Cpath d='M16 5.2 A10.8 10.8 0 0 0 16 26.8 Z' fill='%233fd9a3'/%3E"
              "%3Cg fill='%234f7ce8'%3E"
              "%3Crect x='17.5' y='16.5' width='2.1' height='5' rx='.7'/%3E"
              "%3Crect x='20.5' y='13.25' width='2.1' height='8.25' rx='.7'/%3E"
              "%3Crect x='23.5' y='10' width='2.1' height='11.5' rx='.7'/%3E%3C/g%3E"
              "%3Cpath d='M16 5.2 A10.8 10.8 0 0 1 16 26.8' fill='none' stroke='%234f7ce8' "
              "stroke-width='1.4'/%3E%3C/svg%3E")

_BRAND_MARK_PNG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "assets", "wvm_mark_128.png")
_BRAND_MARK_CACHE = None


def _brand_mark():
    """The Canva brand EMBLEM (ball→bars) as a self-contained data-URI, read once from
    assets/wvm_mark_128.png. Falls back to the inline-SVG mark if the asset is missing — so the
    board still builds anywhere. We use the emblem alone (not the full lockup) so it stays legible
    small; the wordmark is rendered as live HTML text."""
    global _BRAND_MARK_CACHE
    if _BRAND_MARK_CACHE is None:
        try:
            import base64
            with open(_BRAND_MARK_PNG, "rb") as f:
                _BRAND_MARK_CACHE = "data:image/png;base64," + base64.b64encode(f.read()).decode()
        except OSError:
            _BRAND_MARK_CACHE = BRAND_ICON
    return _BRAND_MARK_CACHE


def _name(team):
    """Plain display name (no flag) for a normalized team key."""
    return next((d for d in WM.WL.FIELD if WM.WL._norm(d) == team), team)


def _disp(team):
    """Flag image + display name for a normalized team key (no link — safe to nest anywhere)."""
    return f'{WM.flag_img(team)} {html.escape(_name(team))}'


def _team_cell(team, link=True):
    """The board's team cell: flag + name (linked to the FIFA ranking source), plus the team's
    FIFA rank and World Cup titles as small badges."""
    _iso, rank, titles = WM.info(team)
    name = _disp(team)
    if link:
        name = (f'<a class=tl href="{WM.FIFA_RANKING_URL}" target=_blank rel="noopener noreferrer" '
                f'title="FIFA ranking source">{name}</a>')
    meta = (f'<span class=rk>#{rank}</span>' if rank else "")
    meta += (f'<span class=cup title="World Cup titles">★{titles}</span>' if titles else "")
    return f'<td class="team">{name} {meta}</td>'


def _econ(shares, entry):
    """The payoff envelope of one signed YES-share position settled at {0,1}.
    A binary bet can never lose more than its stake; max upside is the other leg."""
    pnl_yes, pnl_no = shares * (1 - entry), -shares * entry          # outcome 1 vs 0
    return dict(max_up=round(max(pnl_yes, pnl_no), 2),
                max_down=round(min(pnl_yes, pnl_no), 2),
                stake=round(abs(shares) * (entry if shares > 0 else 1 - entry), 2))


def _rationale(side, team, level, entry, model_p, edge, model="zk"):
    """Plain-English 'why we hold this' — names the signal behind the bet. `model` selects the
    zero-knowledge (structural) or the informed (Elo) explanation."""
    rnd = dict(LEVEL_LABEL)[level]
    if model == "elo":
        verb = "higher" if side == "LONG" else "lower"
        return (f"The market prices <b>{_disp(team)}</b> to {rnd} at <b>{entry*100:.1f}%</b>. Our "
                f"<b>informed Elo</b> model — real World Football Elo run through a simulated bracket, "
                f"<i>not</i> the market's prices — rates it {verb}, at <b>{model_p*100:.1f}%</b>, a "
                f"<b>{edge*100:+.1f}%</b> gap. Where a public-ratings model and a liquid market disagree "
                f"the market is usually the sharper one — the scorecard adjudicates.")
    bias = ("the market systematically <b>under</b>prices favorites — we buy the gap"
            if side == "LONG" else
            "the market systematically <b>over</b>prices longshots — we fade the gap")
    return (f"The market prices <b>{_disp(team)}</b> to {rnd} at <b>{entry*100:.1f}%</b>. "
            f"Our zero-knowledge model (favorite–longshot shape correction on the de-vigged "
            f"ladder) puts it at <b>{model_p*100:.1f}%</b> — a <b>{edge*100:+.1f}%</b> gap. "
            f"Because {bias}. No football knowledge is used: the edge is the price structure.")


def _book_risk(legs):
    """Book-level capital-at-risk and the theoretical PnL envelope. `legs` is a list of
    (shares, entry, locked) — locked!=None means already realized. The best/worst case is a
    LOOSE bound (outcomes are correlated), shown as the outer envelope of the book."""
    stake = best = worst = 0.0
    for shares, entry, locked in legs:
        if locked is not None:
            best += locked; worst += locked
            stake += abs(shares) * (entry if shares > 0 else 1 - entry)
        else:
            e = _econ(shares, entry)
            best += e["max_up"]; worst += e["max_down"]; stake += e["stake"]
    return dict(stake=round(stake, 2), best=round(best, 2), worst=round(worst, 2))


def _book_money(pills, legs):
    """A per-book money strip: the book's own deployed/PnL pills PLUS its capital-at-risk and the
    LOOSE max ↑/↓ envelope. Each of the three books holds different positions, so each gets its
    own strip inside its pane (a single shared strip would wrongly imply identical risk)."""
    r = _book_risk(legs)
    return (f'<div class=riskrow>{pills}'
            f'<span class=pill>capital at risk <b>${r["stake"]:,.0f}</b></span>'
            f'<span class=pill>book max ↑ <b class="pos">+${r["best"]:,.0f}</b></span>'
            f'<span class=pill>book max ↓ <b class="neg">${r["worst"]:+,.0f}</b></span></div>')


def _marked_rows(ladder, path):
    """Frozen tracked positions marked to the live ladder. Each row carries its ORIGINAL entry
    and a live mark, so the board shows real running PnL (realized once a market settles,
    unrealized while still open). Returns rows + book-level totals."""
    rows, realized, unreal = [], 0.0, 0.0
    for r in WP.load(path):
        cur = ladder.get(r["level"], {}).get(r["team"])
        if r.get("realized") is not None:                       # settled or closed at market
            pnl, status = r["realized"], r.get("status", "closed")
            realized += pnl
        elif cur is not None:                                   # still open -> mark to live
            pnl, status = round(r["shares"] * (cur - r["entry"]), 4), "open"
            unreal += pnl
        else:
            pnl, status = None, r.get("status", "open")
        rows.append(dict(level=r["level"], team=r["team"], shares=r["shares"], entry=r["entry"],
                         cur=cur, pnl=pnl, status=status, note=r.get("note", "")))
    tot = dict(realized=round(realized, 2), unrealized=round(unreal, 2),
               total=round(realized + unreal, 2), n=len(rows),
               n_open=sum(1 for r in rows if r["status"] == "open"))
    return rows, tot


def _live_timeline(path):
    """Matchday changelog for the recycled book: per date, positions opened and settled, the
    realized PnL of that step and the running cumulative. Built from the ledger's dates."""
    steps = {}
    for r in WP.load(path):
        s = steps.setdefault(r.get("date"), dict(date=r.get("date"), opened=0, settled=0, realized=0.0))
        s["opened"] += 1
        rd = r.get("resolved_at")
        if rd:
            t = steps.setdefault(rd, dict(date=rd, opened=0, settled=0, realized=0.0))
            t["settled"] += 1
            t["realized"] += r.get("realized") or 0.0
    out = sorted((s for s in steps.values() if s["date"]), key=lambda s: s["date"])
    cum = 0.0
    for s in out:
        cum += s["realized"]
        s["realized"], s["cum"] = round(s["realized"], 2), round(cum, 2)
    return out


def _scorecard_tiles(path=SCORECARD):
    """Track-record tiles for the credibility strip. Reads the resolved-out-of-sample scorecard;
    pre-tournament (nothing resolved yet) it shows an honest 'armed, not yet scored' state."""
    try:
        import json as _json
        with open(path) as f:
            d = _json.load(f)
    except Exception:
        return [("track record", "arming", "scores after kickoff")]
    n_res, n_tot = d.get("n_resolved", 0), d.get("n_total", 0)
    if not n_res:
        return [("claims registered", str(n_tot), "timestamped, falsifiable"),
                ("resolved so far", "0", "skill is scored, not claimed"),
                ("status", "PRE-KICKOFF", "scorecard arms Jun 11")]
    ov = d.get("overall", {})
    hit, lift, brier = ov.get("hit_rate"), ov.get("lift"), ov.get("brier")
    return [("hit rate", f"{hit*100:.0f}%" if hit is not None else "—", f"{n_res} resolved"),
            ("lift vs chance", f"{lift:+.2f}x" if lift is not None else "—", "skill over base rate"),
            ("brier score", f"{brier:.3f}" if brier is not None else "—", "lower is better")]


def _kickoff_note(today=None):
    """Countdown / live-state note so the page never looks dead pre-tournament."""
    days = (KICKOFF - (today or dt.date.today())).days
    if days > 0:
        return f'Kicks off in <b>{days}</b> day{"s" if days != 1 else ""} · Jun 11, 2026'
    return '<b>Tournament underway</b> · markets resolving' if days < 0 else '<b>Kicks off today</b>'


# the fan/punter calendar — the official 2026 start date of each stage (group stage Jun 11–27,
# R32 Jun 28–Jul 3, R16 Jul 4–7, QF Jul 9–11, SF Jul 14–15, final Jul 19).
KEY_DATES = [("Jun 11", "Group stage", "tournament opens"),
             ("Jun 28", "Round of 32", "knockouts begin"),
             ("Jul 9", "Quarter-finals", "last 8"),
             ("Jul 14", "Semi-finals", "last 4"),
             ("Jul 19", "Final", "champion crowned")]


def _keydates(today=None):
    """A compact tournament timeline a fan/punter can scan: the key dates + a kickoff countdown."""
    days = (KICKOFF - (today or dt.date.today())).days
    badge = (f'<span class=kd-cd>{days} days to kickoff</span>' if days > 0
             else '<span class=kd-cd>underway</span>' if days < 0 else '<span class=kd-cd>today!</span>')
    pills = "".join(f'<div class=kd><span class=kdd>{d}</span>'
                    f'<span class=kdt>{t}</span><span class=kds>{s}</span></div>'
                    for d, t, s in KEY_DATES)
    return (f'<div class=kdates><div class=kdh>How the tournament unfolds {badge}</div>'
            f'<div class=kdrow>{pills}</div></div>')


FIFA_SCHEDULE_URL = ("https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/"
                     "scores-fixtures")
# a valid 4-team round-robin rotation (each team plays once per matchday) -> the three matchdays
# FIFA's official group matchday template (0-indexed slots): MD1 1v2 & 3v4, MD2 1v3 & 4v2,
# MD3 4v1 & 2v3 (per the FIFA "Schedule by group", e.g. the opener Mexico(A1) v South Africa(A2)).
_RR_MATCHDAYS = [[(0, 1), (2, 3)], [(0, 2), (3, 1)], [(3, 0), (1, 2)]]


def _fixtures(groups):
    """Group-stage matchups by matchday, derived from the VERIFIED draw (the pairings are knowable;
    exact kickoff times & venues are on FIFA, linked). Knockout fixtures depend on results."""
    cards = []
    for g, teams in groups.items():
        if len(teams) < 4:
            continue
        mds = []
        for mi, pairs in enumerate(_RR_MATCHDAYS, 1):
            fx = "".join(
                f'<div class=fx>{WM.flag_img(teams[i])}<span class=fxc>{WM.code(teams[i])}</span>'
                f'<span class=fxv>v</span><span class=fxc>{WM.code(teams[j])}</span>'
                f'{WM.flag_img(teams[j])}</div>' for i, j in pairs)
            mds.append(f'<div class=fxmd><span class=fxmdl>MD{mi}</span>{fx}</div>')
        cards.append(f'<div class=fxcard><div class=gh>Group {g}</div>{"".join(mds)}</div>')
    return (
        f'<h2 id=fixtures>Group fixtures <span class=sub>— who plays whom, from the draw</span></h2>'
        f'<p class=note>Every group\'s matchups by matchday, straight from the verified 2026 draw. '
        f'Exact <b>kickoff times &amp; venues</b> live on '
        f'<a href="{FIFA_SCHEDULE_URL}" target=_blank rel="noopener noreferrer">FIFA ↗</a>; knockout '
        f'fixtures depend on results, so they appear once the groups resolve.</p>'
        f'<div class=fxgrid>{"".join(cards)}</div>')


def _devig_to_slots(prices, slots):
    s = sum(prices.values()) or 1.0
    return {t: p / s * slots for t, p in prices.items()}


def _pctf(p, dp=1):
    """Probability as a %, but never print a false-certain 100% / 0% — a forecast is never sure."""
    if p is None:
        return "·"
    if p > 0.999:
        return ">99.9%"
    if 0 < p < 0.001:
        return "<0.1%"
    return f"{p*100:.{dp}f}%"


def sized_book(ladder, bankroll=1000.0, power=1.15, cap_frac=0.15, top=14, rows=None,
               cost=WM.HALF_SPREAD):
    """Conviction-weighted, dollar-neutral paper book. Each side gets bankroll/2 of capital,
    allocated by |edge| (capped per trade). Returns tickets with stake $ (capital at risk),
    shares, entry price and edge. Edges are NET of the `cost` half-spread, so a gross edge below
    the spread is sized to ~0 (we only act on edges that clear the cost to trade them). `rows`
    (worldcup_markets.book format) lets a caller size an arbitrary edge source — e.g. the
    independent fundamental model — instead of WM.book; such rows are assumed already net."""
    bk = rows if rows is not None else WM.book(ladder, power=power, cost=cost)
    out = []
    for side, rows in (("LONG", [r for r in bk if r["edge"] > 0][::-1][:top]),
                       ("SHORT", [r for r in bk if r["edge"] < 0][:top])):
        w = sum(abs(r["edge"]) for r in rows) or 1.0
        cap = bankroll / 2 * cap_frac
        for r in rows:
            stake = min(bankroll / 2 * abs(r["edge"]) / w, cap)       # capital at risk
            cost_per_share = r["price"] if side == "LONG" else (1 - r["price"])
            shares = stake / max(cost_per_share, 1e-3) * (1 if side == "LONG" else -1)
            out.append(dict(side=side, level=r["level"], team=r["team"], entry=r["price"],
                            edge=r["edge"], stake=round(stake, 2), shares=round(shares, 1)))
    return sorted(out, key=lambda t: -t["stake"])


def _cell(p, lo=0.0, hi=1.0, cls=""):
    """A color-graded probability cell (green = high). `cls` lets the caller tag a column (e.g.
    'midcol' for the mid-ladder rounds we hide on narrow screens)."""
    c = f' class="{cls}"' if cls else ""
    if p is None:
        return f'<td class="na {cls}" data-s="-1">·</td>'
    f = max(0.0, min(1.0, (p - lo) / (hi - lo + 1e-9)))
    bg = f"background:rgba(63,217,163,{0.09 + 0.62*f:.2f})"   # teal gradient = the market/world
    return f'<td{c} style="{bg}">{_pctf(p)}</td>'            # capped display (no false 100%/0%)


def _fundamental_section(ladder, fundamental, bankroll):
    """The INDEPENDENT Elo model vs the market: an Elo explanation + links, the biggest
    disagreements (model vs de-vigged market), and one sized fundamental book. Heavy caveats —
    a public-ratings model is usually less sharp than a liquid market (big disagreement != edge)."""
    dis = WF.disagreements(ladder, level="win", model=fundamental, top=3)
    cards = "".join(
        f'<div class="card {"long" if ed > 0 else "short"}">'
        f'<div class="cv">{"MODEL HIGHER" if ed > 0 else "MODEL LOWER"}</div>'
        f'<div class="ct">{_disp(t)}</div><div class=cr>Win the Cup</div>'
        f'<div class="cm"><span>market <b>{mk*100:.1f}%</b></span><span>model <b>{mo*100:.1f}%</b></span></div>'
        f'<div class="ce {"pos" if ed > 0 else "neg"}">{ed*100:+.1f}% gap</div></div>'
        for t, mo, mk, ed in dis)
    return (
        f'<p class=note>The <b>informed</b> contender: an <b>independent</b> forecast (not derived from the '
        f'market). The engine simulates the verified bracket on real per-team '
        f'<a href="{WF.ELO_SOURCE_URL}" target=_blank rel="noopener noreferrer">World Football Elo</a> '
        f'ratings (<a href="{WF.ELO_REF_URL}" target=_blank rel="noopener noreferrer">what is Elo?</a>, '
        f'as of {WF.ELO_AS_OF}). The group stage trusts Elo as-is; the knockout gets a disclosed '
        f'<b>×{WF.KO_SHRINK} shrink</b> (single-elimination is coin-flippier than match-Elo). The three '
        f'<b>2026 co-hosts</b> get a <b>+{int(WF.HOST_BONUS)} Elo</b> home bump, and every run draws each '
        f'team\'s rating from a <b>±{int(WF.RATING_SD)} Elo</b> uncertainty band — so the favorite sits '
        f'at a plausible ~16% and we don\'t print false-precision 0%/100% for minnows and giants. All '
        f'disclosed priors, <b>not</b> tuned to the market. <b>It can genuinely disagree with the crowd</b> '
        f'— but a public-ratings model is usually <b>less sharp</b> than a liquid market, so a big gap is '
        f'more likely the model being cruder than the market being wrong. Its two books (Buy &amp; Hold / '
        f'Active) sit alongside the zero-knowledge ones below; the scorecard adjudicates.</p>'
        f'<div class=cards>{cards}</div>')


def _outcome_map(fundamental, positions, groups, n_sims=20000):
    """The informed (Elo) model's most-likely outcome: projected group standings (each team's
    finishing rank + advance %) and a knockout pyramid (most-likely QF-8 / SF-4 / Finalists /
    Champion). Probabilities are the MODEL's, not the market's."""
    nz = WM.WL._norm
    adv = fundamental.get("advance", {})
    gcards = []
    ranked_by_group = {}
    for g, teams in groups.items():
        ranked = sorted(teams, key=lambda t: sum(i * p for i, p in enumerate(
            positions.get(nz(t), [0, 0, 0, 1]))))          # by expected finishing position
        ranked_by_group[g] = ranked
        trs = []
        for i, t in enumerate(ranked):
            cls = "q" if i < 2 else ("m" if i == 2 else "o")
            trs.append(f'<tr class="{cls}"><td class=gp>{i+1}</td>'
                       f'<td class="team">{_disp(t)}</td><td>{_pctf(adv.get(nz(t), 0), 0)}</td></tr>')
        gcards.append(f'<div class=gcard><div class=gh>Group {g}</div>'
                      f'<table class=gt><tbody>{"".join(trs)}</tbody></table></div>')

    # ---- the knockout BRACKET: the REAL, OFFICIAL 2026 fixtures. The model's projected group
    #      standings are poured into FIFA's published slot table (src/wc_bracket.py: the 16 fixed
    #      Round-of-32 matches #73-88 + the 495-row best-third contingency), then the stronger side
    #      advances each round. So the *structure* is the actual R32 -> R16 -> QF -> SF -> Final; only
    #      the *placement* is the model's projection. No matchup is invented. ----
    win = fundamental.get("win", {})
    adv_p = fundamental.get("advance", {})
    r16_p = fundamental.get("reach_R16", {})

    def _strength(team):                                       # model strength, ties broken finely
        n = nz(team)
        return (win.get(n, 0.0), adv_p.get(n, 0.0), r16_p.get(n, 0.0))

    br = WB.resolve(ranked_by_group, _strength)
    rounds = br["rounds"]                                      # [R32(32), R16(16), QF(8), SF(4), F(2), champ(1)]
    LV = ("advance", "reach_R16", "reach_QF", "reach_SF", "reach_F")  # tooltip prob per round column

    def _node(team, level):
        if not team:
            return '<div class="bn bne">&mdash;</div>'
        p = fundamental.get(level, {}).get(nz(team), 0)
        return (f'<div class=bn title="{html.escape(_name(team))} · {p*100:.0f}% to reach this round">'
                f'{WM.flag_img(team)}<span class=bc>{WM.code(team)}</span></div>')

    def _col(teams, level):
        return f'<div class=bcol>{"".join(_node(t, level) for t in teams)}</div>'

    def _half(level, sk):                                      # left half = top of the column, right = bottom
        col = rounds[level]
        h = len(col) // 2
        return col[:h] if sk == "L" else col[h:]

    champ = br["champ"]
    champ_node = (f'<div class=bchamp>{WM.flag_img(champ, "40x30")}'
                  f'<div class=bcn>{html.escape(_name(champ))}</div>'
                  f'<div class=bct>🏆 champion · {win.get(nz(champ), 0)*100:.0f}%</div></div>' if champ else "")
    bracket = (
        '<div class=bwrap><div class=blabels>'
        + "".join(f'<span>{x}</span>' for x in
                  ["R32", "R16", "QF", "SF", "Final", "Champion", "Final", "SF", "QF", "R16", "R32"]) + '</div>'
        '<div class=bracket>'
        + "".join(_col(_half(i, "L"), LV[i]) for i in range(5))
        + f'<div class="bcol bmid">{champ_node}</div>'
        + "".join(_col(_half(i, "R"), LV[i]) for i in range(4, -1, -1))
        + '</div></div>')
    return (
        f'<h2 id=outcome>Most likely outcome '
        f'<span class=sub>— the <span class=eloc>informed</span> model\'s projection</span></h2>'
        f'<p class=note>What the informed Elo model expects, from <b>{n_sims//1000}k simulations</b> of the '
        f'verified bracket — these are the <b>model\'s</b> probabilities, not the market\'s. '
        f'Projected group order is by the model; <span class=qd></span> top-2 qualify, '
        f'<span class=md></span> 3rd may sneak through as a best-third.</p>'
        f'<h3>Projected group stage <span class=sub>(advance %)</span></h3>'
        f'<div class=groups>{"".join(gcards)}</div>'
        f'<h3>Projected knockout bracket <span class=sub>— the model\'s projected standings poured into'
        f' FIFA\'s official Round-of-32 slots (real fixtures, model placement)</span></h3>{bracket}'
        f'<div class=mhint>↔ swipe the bracket sideways to follow the path to the final</div>')


def _poll_widget(endpoint):
    """Bottom-left 'Who wins the World Cup?' fan-poll bubble. Renders only when a Cloudflare-Worker
    endpoint is configured (see poll-worker/). Reuses the page's WVM team data to overlay the crowd
    vote against the model and the market. Non-binding, not betting; cookieless, one soft vote/IP."""
    if not endpoint:
        return ""
    blob = r'''
<style>
 #wvp{position:fixed;left:16px;bottom:16px;z-index:30;font-family:inherit}
 .wvp-pill{display:flex;align-items:center;gap:6px;border:1px solid var(--line2);background:var(--panel);
   color:var(--ink);border-radius:22px;padding:9px 14px;font-size:13px;cursor:pointer;box-shadow:0 6px 22px rgba(0,0,0,.28)}
 .wvp-pill:hover{transform:translateY(-1px)} .wvp-pill span{color:var(--ink3)}
 .wvp-card{position:fixed;left:16px;bottom:16px;width:320px;max-width:calc(100vw - 32px);background:var(--panel);
   border:1px solid var(--line2);border-radius:14px;padding:13px 14px;box-shadow:0 14px 40px rgba(0,0,0,.4)}
 .wvp-hd{display:flex;justify-content:space-between;align-items:center;font-size:14px;margin-bottom:3px}
 .wvp-x{background:none;border:none;color:var(--ink3);font-size:18px;cursor:pointer;line-height:1}
 .wvp-sub{font-size:11px;color:var(--ink3);margin-bottom:10px;line-height:1.4}
 .wvp-quick{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px}
 .wvp-q{display:flex;align-items:center;gap:5px;border:1px solid var(--line2);background:var(--bg);color:var(--ink);
   border-radius:8px;padding:5px 8px;font-size:12px;cursor:pointer}
 .wvp-q.sel{border-color:var(--model);background:var(--panel2)}
 .wvp-q img{width:18px;height:13px;border-radius:2px}
 .wvp-sel{width:100%;background:var(--bg);color:var(--ink);border:1px solid var(--line2);border-radius:8px;
   padding:7px 8px;font-size:12px;margin-bottom:8px}
 .wvp-row{display:flex;gap:8px;align-items:center}
 .wvp-vote{flex:1;background:var(--model);color:#fff;border:none;border-radius:8px;padding:8px;font-size:13px;
   font-weight:700;cursor:pointer;opacity:.5;pointer-events:none}
 .wvp-vote.on{opacity:1;pointer-events:auto} .wvp-link{background:none;border:none;color:var(--ink3);
   font-size:12px;cursor:pointer;text-decoration:underline}
 .wvp-res{margin-top:4px}
 .wvp-bar{display:flex;align-items:center;gap:7px;margin:6px 0;font-size:12px}
 .wvp-bar img{width:18px;height:13px;border-radius:2px;flex:none}
 .wvp-bc{font-weight:700;width:34px;flex:none;color:var(--ink2)}
 .wvp-track{flex:1;height:16px;background:var(--bg);border:1px solid var(--line);border-radius:5px;position:relative;overflow:hidden}
 .wvp-fill{height:100%;background:#f0bf49;border-radius:4px}
 .wvp-tick{position:absolute;top:-2px;width:2px;height:20px}
 .wvp-pc{width:34px;flex:none;text-align:right;font-weight:700;color:#f0bf49}
 .wvp-foot{font-size:10.5px;color:var(--ink3);margin-top:9px;display:flex;justify-content:space-between;align-items:center}
 .wvp-foot a{color:var(--ink3)} .wvp-key{font-size:10px;color:var(--ink3);margin:2px 0 0}
 .wvp-key b{font-weight:700}
 @media(max-width:600px){.wvp-card{width:calc(100vw - 32px)}}
</style>
<div id="wvp">
 <button class="wvp-pill" id="wvp-pill">&#128499;&#65039; <b>Who wins?</b> <span>vote</span></button>
 <div class="wvp-card" id="wvp-card" hidden>
  <div class="wvp-hd"><b>Who wins the World Cup 2026?</b><button class="wvp-x" id="wvp-x" aria-label="close">&times;</button></div>
  <div class="wvp-sub">A non-binding fan poll &mdash; not betting. See how the crowd lines up against the model and the market.</div>
  <div id="wvp-pick">
   <div class="wvp-quick" id="wvp-quick"></div>
   <select class="wvp-sel" id="wvp-sel"><option value="">&mdash; or pick any of the 48 &mdash;</option></select>
   <div class="wvp-row"><button class="wvp-vote" id="wvp-vote">Vote</button><button class="wvp-link" id="wvp-see">results &rarr;</button></div>
  </div>
  <div class="wvp-res" id="wvp-res" hidden></div>
  <div class="wvp-foot"><span id="wvp-total"></span><a href="methodology.html">how this works</a></div>
 </div>
</div>
<script>
(function(){
 var EP="__ENDPOINT__"; if(!EP) return;
 var T=(window.WVM||[]).map(function(t){return {d:t.d,c:t.c,iso:t.iso,mk:t.mk||0,mdl:(t.elo!=null?t.elo:t.zk)||0};});
 if(!T.length) return;
 var META={}; T.forEach(function(t){META[t.d]=t;});
 var byMkt=T.slice().sort(function(a,b){return b.mk-a.mk;});
 var $=function(id){return document.getElementById(id);};
 var pill=$("wvp-pill"),card=$("wvp-card"),pick=$("wvp-pick"),res=$("wvp-res"),sel=$("wvp-sel"),voteB=$("wvp-vote");
 var chosen=null, voted=null;
 try{voted=localStorage.getItem("wvm-vote-2026");}catch(e){}
 function flag(iso){return "https://flagcdn.com/20x15/"+iso+".png";}
 byMkt.slice(0,6).forEach(function(t){
  var b=document.createElement("button"); b.className="wvp-q";
  b.innerHTML='<img src="'+flag(t.iso)+'" alt=""> '+t.c;
  b.onclick=function(){choose(t.d);}; b.setAttribute("data-d",t.d); $("wvp-quick").appendChild(b);
 });
 byMkt.forEach(function(t){var o=document.createElement("option");o.value=t.d;o.textContent=t.d;sel.appendChild(o);});
 sel.onchange=function(){choose(sel.value);};
 function choose(d){
  chosen=d||null;
  document.querySelectorAll(".wvp-q").forEach(function(q){q.classList.toggle("sel",q.getAttribute("data-d")===d);});
  if(sel.value!==(d||"")) sel.value=d||"";
  voteB.classList.toggle("on",!!chosen);
 }
 function show(el,on){el.hidden=!on;}
 function open(){show(card,true);show(pill,false); if(voted){load(true);} }
 function close(){show(card,false);show(pill,true);}
 pill.onclick=open; $("wvp-x").onclick=close; $("wvp-see").onclick=function(){load(true);};
 voteB.onclick=function(){ if(!chosen) return; voteB.classList.remove("on"); voteB.textContent="Voting...";
  fetch(EP+"/vote",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({team:chosen})})
   .then(function(r){return r.json();}).then(function(d){
     try{localStorage.setItem("wvm-vote-2026",chosen);}catch(e){} voted=chosen; render(d);
   }).catch(function(){voteB.textContent="Vote";voteB.classList.add("on");res.hidden=false;res.innerHTML='<div class="wvp-key">Could not reach the poll &mdash; try again later.</div>';});
 };
 function load(force){ fetch(EP+"/results").then(function(r){return r.json();}).then(render)
   .catch(function(){show(res,true);res.innerHTML='<div class="wvp-key">Could not load results yet.</div>';}); }
 function render(d){
  show(pick,false); show(res,true);
  var counts=d.counts||{}, total=d.total||0;
  var rows=Object.keys(counts).map(function(k){
    var m=META[k]||{c:k.slice(0,3).toUpperCase(),iso:"",mk:0,mdl:0};
    return {d:k, share:(total?counts[k]/total*100:0), mdl:m.mdl||0, mk:m.mk||0, c:m.c, iso:m.iso};
  }).sort(function(a,b){return b.share-a.share;}).slice(0,8);
  // crowd share, model win% and market win% are all "P(this team wins)" — put them on one axis
  var scaleMax=5; rows.forEach(function(r){scaleMax=Math.max(scaleMax,r.share,r.mdl,r.mk);});
  var sc=function(v){return Math.max(0,Math.min(100,v/scaleMax*100));};
  var html=rows.map(function(r){
    return '<div class="wvp-bar"><img src="'+flag(r.iso)+'" alt=""><span class="wvp-bc">'+r.c+'</span>'+
      '<span class="wvp-track"><span class="wvp-fill" style="width:'+sc(r.share)+'%"></span>'+
      '<span class="wvp-tick" style="left:'+sc(r.mdl)+'%;background:var(--model)" title="model '+Math.round(r.mdl)+'%"></span>'+
      '<span class="wvp-tick" style="left:'+sc(r.mk)+'%;background:var(--world)" title="market '+Math.round(r.mk)+'%"></span>'+
      '</span><span class="wvp-pc">'+Math.round(r.share)+'%</span></div>';
  }).join("") || '<div class="wvp-key">No votes yet &mdash; be the first.</div>';
  res.innerHTML=html+'<div class="wvp-key">All three are <b>P(wins the cup)</b>: <b style="color:#f0bf49">&#9632; crowd</b> <b style="color:var(--model)">&#9632; model</b> <b style="color:var(--world)">&#9632; market</b></div>';
  $("wvp-total").textContent=(total||0)+" vote"+(total===1?"":"s")+(voted?" · you picked "+voted:"");
 }
 if(voted){ /* returning voter: pill still shows; results load on open */ }
})();
</script>
'''
    return blob.replace("__ENDPOINT__", endpoint)


def build_html(ladder=None, bankroll=1000.0, power=1.15, core_path=CORE_LEDGER,
               live_path=LIVE_LEDGER, fundamental=None, positions=None, history=None, liquidity=None,
               elo_core_path=ELO_CORE_LEDGER, elo_live_path=ELO_LIVE_LEDGER):
    ladder = ladder or WM.fetch_ladder()
    history = history or {}                                    # {team_norm: [win-price series]}
    liquidity = liquidity or {}                               # {team_norm: {vol, liq}} (USD)
    levels = WM.level_sums(ladder)
    nested = WM.nested_scan(ladder)
    # de-vigged market probability per level, and the model (favorite-longshot) win prob
    mkt = {lvl: _devig_to_slots(ladder.get(lvl, {}), slots) for lvl, _s, slots in WM.LADDER}
    model_win = C.coherent_forecast(ladder.get("win", {}), method="power", power=power)
    teams = sorted(ladder.get("win", {}), key=lambda t: mkt["win"].get(t, 0), reverse=True)
    book = sized_book(ladder, bankroll=bankroll, power=power)
    half_spread_c = WM.HALF_SPREAD * 100                       # disclosed half-spread, in cents
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ---- the board table: per team, market ladder + Win market|model|edge ----
    # the MODEL column can switch between the zero-knowledge (structural) and informed (Elo) models;
    # each row carries both values as data-attrs and a toggle swaps them client-side.
    fwin = fundamental.get("win", {}) if fundamental else {}
    rows = []
    for t in teams:
        cells = "".join(_cell(mkt[lvl].get(t), 0, 1,
                               cls="midcol" if lvl in ("reach_QF", "reach_SF", "reach_F") else "")
                         for lvl, _s, _n in WM.LADDER)
        mw, md = mkt["win"].get(t, 0), model_win.get(t, 0)
        edge = md - mw
        ecls = "pos" if edge > 0.003 else ("neg" if edge < -0.003 else "")
        me = fwin.get(t)                                  # informed (Elo) win prob, if available
        de = (me - mw) if me is not None else None
        rows.append(
            f'<tr data-team="{html.escape(_name(t).lower())}">{_team_cell(t)}{cells}'
            f'<td class="mk">{mw*100:.1f}%</td>'
            f'<td class="md" data-zk="{md:.4f}"{f" data-elo={me:.4f}" if me is not None else ""}>{md*100:.1f}%</td>'
            f'<td class="edge {ecls}" data-ze="{edge:.4f}"'
            f'{f" data-ee={de:.4f}" if de is not None else ""}>{edge*100:+.1f}%</td></tr>')

    head = "".join(f'<th data-c={i+1}'
                   f'{" class=midcol" if lv in ("reach_QF", "reach_SF", "reach_F") else ""}>{lbl}</th>'
                   for i, (lv, lbl) in enumerate(LEVEL_LABEL))
    # two-row header: a group banner makes explicit which columns are the WORLD (Polymarket,
    # de-vigged) and which is the MODEL. Leaf headers carry data-c => click to sort.
    board = (f'<table class="board sortable"><thead>'
             f'<tr><th class="team l" rowspan=2 data-c=0>Team</th>'
             f'<th colspan=5 class="grp world">Polymarket — de-vigged to round slots (what the WORLD prices)</th>'
             f'<th colspan=2 class="grp model">Win the Cup</th>'
             f'<th rowspan=2 data-c=8>Edge<br><span class=sub>model−world</span></th></tr>'
             f'<tr>{head}<th class="mkh" data-c=6>market<br><span class=sub>world</span></th>'
             f'<th class="mdh" data-c=7>model<br><span class=sub id=modelhdr>zero-knowledge</span></th></tr>'
             f'</thead><tbody>{"".join(rows)}</tbody></table>')
    # the model switch (only when the informed Elo model is present)
    model_toggle = (
        '<div class=mtog><span class=mtl>Model:</span>'
        '<button class="mb on" id=mb-zk onclick="setModel(\'zk\')">⚙ Zero-knowledge</button>'
        '<button class="mb pulse" id=mb-elo onclick="setModel(\'elo\')">🧮 Informed · Elo</button>'
        '<span class=hint>👆 tap to switch model</span></div>') if fundamental else ""

    # ---- per-team data for the quick-lookup popup: market vs both models, the informed model's
    #      ROUTE (reach-each-round %), and the WIN-price sparkline series ----
    import json as _json
    _route_levels = [("advance", "adv"), ("reach_QF", "qf"), ("reach_SF", "sf"),
                     ("reach_F", "f"), ("win", "win")]

    def _route(t):
        if not fundamental:
            return None
        r = {k: round(fundamental.get(lvl, {}).get(t, 0) * 100) for lvl, k in _route_levels}
        return r if any(r.values()) else None

    team_data = [dict(n=_name(t).lower(), d=_name(t), c=WM.code(t), iso=WM.info(t)[0],
                      mk=round(mkt["win"].get(t, 0) * 100, 1), zk=round(model_win.get(t, 0) * 100, 1),
                      elo=(round(fwin[t] * 100, 1) if t in fwin else None),
                      route=_route(t),
                      hist=[round(p * 100, 1) for p in history.get(t, [])],
                      vol=liquidity.get(t, {}).get("vol"), liq=liquidity.get(t, {}).get("liq"))
                 for t in teams]
    team_js = _json.dumps(team_data)

    # ---- the per-round hidden vig ----
    vig = "".join(
        f'<tr><td class="team" data-s="{LV_IDX[lvl]}">{lbl}</td><td>{levels[lvl]["sum"]}</td><td>{slots}</td>'
        f'<td class="{"neg" if levels[lvl]["overround_pct"]>8 else ""}">'
        f'{levels[lvl]["overround_pct"]:+.1f}%</td></tr>'
        for (lvl, lbl), (_l2, _s2, slots) in zip(LEVEL_LABEL, WM.LADDER))

    # ---- the book table: the TRACKED book marked to live (real PnL) if it exists, else the
    #      freshly-sized PROPOSED book (sizing preview). Every row is click-to-expand for the
    #      per-trade 'why' (methodology) + its max upside / downside.
    zk_lu = {(r["level"], r["team"]): r for r in WM.book(ladder, power=power)}    # zero-knowledge ours+edge
    slug_of = {lvl: slug for lvl, slug, _s in WM.LADDER}
    # the informed (Elo) sized book: knockout rounds only (advance excluded), net of the half-spread
    if fundamental:
        efrows = [r for r in WF.book_rows(ladder, model=fundamental, cost=WM.HALF_SPREAD)
                  if r["level"] != "advance"]
        ebook = sized_book(ladder, bankroll=bankroll, rows=efrows)
        elo_lu = {(r["level"], r["team"]): r for r in efrows}
    else:
        ebook, elo_lu = [], {}

    def _why_row(team, level, side, entry, econ, lu, model):
        m = lu.get((level, team), {})
        ours = m.get("ours", entry)
        edge = m.get("edge", ours - entry)
        pm = (f' &nbsp;·&nbsp; <a href="https://polymarket.com/event/{slug_of[level]}" target=_blank '
              f'rel="noopener noreferrer">view market on Polymarket ↗</a> '
              f'<span class=sub>(may be restricted in your region)</span>' if level in slug_of else "")
        return (f'<tr class="why"><td colspan=9 class="whyc">'
                f'{_rationale(side, team, level, entry, ours, edge, model)}'
                f'<div class="mini">stake (most you can lose) <b class="neg">${econ["stake"]:.2f}</b>'
                f' &nbsp;·&nbsp; max upside if it resolves your way <b class="pos">+${econ["max_up"]:.2f}</b>'
                f' &nbsp;·&nbsp; breakeven at a true probability of <b>{entry*100:.1f}%</b>{pm}</div></td></tr>')

    def _render_book(path, kind, pbook, lu, model):
        """Build ONE book's table — tracked-and-marked if a ledger exists at `path`, else the
        freshly-sized PROPOSED `pbook`. `kind` ('core'|'live') = hold vs rebalance; `model`
        ('zk'|'elo') picks which engine's edges and which per-bet rationale."""
        rows, tot = _marked_rows(ladder, path)
        pref = "Elo · " if model == "elo" else ""
        held = (kind == "core")
        legs, trs = [], []
        if rows:                                                    # a real, entered book
            for r in rows:
                side = "LONG" if r["shares"] > 0 else "SHORT"
                locked = r["pnl"] if r["status"] in ("closed", "resolved") else None
                legs.append((r["shares"], r["entry"], locked))
                econ = _econ(r["shares"], r["entry"])
                up = f'+${econ["max_up"]:.2f}' if locked is None else f'${locked:+.2f}'
                dn = f'${econ["max_down"]:.2f}' if locked is None else f'${locked:+.2f}'
                cur = "—" if r["cur"] is None else f'{r["cur"]*100:.1f}%'
                pnl = ('<td class="pnl">—</td>' if r["pnl"] is None else
                       f'<td class="pnl {"pos" if r["pnl"]>=0 else "neg"}">${r["pnl"]:+.2f}</td>')
                li = LV_IDX[r["level"]]
                trs.append(
                    f'<tr class="clk" data-team="{html.escape(_name(r["team"]).lower())}" onclick="w(this)">'
                    f'<td class="sd {"pos" if side=="LONG" else "neg"}">{side}</td>'
                    f'<td class="team">{_disp(r["team"])}</td><td class=l data-s="{li}">{dict(LEVEL_LABEL)[r["level"]]}</td>'
                    f'<td class=res data-s="{li}">{WM.ROUND_RESOLVES.get(r["level"],"—")}</td>'
                    f'<td>{r["entry"]*100:.1f}%</td><td>{cur}</td>{pnl}'
                    f'<td class="neg">{dn}</td><td class="pos">{up}</td></tr>')
                trs.append(_why_row(r["team"], r["level"], side, r["entry"], econ, lu, model))
            tt = 'pos' if tot["total"] >= 0 else 'neg'
            trs.append(
                f'<tr class="tot"><td colspan=6>realized ${tot["realized"]:+.2f} · '
                f'unrealized ${tot["unrealized"]:+.2f} · {tot["n_open"]}/{tot["n"]} open</td>'
                f'<td class="{tt}">${tot["total"]:+.2f}</td><td colspan=2 class=sub>↤ click a row</td></tr>')
            note = (f"{pref}{'Buy &amp; Hold' if held else 'Active Trading'} — "
                    + ("entered once at day 0, held to each market's resolution, marked to today's prices."
                       if held else
                       "re-evaluated daily; rebalances when a market settles or a fresh edge clears the "
                       "cost buffer — any day, not only matchdays. Open positions marked to today's prices."))
            cols, pills = ('<th data-c=4>Entry</th><th data-c=5>Now</th><th data-c=6>PnL</th>',
                           f'<span class=pill>realized <b class="{tt}">${tot["realized"]:+.2f}</b></span>'
                           f'<span class=pill>unrealized <b>${tot["unrealized"]:+.2f}</b></span>'
                           f'<span class=pill>total PnL <b class="{tt}">${tot["total"]:+.2f}</b></span>')
        else:                                                       # not entered yet -> proposed sizing
            for tk in pbook:
                sc = "pos" if tk["side"] == "LONG" else "neg"
                econ = _econ(tk["shares"], tk["entry"])
                legs.append((tk["shares"], tk["entry"], None))
                li = LV_IDX[tk["level"]]
                trs.append(
                    f'<tr class="clk" data-team="{html.escape(_name(tk["team"]).lower())}" onclick="w(this)">'
                    f'<td class="sd {sc}">{tk["side"]}</td><td class="team">{_disp(tk["team"])}</td>'
                    f'<td class=l data-s="{li}">{dict(LEVEL_LABEL)[tk["level"]]}</td>'
                    f'<td class=res data-s="{li}">{WM.ROUND_RESOLVES.get(tk["level"],"—")}</td>'
                    f'<td>{tk["entry"]*100:.1f}%</td><td>${tk["stake"]:.0f}</td>'
                    f'<td class="{"pos" if tk["edge"]>0 else "neg"}">{tk["edge"]*100:+.1f}%</td>'
                    f'<td class="neg">${econ["max_down"]:.2f}</td><td class="pos">+${econ["max_up"]:.2f}</td></tr>')
                trs.append(_why_row(tk["team"], tk["level"], tk["side"], tk["entry"], econ, lu, model))
            note = (f"{pref}{'Buy &amp; Hold' if held else 'Active Trading'} — proposed day-0 book, sized "
                    f"from ${bankroll:,.0f}, stake ∝ |edge| (capped), net of the half-spread."
                    + ("" if held else " Seeds from the SAME day-0 book, then re-evaluated daily — it "
                       "rebalances when a market settles or a new edge clears the cost buffer (any day, "
                       "settle → close at market → redeploy), so it tracks Buy &amp; Hold until the first trigger."))
            cols, pills = ('<th data-c=4>Pay</th><th data-c=5>Stake</th><th data-c=6>Edge</th>',
                           f'<span class=pill>deployed <b>${sum(t["stake"] for t in pbook):,.0f}</b></span>')
        if model == "elo":
            note += (" <b>Knockout rounds only</b> (advance excluded); the rows are largely <i>one</i> "
                     "correlated 'results-vs-reputation' bet, not diversified breadth.")
        tbl = (f'<p class=note>{note} <b>Click a row</b> for the why; <b>click a header</b> to sort.</p>'
               f'<table class="trades sortable"><thead><tr>'
               f'<th data-c=0 class=l>Side</th><th data-c=1 class=l>Team</th><th data-c=2 class=l>Round</th>'
               f'<th data-c=3 class="l res">Resolves</th>{cols}'
               f'<th data-c=7>Max&nbsp;↓</th><th data-c=8>Max&nbsp;↑</th></tr></thead>'
               f'<tbody>{"".join(trs)}</tbody></table>')
        return dict(html=tbl, legs=legs, pills=pills)

    # FOUR books = 2 models × {Buy & Hold, Active}, each through the SAME machinery (same columns,
    # tracked Entry→Now→PnL once stamped). Each gets its OWN money strip (different positions).
    core = _render_book(core_path, "core", book, zk_lu, "zk")
    live = _render_book(live_path, "live", book, zk_lu, "zk")
    core_book, live_book = core["html"], live["html"]
    core_money = _book_money(core["pills"], core["legs"])
    live_money = _book_money(live["pills"], live["legs"])
    if fundamental:
        eloc = _render_book(elo_core_path, "core", ebook, elo_lu, "elo")
        elol = _render_book(elo_live_path, "live", ebook, elo_lu, "elo")
        eloc_book, elol_book = eloc["html"], elol["html"]
        eloc_money = _book_money(eloc["pills"], eloc["legs"])
        elol_money = _book_money(elol["pills"], elol["legs"])
    else:
        eloc_book = elol_book = eloc_money = elol_money = ""

    # ---- catchy hook: a CURATED set of disagreements (biggest BUY, biggest FADE, biggest ARB)
    #      so the strip tells a varied story rather than three of the same.
    def _edge_card(tk):
        _iso, rank, _t = WM.info(tk["team"])
        rk = f' <span class=rk>#{rank}</span>' if rank else ""
        hi = tk["edge"] > 0
        return (f'<div class="card {"long" if hi else "short"}">'
                f'<div class="cv">MODEL {"HIGHER" if hi else "LOWER"}</div>'
                f'<div class="ct">{_disp(tk["team"])}{rk}</div>'
                f'<div class="cr">{dict(LEVEL_LABEL)[tk["level"]]}</div>'
                f'<div class="cm"><span>market <b>{tk["entry"]*100:.1f}%</b></span>'
                f'<span>model <b>{min(tk["entry"]+tk["edge"],1)*100:.1f}%</b></span></div>'
                f'<div class="ce {"pos" if hi else "neg"}">{tk["edge"]*100:+.1f}% gap</div></div>')
    longs = [t for t in book if t["side"] == "LONG"]
    shorts = [t for t in book if t["side"] == "SHORT"]
    cards = []
    if longs:
        cards.append(_edge_card(max(longs, key=lambda t: t["edge"])))
    if shorts:
        cards.append(_edge_card(min(shorts, key=lambda t: t["edge"])))
    if nested:                                                   # a riskless inconsistency, if any
        t, sh, dp, sp, dpp, _g = nested[0]
        cards.append(
            f'<div class="card arb"><div class="cv">RISKLESS MISPRICING</div>'
            f'<div class="ct">{_disp(t)}</div><div class="cr">nested inconsistency</div>'
            f'<div class="cm">priced higher to <b>{dpp}</b>&nbsp;({dp}) than to <b>{sp}</b>&nbsp;({sh})</div>'
            f'<div class="ce neg">logically impossible — one of these prices is wrong</div></div>')
    elif len(book) > 2:                                          # else a third disagreement
        cards.append(_edge_card(sorted(book, key=lambda t: -abs(t["edge"]))[2]))
    cardstrip = f'<div class="cards">{"".join(cards)}</div>' if cards else ""

    # ---- wc-live matchday timeline (settle -> close -> redeploy), if the live book has run ----
    tl = _live_timeline(live_path)
    if tl:
        tlr = "".join(
            f'<tr><td class="team">{s["date"]}</td><td>{s["opened"]}</td><td>{s["settled"]}</td>'
            f'<td class="{"pos" if s["realized"]>=0 else "neg"}">${s["realized"]:+.2f}</td>'
            f'<td>${s["cum"]:+.2f}</td></tr>' for s in tl)
        timeline = (f'<h2>wc-live — rebalance timeline <span class=sub>(settle · close @ market · redeploy)</span></h2>'
                    f'<table class="tl"><thead><tr><th class=team>Date</th><th>Opened</th>'
                    f'<th>Settled</th><th>Step PnL</th><th>Cumulative</th></tr></thead>'
                    f'<tbody>{tlr}</tbody></table>')
    else:
        timeline = ('<h2>wc-live — rebalance timeline</h2><p class=note>No rebalances yet. The book is '
                    're-checked daily; each step (settle resolved markets → close the rest at the current '
                    'price → redeploy compounding capital) appears here whenever a settle or a fresh '
                    'edge over the cost buffer triggers one — any day, not only matchdays.</p>')

    arbs = ("".join(f"<li><b>{_disp(t)}</b>: "
                    f"priced to {dp} ({dpp}) more than to {sh} ({sp}) — impossible.</li>"
                    for t, sh, dp, sp, dpp, _g in nested[:4])
            or "<li>none right now (the ladder is internally coherent)</li>")

    # ---- the track-record strip (the differentiator: we resolve and keep score) ----
    record = "".join(f'<div class="tile"><div class="tk">{lab}</div>'
                     f'<div class="tv">{val}</div><div class="tn">{note}</div></div>'
                     for lab, val, note in _scorecard_tiles())
    kick = _kickoff_note()
    keydates = _keydates()

    # ---- the INDEPENDENT Elo model (intro+cards shown prominently; its two books become tabs) ----
    fund_intro = _fundamental_section(ladder, fundamental, bankroll) if fundamental else ""
    elo_intro_section = (
        f'<section id=fundamental><h2>The <span style="color:var(--elo)">informed</span> model '
        f'— Elo ratings vs the market <span class=sub>an independent second opinion</span></h2>'
        f'{fund_intro}</section>' if fundamental else "")
    elo_tabs = ('<button class="tab pulse" id=tb-eloc onclick="tab(\'eloc\')">🧮 Elo · Buy &amp; Hold '
                '<span class=sub>informed, held</span></button>'
                '<button class="tab pulse" id=tb-elol onclick="tab(\'elol\')">🧮 Elo · Active '
                '<span class=sub>informed, daily</span></button>') if fundamental else ""
    elo_panes = (f'<div id=pane-eloc class=pane hidden>{eloc_money}<div class=scroll>{eloc_book}</div></div>'
                 f'<div id=pane-elol class=pane hidden>{elol_money}<div class=scroll>{elol_book}</div></div>'
                 ) if fundamental else ""
    outcome_html = (_outcome_map(fundamental, positions, WM.WL.GROUPS_2026)
                    if (fundamental and positions) else "")
    fixtures_html = _fixtures(WM.WL.GROUPS_2026)
    poll_widget = _poll_widget(POLL_ENDPOINT)                 # bottom-left fan poll (only if configured)

    icon = BRAND_ICON                                         # crisp tiny favicon
    mark = _brand_mark()                                      # the Canva emblem (brand + hero)
    desc = ("Can a model beat the World Cup market? A zero-knowledge model (price structure) and an "
            "informed model (Elo) take on the crowd across all 240 markets — scored publicly. Research only.")
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>⚽ World vs Model · World Cup 2026 — Can a model beat the market?</title>
<meta name=description content="{desc}">
<meta property="og:title" content="World vs Model · World Cup 2026">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
<meta property="og:url" content="{SITE_URL}/">
<meta property="og:image" content="{SITE_URL}/wvm_og.png">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{SITE_URL}/wvm_og.png">
<link rel=icon href="{icon}">
<link rel=preconnect href="https://fonts.googleapis.com"><link rel=preconnect href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Space+Grotesk:wght@600;700&display=swap" rel=stylesheet>
<script>(function(){{try{{var t=localStorage.getItem('cm-theme')||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<style>
 :root{{--bg:#0c1424;--panel:#13203a;--panel2:#172642;--raise:#1b2a49;--ink:#e9edf8;--ink2:#aab6d4;
  --ink3:#8190b3;--ink4:#5c6a90;--line:#1c2941;--line2:#26344f;--line3:#33446a;
  --world:#3fd9a3;--worldink:#63e6b8;--model:#4f7ce8;--modelink:#86a4f0;--pos:#3fd9a3;--neg:#f2876c;
  --elo:#8b6dff;--eloink:#b1a1ff;--elowash:rgba(139,109,255,.16);
  --worldwash:rgba(63,217,163,.09);--modelwash:rgba(79,124,232,.14);--hover:#16243f;--whybg:#0b1322}}
 html[data-theme=light]{{--bg:#f5f7fc;--panel:#fff;--panel2:#eef2f9;--raise:#eef2f9;--ink:#101a2e;--ink2:#3a4763;
  --ink3:#5a688a;--ink4:#8693b0;--line:#e5eaf3;--line2:#dbe2ee;--line3:#cbd5e6;
  --world:#0f9c69;--worldink:#0b8157;--model:#2f63d6;--modelink:#244db8;--pos:#0f9c69;--neg:#d75f3c;
  --elo:#6a3fe0;--eloink:#5530bd;--elowash:rgba(106,63,224,.12);
  --worldwash:rgba(15,156,105,.10);--modelwash:rgba(47,99,214,.12);--hover:#eef2f9;--whybg:#eef2f9}}
 *{{box-sizing:border-box}}
 body{{font:14px/1.55 Inter,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:var(--ink)}}
 h1,h2,h3,.brand,.tile .tv{{font-family:'Space Grotesk',Inter,sans-serif}}
 table,.pill,.tile .tv,.chip,.card .cm,.card .ce,td,th{{font-variant-numeric:tabular-nums;font-feature-settings:'tnum' 1}}
 .wrap{{max-width:1100px;margin:0 auto;padding:0 22px 30px}}
 .top{{position:sticky;top:0;z-index:9;background:var(--bg);border-bottom:1px solid var(--line2);
   display:flex;align-items:center;gap:14px;padding:11px 22px;margin-bottom:6px}}
 .brand{{display:flex;align-items:center;gap:9px;font-weight:700;font-size:15px;white-space:nowrap}}
 .brand img{{width:31px;height:31px;border-radius:8px}} .brand .bt{{color:var(--ink4);font-weight:500}}
 .brand .vs{{color:var(--elo)}}
 .hmark{{width:50px;height:50px;border-radius:12px;flex:0 0 auto;box-shadow:0 2px 14px rgba(0,0,0,.35)}}
 @media(max-width:560px){{.hmark{{width:40px;height:40px;border-radius:10px}}}}
 .nav{{display:flex;gap:15px;margin-left:auto;font-size:13px}} .nav a{{color:var(--ink3);text-decoration:none}}
 .nav a:hover{{color:var(--ink)}} @media(max-width:720px){{.nav{{display:none}}}}
 .tgl{{background:var(--raise);border:1px solid var(--line3);color:var(--ink);border-radius:8px;
   width:32px;height:30px;cursor:pointer;font-size:14px}}
 h1{{font-size:25px;margin:18px 0 4px;letter-spacing:-.3px}} .sub2{{color:var(--ink3);font-size:13px;max-width:760px}}
 .byline{{margin-top:6px;font-size:12px;color:var(--ink4)}} .byline a{{color:var(--ink3);font-weight:600}}
 h2{{font-size:16px;margin:30px 0 8px;border-bottom:1px solid var(--line2);padding-bottom:5px;scroll-margin-top:60px}}
 table{{border-collapse:collapse;width:100%;font-size:13px}}
 th,td{{padding:5px 8px;text-align:right;border-bottom:1px solid var(--line)}}
 th{{color:var(--ink3);font-weight:600;font-size:11px;text-transform:uppercase}}
 td.team,th.team{{text-align:left;font-weight:600}} .sub{{color:var(--ink4);font-weight:400;font-size:9px}}
 .l,td.sd,td.res{{text-align:left}} td.sd{{font-weight:700}} td.res{{color:var(--ink3);font-size:12px;white-space:nowrap}}
 .sortable th[data-c]{{cursor:pointer;user-select:none;white-space:nowrap}} .sortable th[data-c]:hover{{color:var(--ink)}}
 .sortable th.asc::after{{content:" ▲";color:var(--model);font-size:9px}}
 .sortable th.desc::after{{content:" ▼";color:var(--model);font-size:9px}}
 td.mk,th.mkh{{color:var(--ink2);background:var(--worldwash)}}
 td.md,th.mdh{{color:var(--ink);font-weight:600;background:var(--modelwash)}} td.na{{color:var(--ink4)}}
 .grp{{text-align:center;font-size:10px;letter-spacing:.3px;background:var(--panel2);border-bottom:1px solid var(--line2)}}
 .grp.world{{color:var(--worldink)}} .grp.model{{color:var(--modelink)}}
 .pos{{color:var(--pos)}} .neg{{color:var(--neg)}} .edge{{font-weight:600}}
 tr.tot td{{font-weight:700;border-top:2px solid var(--line3);color:var(--ink2);text-align:right}}
 .note{{color:var(--ink3);font-size:12px;margin:0 0 8px}}
 .legend{{color:var(--ink3);font-size:12px;margin:6px 0 0}} .legend b{{color:var(--ink);font-weight:600}}
 .dot{{display:inline-block;width:9px;height:9px;border-radius:2px;margin:0 4px 0 10px;vertical-align:middle}}
 .pill{{display:inline-block;background:var(--raise);border:1px solid var(--line2);border-radius:14px;
   padding:3px 10px;margin:3px 4px 3px 0;font-size:12px;color:var(--ink2)}} .pill b{{color:var(--ink)}}
 .riskrow{{margin:0 0 10px}}
 .about{{display:flex;gap:13px;align-items:center;margin-top:24px;padding:13px 16px;background:var(--panel);
   border:1px solid var(--line2);border-radius:12px;color:var(--ink2);font-size:13px;line-height:1.55}}
 .about b{{color:var(--ink)}} .about a{{color:var(--model)}} .about a:hover{{text-decoration:underline}}
 .amark{{width:44px;height:44px;border-radius:11px;flex:0 0 auto}}
 @media(max-width:560px){{.about{{flex-direction:column;align-items:flex-start}}}}
 .disc{{color:var(--ink4);font-size:12px;margin-top:22px;border-top:1px solid var(--line2);padding-top:12px}}
 a{{color:var(--model)}}
 .grid{{display:grid;grid-template-columns:1fr 1fr;gap:24px}} @media(max-width:760px){{.grid{{grid-template-columns:1fr}}}}
 .scroll{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
 .hero{{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin-top:2px}}
 .kick{{background:var(--worldwash);color:var(--worldink);border:1px solid var(--line2);border-radius:20px;
   padding:2px 11px;font-size:12px;font-weight:600}}
 .kdates{{margin:12px 0 2px;border:1px solid var(--line2);border-radius:12px;padding:11px 13px;background:var(--panel)}}
 .kdh{{font-size:12px;font-weight:700;color:var(--ink2);margin-bottom:9px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
 .kd-cd{{background:var(--elowash);color:var(--eloink);border-radius:20px;padding:1px 9px;font-size:11px}}
 .kdrow{{display:flex;gap:8px;overflow-x:auto;-webkit-overflow-scrolling:touch}}
 .kd{{flex:1 0 auto;min-width:96px;border-left:2px solid var(--elo);padding:2px 0 2px 9px;display:flex;flex-direction:column}}
 .kdd{{font-size:13px;font-weight:800;font-family:'Space Grotesk',system-ui,sans-serif}}
 .kdt{{font-size:12px;font-weight:600;color:var(--ink)}} .kds{{font-size:10px;color:var(--ink4);text-transform:uppercase;letter-spacing:.4px}}
 .record{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0 2px}}
 @media(max-width:620px){{.record{{grid-template-columns:1fr 1fr}}}}
 .tile{{background:var(--panel);border:1px solid var(--line2);border-radius:11px;padding:11px 14px}}
 .tile .tk{{color:var(--ink3);font-size:10px;text-transform:uppercase;letter-spacing:.4px}}
 .tile .tv{{font-size:22px;font-weight:800;letter-spacing:-.5px;margin:2px 0}} .tile .tn{{color:var(--ink4);font-size:11px}}
 .searchbar{{display:flex;align-items:center;gap:8px;background:var(--panel);border:1px solid var(--line3);
   border-radius:12px;padding:2px 10px;margin:16px 0 4px}} .searchbar:focus-within{{border-color:var(--model)}}
 .find{{flex:1;width:auto;border:0;background:transparent;color:var(--ink);font-size:14px;padding:11px 2px}}
 .find:focus{{outline:none}} .find::placeholder{{color:var(--ink4)}}
 .ball2{{font-size:20px;cursor:pointer;line-height:1;animation:roll 2.4s linear infinite}}
 .nores{{color:var(--neg);font-size:12px;margin:2px 2px 4px}}
 .fab{{position:fixed;right:18px;bottom:18px;z-index:20;width:54px;height:54px;border-radius:50%;
   border:1px solid var(--line3);background:var(--panel);color:inherit;cursor:pointer;
   box-shadow:0 6px 22px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center}}
 .fab:hover{{transform:translateY(-2px)}} .fab span{{font-size:26px;animation:bob 1.4s ease-in-out infinite}}
 @keyframes roll{{from{{transform:rotate(0)}}to{{transform:rotate(360deg)}}}}
 .boot{{font-size:18px;cursor:pointer;line-height:1;transition:transform .1s}} .boot:hover{{transform:rotate(-22deg)}}
 .fab.kicked{{animation:kick 1.15s cubic-bezier(.34,-.3,.7,1.3)}}
 @keyframes kick{{0%{{transform:translate(0,0) rotate(0)}}
   40%{{transform:translate(var(--kx1,-58vw),var(--ky1,-34vh)) rotate(var(--kr1,-560deg))}}
   70%{{transform:translate(var(--kx2,-26vw),var(--ky2,6vh)) rotate(var(--kr2,-820deg))}}
   100%{{transform:translate(0,0) rotate(var(--kr3,-1080deg))}}}}
 .confp{{position:fixed;top:-14px;z-index:60;border-radius:1px;pointer-events:none;animation:conffall linear forwards}}
 @keyframes conffall{{to{{transform:translate(var(--dx,0),106vh) rotate(var(--rot,360deg))}}}}
 .goalbanner{{position:fixed;left:50%;top:32%;transform:translateX(-50%);z-index:61;pointer-events:none;
   font-family:'Space Grotesk',system-ui,sans-serif;font-weight:800;font-size:clamp(26px,7vw,42px);
   color:var(--ink);text-shadow:0 3px 22px rgba(0,0,0,.55);white-space:nowrap;animation:goalpop 1.9s ease-out forwards}}
 @keyframes goalpop{{0%{{opacity:0;transform:translateX(-50%) scale(.5)}}
   16%{{opacity:1;transform:translateX(-50%) scale(1.12)}}70%{{opacity:1;transform:translateX(-50%) scale(1)}}
   100%{{opacity:0;transform:translateX(-50%) scale(1) translateY(-26px)}}}}
 .tabs{{display:flex;gap:6px;margin:10px 0;flex-wrap:wrap}}
 .tab{{background:var(--panel);border:1px solid var(--line2);color:var(--ink3);border-radius:9px;
   padding:8px 13px;cursor:pointer;font-size:13px;font-weight:600}}
 .tab.on{{color:var(--ink);border-color:var(--model);background:var(--modelwash)}}
 .mtog{{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin:4px 0 8px}}
 .mtl{{color:var(--ink3);font-size:12px;font-weight:600}}
 .mb{{background:var(--panel);border:1px solid var(--line2);color:var(--ink3);border-radius:8px;
   padding:5px 11px;cursor:pointer;font-size:12px;font-weight:600}}
 .mb.on{{color:var(--ink);border-color:var(--model);background:var(--modelwash)}}
 .mb#mb-elo.on{{border-color:var(--elo);background:var(--elowash)}}
 .tab#tb-elo.on{{border-color:var(--elo);background:var(--elowash)}}
 .tab#tb-elo .sub{{color:var(--eloink)}}
 table.board.elo td.md,table.board.elo th.mdh{{background:var(--elowash)}}
 table.board.elo #modelhdr{{color:var(--eloink)}}
 .eloc{{color:var(--eloink);font-weight:600}}
 .hint{{color:var(--ink4);font-size:11px;font-style:italic}}
 .pulse{{animation:pulse 1.7s ease-in-out 3;position:relative}}
 @keyframes pulse{{0%,100%{{box-shadow:0 0 0 0 var(--elowash)}}50%{{box-shadow:0 0 0 5px var(--elowash)}}}}
 .rst{{background:transparent;border:1px solid var(--line2);color:var(--ink4);border-radius:7px;
   padding:3px 8px;cursor:pointer;font-size:11px;margin-left:6px}} .rst:hover{{color:var(--ink2);border-color:var(--line3)}}
 .pop{{position:fixed;right:18px;bottom:82px;z-index:21;width:300px;max-width:calc(100vw - 28px);
   background:var(--panel);border:1px solid var(--line3);border-radius:13px;padding:12px;
   box-shadow:0 12px 38px rgba(0,0,0,.45)}}
 .pophd{{font-weight:700;font-size:13px;display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
 .popx{{cursor:pointer;color:var(--ink4);font-size:14px}} .popx:hover{{color:var(--ink)}}
 .popin{{width:100%;box-sizing:border-box;background:var(--raise);border:1px solid var(--line2);
   color:var(--ink);border-radius:8px;padding:8px 10px;font-size:13px;outline:none}}
 .popin:focus{{border-color:var(--model)}}
 .popr{{margin-top:8px;max-height:46vh;overflow:auto}}
 .pophint{{color:var(--ink4);font-size:12px;padding:6px 2px}}
 .pr{{border:1px solid var(--line2);border-radius:9px;padding:8px 10px;margin-bottom:6px;cursor:pointer}}
 .pr:hover{{border-color:var(--model);background:var(--hover)}}
 .prn{{font-weight:700;font-size:13px}} .prv{{font-size:12px;color:var(--ink2);margin-top:3px}}
 .prg{{font-size:10px;color:var(--model);margin-top:6px;cursor:pointer}} .prg:hover{{text-decoration:underline}}
 .pq{{color:var(--ink4);font-size:10px}}
 .prspark{{display:flex;align-items:center;gap:6px;margin-top:6px}}
 .spk{{flex:0 0 auto;border-radius:3px;background:var(--raise)}} .spd{{font-size:11px;font-weight:700}}
 .prr{{margin-top:6px;font-size:11px;color:var(--ink2);display:flex;align-items:center;gap:3px;flex-wrap:wrap}}
 .prseg b{{color:var(--eloink)}} .prarrow{{color:var(--ink4)}}
 .prl{{margin-top:6px;font-size:11px;color:var(--ink2)}} .prl b{{color:var(--ink)}}
 .thinwarn{{color:var(--neg);font-weight:700;font-size:10px;text-transform:uppercase;letter-spacing:.4px}}
 tr.flash{{animation:flash 1.6s ease-out}}
 @keyframes flash{{0%,30%{{background:var(--elowash)}}100%{{background:transparent}}}}
 @media(prefers-reduced-motion:reduce){{.pulse,tr.flash{{animation:none}}}}
 .clr{{background:var(--raise);border:1px solid var(--line3);color:var(--ink3);border-radius:8px;
   padding:5px 9px;cursor:pointer;font-size:12px}} .clr:hover{{color:var(--ink)}}
 .searchbar{{scroll-margin-top:62px}} body.searching #recordsec,body.searching #disagree{{display:none}}
 @media(prefers-reduced-motion:reduce){{.ball2,.fab span,.fab.kicked,.confp{{animation:none}}}}
 .cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0 4px}}
 @media(max-width:680px){{.cards{{grid-template-columns:1fr}}}}
 .card{{background:var(--panel);border:1px solid var(--line2);border-left:3px solid var(--world);border-radius:11px;padding:12px 14px}}
 .card.short{{border-left-color:var(--neg)}} .card.arb{{border-left-color:var(--model)}}
 .card .cv{{font-size:10px;letter-spacing:1px;color:var(--worldink);font-weight:800}}
 .card.short .cv{{color:var(--neg)}} .card.arb .cv{{color:var(--modelink)}}
 .card .ct{{font-size:18px;font-weight:700;margin:3px 0}} .card .cr{{color:var(--ink3);font-size:11px;text-transform:uppercase}}
 .card .cm{{display:flex;justify-content:space-between;gap:8px;color:var(--ink2);font-size:12px;margin:8px 0 5px}}
 .card .cm b{{color:var(--ink)}} .card .ce{{font-weight:700;font-size:13px}}
 tr.clk{{cursor:pointer}} tr.clk:hover{{background:var(--hover)}} tr.clk td.team::after{{content:" ›";color:var(--ink4)}}
 tr.why{{display:none}}
 td.whyc{{text-align:left;color:var(--ink2);font-size:12px;line-height:1.55;background:var(--whybg);white-space:normal}}
 td.whyc b{{color:var(--ink)}} .mini{{margin-top:6px;color:var(--ink3)}}
 img.flag{{border-radius:2px;vertical-align:-2px;margin-right:5px;box-shadow:0 0 0 1px rgba(0,0,0,.25)}}
 a.tl{{color:inherit;text-decoration:none}} a.tl:hover{{text-decoration:underline}}
 .rk{{color:var(--ink4);font-weight:600;font-size:11px;margin-left:5px}}
 .cup{{color:#e9b949;font-weight:700;font-size:11px;margin-left:4px}}
 .card .ct .rk{{font-size:12px}}
 .ball{{display:inline-block;animation:bob 1.8s ease-in-out infinite}}
 @keyframes bob{{0%,100%{{transform:translateY(0) rotate(0)}}50%{{transform:translateY(-4px) rotate(18deg)}}}}
 @media(prefers-reduced-motion:reduce){{.ball{{animation:none}}}}
 h3{{font-size:14px;margin:18px 0 7px;color:var(--ink2)}}
 .groups{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:8px 0}}
 @media(max-width:860px){{.groups{{grid-template-columns:repeat(3,1fr)}}}}
 @media(max-width:560px){{.groups{{grid-template-columns:repeat(2,1fr)}}}}
 .fxgrid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:8px 0}}
 @media(max-width:860px){{.fxgrid{{grid-template-columns:repeat(2,1fr)}}}}
 @media(max-width:560px){{.fxgrid{{grid-template-columns:1fr}}}}
 .fxcard{{background:var(--panel);border:1px solid var(--line2);border-radius:11px;padding:10px 12px}}
 .fxmd{{display:flex;align-items:center;gap:8px;margin-top:7px;flex-wrap:wrap}}
 .fxmdl{{font-size:10px;font-weight:800;color:var(--ink4);min-width:26px}}
 .fx{{display:inline-flex;align-items:center;gap:4px;font-size:12px;background:var(--raise);
   border-radius:7px;padding:3px 7px}}
 .fxc{{font-weight:700;font-size:11px}} .fxv{{color:var(--ink4);font-size:10px;margin:0 1px}}
 .gcard{{background:var(--panel);border:1px solid var(--line2);border-radius:10px;padding:8px 10px}}
 .gh{{font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:var(--ink3);font-weight:700;margin-bottom:3px}}
 .gt{{width:100%;font-size:12px}} .gt td{{padding:3px 2px;border-bottom:1px solid var(--line)}}
 .gt td.gp{{width:13px;color:var(--ink4);text-align:center}} .gt td:last-child{{text-align:right;color:var(--ink3)}}
 .gt tr.q td.gp{{color:var(--world);font-weight:800}} .gt tr.m td.gp{{color:#d9a441;font-weight:700}}
 .gt tr.o{{opacity:.5}} img.flag{{margin-right:4px}}
 .qd,.md{{display:inline-block;width:8px;height:8px;border-radius:2px;vertical-align:middle;margin:0 2px}}
 .qd{{background:var(--world)}} .md{{background:#d9a441}}
 .bwrap{{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:6px 0}}
 .blabels{{display:flex;min-width:1120px;margin-bottom:5px}}
 .blabels span{{flex:1;text-align:center;color:var(--ink3);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px}}
 .bracket{{display:flex;min-width:1120px;align-items:stretch}}
 .bcol{{flex:1;display:flex;flex-direction:column;justify-content:space-around;gap:5px;padding:0 3px}}
 .bcol.bmid{{flex:1.25;justify-content:center}}
 .bn{{display:flex;align-items:center;justify-content:center;gap:5px;background:var(--panel);
   border:1px solid var(--line2);border-radius:7px;padding:4px 5px;white-space:nowrap}}
 .bn .bc{{font-weight:700;color:var(--ink2);font-size:11px;letter-spacing:.3px}}
 .bn.bne{{opacity:.35;color:var(--ink3)}}
 .bn img.flag{{margin:0}}
 .bchamp{{background:var(--elowash);border:1.5px solid var(--elo);border-radius:12px;padding:10px 8px;text-align:center}}
 .bchamp img.flag{{margin:0 auto 4px;display:block;width:33px;height:25px}}
 .bchamp .bcn{{font-weight:700;font-size:14px;font-family:'Space Grotesk',Inter,sans-serif}}
 .bchamp .bct{{color:var(--eloink);font-weight:700;font-size:11px;text-transform:uppercase;letter-spacing:.4px;margin-top:2px}}
 /* a one-line "swipe" hint, shown only on phones where something still scrolls sideways */
 .mhint{{display:none;color:var(--ink4);font-size:11px;font-style:italic;margin:3px 2px 0}}
 /* ---- mobile: NARROW the wide tables (hide non-essential columns) instead of forcing scroll ---- */
 @media(max-width:600px){{
   .mhint{{display:block}}
   /* board: drop the mid-ladder rounds; keep Team · Advance · Win (market/model) · Edge */
   table.board td.midcol,table.board th.midcol{{display:none}}
   table.board{{font-size:12px}}
   table.board td.team,table.board th.team{{position:sticky;left:0;z-index:2;
     background:var(--bg);box-shadow:1px 0 0 var(--line2)}}
   .grp.world{{font-size:0}} .grp.world::after{{content:'World (Polymarket)';font-size:11px}}
   /* books: drop the Resolves column; pin the team name */
   .trades td.res,.trades th.res{{display:none}}
   .trades td.team,.trades th.team{{position:sticky;left:0;z-index:2;background:var(--bg)}}
   /* knockout bracket: shrink so there's far less sideways scroll */
   .bracket,.blabels{{min-width:760px}}
   .bn{{padding:3px;gap:3px}} .bn img.flag{{width:15px;height:11px}} .bn .bc{{font-size:9px}}
 }}
</style></head><body>
<div class=top>
  <span class=brand><img src="{mark}" alt="World vs Model"> World <span class=vs>vs</span> Model <span class=bt>· World Cup 2026</span></span>
  <nav class=nav><a href="#cards">Disagreements</a><a href="#board">Board</a><a href="#book">Book</a>
    <a href="#fundamental">Elo model</a><a href="#outcome">Outcome map</a><a href="#record">Track record</a>
    <a href="methodology.html">Method</a></nav>
  <button class=tgl id=th onclick="tg()" title="Toggle light / dark">☀️</button>
</div>
<div class=wrap>
 <div class=hero><img class=hmark src="{mark}" alt="World vs Model logo">
   <h1>World Cup 2026 — Can a model beat the market?</h1>
   <span class=kick>{kick}</span></div>
 <div class=sub2>Two models take on the crowd across all 240 markets: one knows <b>zero football</b>
   (<span style="color:var(--world)">just price structure</span>), one is <b>informed</b>
   (<span style="color:var(--elo)">Elo ratings</span>). Can either beat the market — or is the crowd
   unbeatable? We keep a public scorecard.
   <a href="methodology.html">How this works →</a> &nbsp;·&nbsp; <a href="glossary.html">Glossary &amp; references →</a></div>
 <div class=byline>A research experiment by <a href="{AUTHOR_URL}" target=_blank rel="noopener noreferrer">{AUTHOR_NAME} ↗</a></div>
 <div style="margin-top:10px">
   <span class=pill>updated <b>{stamp}</b></span>
   <span class=pill><b>240</b> markets · 48 teams</span>
   <span class=pill><b>2</b> models vs the crowd</span>
   <span class=pill>scored <b>vs the market</b></span>
   <span class=pill>market data · <a href="https://polymarket.com/sports/world-cup" target=_blank rel="noopener noreferrer"><b>Polymarket</b> ↗</a></span>
 </div>
 {keydates}
 <section id=recordsec><h2 id=record>Track record <span class=sub>— we resolve every call out of sample and keep score</span></h2>
 <div class=record>{record}</div></section>
 <div class=searchbar><span class=ball2 onclick="focusFind()" title="Find a team">⚽</span>
   <input class=find id=find type=search placeholder="Find a country or trade — e.g. France, Japan, Brazil…"
     oninput="fq(this.value)" aria-label="Find a country or trade">
   <button class=clr id=clr onclick="clearFind()" title="Clear filter" hidden>✕ reset</button>
   <span class=boot onclick="kick()" title="Kick the ball!">🦵</span></div>
 <div class=nores id=nores hidden>No team matches — try a country like <b>France</b>, <b>Japan</b> or <b>Brazil</b>.</div>
 <section id=disagree><h2 id=cards>The <span style="color:var(--world)">zero-knowledge</span> model's biggest disagreements</h2>
 {cardstrip}</section>
 {elo_intro_section}
 <h2 id=board>The board — each round, market vs model</h2>
 <div class=legend><span class="dot" style="background:var(--world)"></span><b>Market</b> = live
   <a href="https://polymarket.com/sports/world-cup" target=_blank rel="noopener noreferrer">Polymarket ↗</a>
   prices, de-vigged so each round sums to its slots (32 advance · 8 QF · 4 SF · 2 final · 1 win).
   <span class="dot" style="background:var(--model)"></span><b>Model</b> = pick one below. <b>Edge</b> = model − market.
   <button class=rst onclick="resetSort()" title="Reset table sorting">↺ reset sort</button></div>
 {model_toggle}
 <div class=scroll>{board}</div>
 <div class=mhint>↔ swipe the table sideways · the QF/SF/final columns are hidden on small screens (tap a team for its full route)</div>
 <div class=grid>
  <div><h2>The market's hidden vig</h2>
   <p class=note>Add up every team's price in a round and it sums to <i>more</i> than the real number of
     slots (32 advance, 1 champion…). That excess is the market's built-in margin — the <b>overround</b>,
     or <b>vig</b>. A bigger overround means a fatter, less efficient market; we strip it out (de-vig)
     before comparing anyone to the crowd.</p>
   <table class="vig sortable"><thead><tr><th class="team l" data-c=0>Round</th><th data-c=1>Sums to</th><th data-c=2>Slots</th><th data-c=3>Overround</th></tr></thead>
   <tbody>{vig}</tbody></table></div>
  <div><h2>Riskless inconsistencies <span class=sub>— checked daily; tradeable any day</span></h2>
   <p class=note>Where the ladder's own prices break nesting (a team priced likelier to go far than to
     go less far) — a risk-free edge that can open on a quiet day, not just a matchday.</p><ul>{arbs}</ul></div>
 </div>
 {outcome_html}
 {fixtures_html}
 <h2 id=book>If you'd traded it <span class=sub>— a paper book to keep score, not advice</span></h2>
 <p class=note><b>A secondary, "what-if" view</b> — purely to put a number on the disagreements above.
   No real money: a $1,000 <i>paper</i> book, conviction-weighted and dollar-neutral. Edges are shown
   <b>net of a ~{half_spread_c:.0f}c half-spread</b> — a gap that doesn't clear the cost to trade it is
   sized to zero (that half-spread is the <b>cost buffer</b>). <b>Buy &amp; Hold</b> enters once at day 0
   and holds to resolution; <b>Active Trading</b> is re-evaluated daily and rebalances whenever a market
   settles or a fresh edge clears that buffer — any day, not only matchdays (a riskless inconsistency is
   the clearest example). <a href="methodology.html">Methodology →</a></p>
 <div style="margin:0 0 10px"><span class=pill>paper bankroll <b>${bankroll:,.0f}</b></span>
   <span class=hint>👇 each book below shows its <b>own</b> capital at risk &amp; max ↑/↓</span></div>
 <div class=tabs role=tablist>
   <button class="tab on" id=tb-core onclick="tab('core')">🤝 Buy &amp; Hold <span class=sub>zero-knowledge, held</span></button>
   <button class="tab" id=tb-live onclick="tab('live')">🔄 Active Trading <span class=sub>zero-knowledge, daily</span></button>
   {elo_tabs}
 </div>
 <div id=pane-core class=pane>{core_money}<div class=scroll>{core_book}</div></div>
 <div id=pane-live class=pane hidden>{live_money}<div class=scroll>{live_book}</div>{timeline}</div>
 {elo_panes}
 <div class=about><img class=amark src="{mark}" alt="">
   <div><b>About.</b> A solo research &amp; education project by
   <a href="{AUTHOR_URL}" target=_blank rel="noopener noreferrer">{AUTHOR_NAME} ↗</a> — an open test of
   whether transparent models can beat a liquid market, with an honest public scorecard. Built in the
   open, scored against the crowd; <b>no positions, no capital, no advice</b>.
   <a href="https://github.com/mli3w/world-vs-model" target=_blank rel="noopener noreferrer">Source &amp; method on GitHub ↗</a></div></div>
 <div class=disc>⚠️ <b>A research &amp; education experiment — NOT gambling, and NOT an encouragement
   to gamble.</b> We hold <b>no positions</b> and invest <b>no real capital</b>; every figure here is a
   paper simulation of market <i>structure</i>, not investment returns or a tipping service. This is
   <b>not financial advice and not a solicitation</b> to trade or bet. Prediction-market platforms such
   as Polymarket are <b>restricted or banned in several jurisdictions (e.g. Singapore)</b> — know and
   follow your local laws; the Polymarket links are reference-only. Book max ↑/↓ is a loose theoretical
   envelope (outcomes are correlated). Whether the model actually beats the market is settled by the
   live scorecard as matches resolve.
   <div style="margin-top:6px">FIFA ranking &amp; titles are reference data
   (rank {WM.FIFA_RANK_AS_OF}) — source: <a href="{WM.FIFA_RANKING_URL}" target=_blank
   rel="noopener noreferrer">FIFA / inside.fifa.com ↗</a>. Flag images via flagcdn.com. We are not
   affiliated with FIFA or Polymarket.</div></div>
</div>
<div id=pop class=pop hidden>
  <div class=pophd>⚽ Look up a team<span class=popx onclick="togglePop()" title="Close">✕</span></div>
  <input id=popin class=popin type=search placeholder="Type a country — France, Japan, Brazil…"
    oninput="popSearch(this.value)" aria-label="Look up a team">
  <div id=popr class=popr></div>
</div>
<button class=fab id=fab onclick="togglePop()" title="Look up a team" aria-label="Look up a team"><span>⚽</span></button>
<script>
var WVM={team_js};
function w(r){{var d=r.nextElementSibling;if(d&&d.className.indexOf('why')>=0){{
  d.style.display=(d.style.display==='table-row')?'none':'table-row';}}}}
function focusFind(){{var f=document.querySelector('.find');if(f){{f.scrollIntoView({{block:'center',behavior:'smooth'}});f.focus();}}}}
function fq(v){{v=(v||'').trim().toLowerCase();var any=false;
  document.querySelectorAll('tr[data-team]').forEach(function(r){{
    var hit=!v||r.getAttribute('data-team').indexOf(v)>=0;
    r.style.display=hit?'':'none';if(hit)any=true;
    var d=r.nextElementSibling;
    if(d&&d.className.indexOf('why')>=0)d.style.display='none';}});
  var n=document.getElementById('nores');if(n)n.hidden=!(v&&!any);
  var c=document.getElementById('clr');if(c)c.hidden=!v;
  document.body.classList.toggle('searching',!!v);   // collapse the marketing sections so results show
  if(v){{var sb=document.querySelector('.searchbar'),t=sb.getBoundingClientRect().top;
    if(t<0||t>150)sb.scrollIntoView({{behavior:'smooth',block:'start'}});}}}}
function clearFind(){{var f=document.getElementById('find');if(f){{f.value='';fq('');f.focus();}}}}
function tab(n){{document.querySelectorAll('.pane').forEach(function(p){{p.hidden=p.id!=='pane-'+n;}});
  document.querySelectorAll('.tab').forEach(function(b){{b.classList.toggle('on',b.id==='tb-'+n);b.classList.remove('pulse');}});}}
function setModel(wm){{
  var bt=document.querySelector('table.board');if(bt)bt.classList.toggle('elo',wm==='elo');
  document.querySelectorAll('table.board td.md').forEach(function(c){{
    var v=c.getAttribute('data-'+wm);if(v===null)return;c.textContent=(parseFloat(v)*100).toFixed(1)+'%';}});
  document.querySelectorAll('table.board td.edge').forEach(function(c){{
    var v=c.getAttribute(wm==='zk'?'data-ze':'data-ee');if(v===null)return;var n=parseFloat(v);
    c.textContent=(n>=0?'+':'')+(n*100).toFixed(1)+'%';
    c.className='edge '+(n>0.003?'pos':(n<-0.003?'neg':''));}});
  var h=document.getElementById('modelhdr');if(h)h.textContent=wm==='zk'?'zero-knowledge':'informed · Elo';
  var z=document.getElementById('mb-zk'),e=document.getElementById('mb-elo');
  if(z)z.classList.toggle('on',wm==='zk');if(e)e.classList.toggle('on',wm==='elo');
  if(z)z.classList.remove('pulse');if(e)e.classList.remove('pulse');}}
var _kicks=0;
function _rnd(a,b){{return a+Math.random()*(b-a);}}
function kick(){{var b=document.querySelector('.fab');if(!b)return;
  var dir=Math.random()<0.5?-1:1, spin=Math.random()<0.5?-1:1;          // random side + spin
  b.style.setProperty('--kx1',(dir*_rnd(34,68)).toFixed(1)+'vw');
  b.style.setProperty('--ky1',(-_rnd(20,46)).toFixed(1)+'vh');
  b.style.setProperty('--kx2',(dir*_rnd(8,40)*(Math.random()<0.5?-1:1)).toFixed(1)+'vw');
  b.style.setProperty('--ky2',(_rnd(-8,12)).toFixed(1)+'vh');           // a low second bounce
  b.style.setProperty('--kr1',(spin*_rnd(360,760)).toFixed(0)+'deg');
  b.style.setProperty('--kr2',(spin*_rnd(620,1040)).toFixed(0)+'deg');
  b.style.setProperty('--kr3',(spin*_rnd(900,1320)).toFixed(0)+'deg');
  b.classList.remove('kicked');void b.offsetWidth;b.classList.add('kicked');
  if((++_kicks)%5===0)confetti(_kicks);}}
function confetti(n){{
  var reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion:reduce)').matches;
  var banner=document.createElement('div');banner.className='goalbanner';
  banner.textContent='\\u26BD GOAL! '+n+' kicks';document.body.appendChild(banner);
  setTimeout(function(){{banner.remove();}},1900);
  if(reduce)return;                                                     // banner only, no particles
  var cols=['#3fd9a3','#4f7ce8','#8b6dff','#e9b949','#ff6b6b','#ffffff'];
  for(var i=0;i<110;i++){{(function(){{
    var p=document.createElement('div');p.className='confp';
    var s=4+Math.random()*7;
    p.style.left=(Math.random()*100).toFixed(1)+'vw';
    p.style.width=s.toFixed(1)+'px';p.style.height=(s*0.55+2).toFixed(1)+'px';
    p.style.background=cols[i%cols.length];
    p.style.animationDelay=(Math.random()*0.5).toFixed(2)+'s';
    p.style.animationDuration=(2.2+Math.random()*1.9).toFixed(2)+'s';
    p.style.setProperty('--dx',((Math.random()*2-1)*22).toFixed(1)+'vw');
    p.style.setProperty('--rot',(Math.random()*1080-540).toFixed(0)+'deg');
    document.body.appendChild(p);
    setTimeout(function(){{p.remove();}},4700);
  }})();}}}}
// ---- ball pop-up: type a team, see market vs both models, jump to its card ----
function togglePop(){{var p=document.getElementById('pop');if(!p)return;
  p.hidden=!p.hidden;if(!p.hidden){{var i=document.getElementById('popin');if(i){{i.focus();popSearch(i.value);}}}}}}
function popSearch(v){{v=(v||'').trim().toLowerCase();var box=document.getElementById('popr');if(!box)return;
  if(!v){{box.innerHTML='<div class=pophint>Start typing a country to see the market vs the models.</div>';return;}}
  var hits=WVM.filter(function(t){{return t.n.indexOf(v)>=0;}}).slice(0,6);
  if(!hits.length){{box.innerHTML='<div class=pophint>No team matches “'+v+'”.</div>';return;}}
  box.innerHTML=hits.map(function(t){{
    var elo=(t.elo===null)?'<span class=pq>—</span>':('<b style="color:var(--elo)">'+t.elo+'%</b>');
    return '<div class=pr>'
      +'<div class=prn>'+t.c+' · '+t.d+'</div>'
      +'<div class=prv><span class=pq>world</span> <b style="color:var(--world)">'+t.mk+'%</b>'
      +' <span class=pq>zk</span> <b style="color:var(--model)">'+t.zk+'%</b>'
      +' <span class=pq>elo</span> '+elo+'</div>'
      +sparkBlock(t.hist)
      +routeLine(t.route)
      +liqLine(t.vol,t.liq)
      +'<div class=prg onclick="goTeam(\\''+t.n+'\\')">tap to find on the board →</div></div>';}}).join('');}}
function money(x){{
  if(x==null)return '';
  if(x>=1e6)return '$'+(x/1e6).toFixed(x>=1e7?0:1)+'M';
  if(x>=1e3)return '$'+(x/1e3).toFixed(x>=1e4?0:1)+'k';
  return '$'+Math.round(x);
}}
function liqLine(vol,liq){{
  if(vol==null&&liq==null)return '';
  var thin=(liq!=null&&liq<2000);
  return '<div class=prl><span class=pq>market</span> '
    +(vol!=null?'<b>'+money(vol)+'</b> traded':'')
    +(liq!=null?' · <b>'+money(liq)+'</b> liquidity'+(thin?' <span class=thinwarn>thin</span>':''):'')+'</div>';
}}
function spark(a){{
  if(!a||a.length<2)return '';
  var w=132,h=26,mn=Math.min.apply(null,a),mx=Math.max.apply(null,a),rng=(mx-mn)||1;
  var pts=a.map(function(v,i){{var x=(i/(a.length-1))*(w-2)+1,y=h-2-((v-mn)/rng)*(h-4);
    return x.toFixed(1)+','+y.toFixed(1);}}).join(' ');
  var up=a[a.length-1]>=a[0],col=up?'var(--world)':'var(--neg)';
  return '<svg class=spk width='+w+' height='+h+' viewBox="0 0 '+w+' '+h+'" preserveAspectRatio=none>'
    +'<polyline points="'+pts+'" fill=none stroke="'+col+'" stroke-width=1.5 stroke-linejoin=round stroke-linecap=round/></svg>';
}}
function sparkBlock(a){{
  if(!a||a.length<2)return '';
  var d=a[a.length-1]-a[0],s=(d>=0?'+':'')+d.toFixed(1),c=d>=0?'var(--world)':'var(--neg)';
  return '<div class=prspark><span class=pq>win odds, history</span>'+spark(a)
    +'<span class=spd style="color:'+c+'">'+s+'pp</span></div>';
}}
function routeLine(r){{
  if(!r)return '';
  var seg=[['adv','Adv'],['qf','QF'],['sf','SF'],['f','Final'],['win','Win']];
  return '<div class=prr><span class=pq>route (Elo)</span> '+seg.map(function(s){{
    return '<span class=prseg>'+s[1]+' <b>'+r[s[0]]+'%</b></span>';}}).join('<span class=prarrow>›</span>')+'</div>';
}}
function goTeam(n){{var f=document.getElementById('find');if(f){{f.value=n;fq(n);}}
  togglePop();
  var row=document.querySelector('tr[data-team="'+n+'"]');
  if(row)setTimeout(function(){{row.scrollIntoView({{behavior:'smooth',block:'center'}});
    row.classList.add('flash');setTimeout(function(){{row.classList.remove('flash');}},1600);}},80);}}
// ---- reset every sortable table to the order it was rendered in ----
var _snap=[];
function resetSort(){{_snap.forEach(function(s){{s.rows.forEach(function(r){{s.tb.appendChild(r);}});}});
  document.querySelectorAll('th[data-c]').forEach(function(h){{h.classList.remove('asc','desc');}});}}
function srt(th){{var tbl=th.closest('table'),tb=tbl.tBodies[0],c=+th.getAttribute('data-c');
  var dir=th.classList.contains('asc')?-1:1;
  tbl.querySelectorAll('th[data-c]').forEach(function(h){{h.classList.remove('asc','desc');}});
  th.classList.add(dir===1?'asc':'desc');
  var rows=[].slice.call(tb.rows),units=[],tot=[],i,r;
  for(i=0;i<rows.length;i++){{r=rows[i];
    if(r.className.indexOf('why')>=0)continue;
    if(r.className.indexOf('tot')>=0){{tot.push(r);continue;}}
    var u=[r];if(rows[i+1]&&rows[i+1].className.indexOf('why')>=0)u.push(rows[i+1]);
    units.push(u);}}
  function cv(cell,row){{if(!cell)return '';
    if(cell.className.indexOf('team')>=0&&row.getAttribute('data-team'))return row.getAttribute('data-team');
    var s=cell.getAttribute('data-s'),t=(s!==null)?s:cell.innerText;
    var num=parseFloat(String(t).replace(/[^0-9.\\-]/g,''));return isNaN(num)?String(t).toLowerCase():num;}}
  units.sort(function(a,b){{var x=cv(a[0].cells[c],a[0]),y=cv(b[0].cells[c],b[0]);
    return (x<y?-1:x>y?1:0)*dir;}});
  units.forEach(function(u){{u.forEach(function(x){{tb.appendChild(x);}});}});
  tot.forEach(function(x){{tb.appendChild(x);}});}}
document.querySelectorAll('table.sortable thead th[data-c]').forEach(function(h){{
  h.addEventListener('click',function(){{srt(h);}});}});
document.querySelectorAll('table.sortable').forEach(function(t){{
  if(t.tBodies[0])_snap.push({{tb:t.tBodies[0],rows:[].slice.call(t.tBodies[0].rows)}});}});
function _ti(){{document.getElementById('th').textContent=
  document.documentElement.getAttribute('data-theme')==='light'?'🌙':'☀️';}}
function tg(){{var h=document.documentElement;var n=h.getAttribute('data-theme')==='light'?'dark':'light';
  h.setAttribute('data-theme',n);try{{localStorage.setItem('cm-theme',n);}}catch(e){{}}_ti();}}
_ti();
</script>
{poll_widget}
</body></html>"""


METHODOLOGY_MD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "docs", "methodology-worldcup.md")
GLOSSARY_MD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "docs", "glossary-worldcup.md")


def _md_inline(s):
    """Inline markdown -> HTML: links, bold, italics, code (text is HTML-escaped first)."""
    s = html.escape(s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
               r'<a href="\2" target=_blank rel="noopener noreferrer">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)          # bold first (may wrap inner *italics*)
    s = re.sub(r"\*([^*]+?)\*", r"<i>\1</i>", s)           # then the remaining single-* italics
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


# KaTeX (math typesetting) for the methodology page only. We render $$...$$ (display) and \(...\)
# (inline) — NOT single $, so literal dollar amounts ($1,000) are never mistaken for math. Degrades
# gracefully: if the CDN is blocked, the raw LaTeX source shows (still readable).
KATEX_CSS = ('<link rel=stylesheet '
             'href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">')
KATEX_JS = (
    '<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>'
    '<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js" '
    'onload="renderMathInElement(document.body,{delimiters:['
    "{left:'$$',right:'$$',display:true},"
    "{left:'\\\\[',right:'\\\\]',display:true},"
    "{left:'\\\\(',right:'\\\\)',display:false}"
    '],throwOnError:false})"></script>')


def _protect_math(md):
    """Stash $$...$$ / \\[...\\] / \\(...\\) spans behind tokens so the markdown renderer can't mangle
    the LaTeX (escaping, * -> italics, etc.). Returns (md_with_tokens, spans)."""
    spans = []

    def stash(m):
        spans.append(m.group(0))
        return f"@@MATH{len(spans) - 1}@@"

    md = re.sub(r"\$\$.+?\$\$", stash, md, flags=re.S)
    md = re.sub(r"\\\[.+?\\\]", stash, md, flags=re.S)
    md = re.sub(r"\\\(.+?\\\)", stash, md, flags=re.S)
    return md, spans


def _restore_math(html_text, spans):
    """Put the raw LaTeX spans back after markdown rendering (KaTeX typesets them client-side)."""
    for i, s in enumerate(spans):
        html_text = html_text.replace(f"@@MATH{i}@@", s)
    return html_text


def _md_to_html(md):
    """A small, dependency-free markdown renderer for our own docs (headings, hr, blockquote,
    tables, ordered/unordered lists, paragraphs + inline formatting). Not a general parser."""
    def is_block(ln):
        return (not ln.strip() or ln.startswith("#") or ln.strip() == "---"
                or ln.startswith(">") or ln.lstrip().startswith("|")
                or re.match(r"^\s*([-*]|\d+\.)\s", ln))
    lines, out, i = md.split("\n"), [], 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1; continue
        if ln.startswith("### "): out.append(f"<h3>{_md_inline(ln[4:])}</h3>"); i += 1; continue
        if ln.startswith("## "): out.append(f"<h2>{_md_inline(ln[3:])}</h2>"); i += 1; continue
        if ln.startswith("# "): out.append(f"<h1>{_md_inline(ln[2:])}</h1>"); i += 1; continue
        if ln.strip() == "---": out.append("<hr>"); i += 1; continue
        if ln.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").strip()); i += 1
            out.append(f"<blockquote>{_md_inline(' '.join(buf))}</blockquote>"); continue
        if ln.lstrip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(lines[i].strip()); i += 1
            cells = lambda r: [c.strip() for c in r.strip().strip("|").split("|")]
            head = "".join(f"<th>{_md_inline(c)}</th>" for c in cells(rows[0]))
            body = "".join("<tr>" + "".join(f"<td>{_md_inline(c)}</td>" for c in cells(r)) + "</tr>"
                           for r in rows[2:])
            out.append(f"<table class=prose><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
            continue
        m = re.match(r"^\s*([-*]|\d+\.)\s", ln)
        if m:
            ordered = m.group(1).endswith(".")
            items = []
            while i < len(lines):
                lm = re.match(r"^\s*([-*]|\d+\.)\s+(.*)$", lines[i])
                if not lm:
                    break
                items.append(lm.group(2)); i += 1
                while (i < len(lines) and lines[i].strip() and lines[i][0] in " \t"
                       and not re.match(r"^\s*([-*]|\d+\.)\s", lines[i])):   # wrapped continuation
                    items[-1] += " " + lines[i].strip(); i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{_md_inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        buf = []
        while i < len(lines) and lines[i].strip() and not is_block(lines[i]):
            buf.append(lines[i].strip()); i += 1
        out.append(f"<p>{_md_inline(' '.join(buf))}</p>")
    return "\n".join(out)


def _doc_page(md_path, title, brand_suffix, nav_html):
    """Render one of our markdown docs (methodology / glossary) as a themed, standalone, shareable
    HTML page matching the board — same brand header, light/dark theme and KaTeX math. `nav_html` is
    the top-bar link cluster (back to the board + the sibling doc)."""
    with open(md_path, encoding="utf-8") as f:
        protected, _math = _protect_math(f.read())
        body = _restore_math(_md_to_html(protected), _math)
    icon = BRAND_ICON
    mark = _brand_mark()
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel=icon href="{icon}">
<link rel=preconnect href="https://fonts.googleapis.com"><link rel=preconnect href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Space+Grotesk:wght@600;700&display=swap" rel=stylesheet>
{KATEX_CSS}
<script>(function(){{try{{var t=localStorage.getItem('cm-theme')||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<style>
 :root{{--bg:#0c1424;--panel:#13203a;--raise:#1b2a49;--ink:#e9edf8;--ink2:#aab6d4;--ink3:#8190b3;--ink4:#5c6a90;
  --line:#1c2941;--line2:#26344f;--line3:#33446a;--model:#4f7ce8;--world:#3fd9a3;--elo:#8b6dff;--codebg:#0b1322}}
 html[data-theme=light]{{--bg:#f5f7fc;--panel:#fff;--raise:#eef2f9;--ink:#101a2e;--ink2:#3a4763;--ink3:#5a688a;
  --ink4:#8693b0;--line:#e5eaf3;--line2:#dbe2ee;--line3:#cbd5e6;--model:#2f63d6;--world:#0f9c69;--elo:#6a3fe0;--codebg:#eef2f9}}
 *{{box-sizing:border-box}} body{{font:15px/1.7 Inter,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:var(--ink)}}
 h1,h2,h3,.brand{{font-family:'Space Grotesk',Inter,sans-serif}} table{{font-variant-numeric:tabular-nums}}
 .top{{position:sticky;top:0;z-index:9;background:var(--bg);border-bottom:1px solid var(--line2);
   display:flex;align-items:center;gap:14px;padding:11px 22px}}
 .brand{{display:flex;align-items:center;gap:9px;font-weight:700;font-size:15px}} .brand img{{width:31px;height:31px;border-radius:8px}}
 .brand .vs{{color:var(--elo)}} .brand .bt{{color:var(--ink4);font-weight:500}} .top a{{margin-left:auto;color:var(--ink3);text-decoration:none;font-size:13px}}
 .top a:hover{{color:var(--ink)}} .tgl{{background:var(--raise);border:1px solid var(--line3);color:var(--ink);
   border-radius:8px;width:32px;height:30px;cursor:pointer;font-size:14px}}
 .wrap{{max-width:820px;margin:0 auto;padding:8px 22px 60px}}
 h1{{font-size:27px;letter-spacing:-.4px;margin:24px 0 6px}} h2{{font-size:19px;margin:30px 0 8px;
   border-bottom:1px solid var(--line2);padding-bottom:5px}} h3{{font-size:15px;margin:20px 0 6px}}
 a{{color:var(--model)}} p{{color:var(--ink2)}} li{{color:var(--ink2);margin:3px 0}}
 b{{color:var(--ink)}} hr{{border:0;border-top:1px solid var(--line2);margin:22px 0}}
 blockquote{{background:var(--raise);border-left:3px solid var(--model);border-radius:8px;
   padding:11px 15px;margin:14px 0;color:var(--ink2)}}
 code{{background:var(--codebg);border:1px solid var(--line2);border-radius:5px;padding:1px 5px;font-size:13px}}
 table.prose{{border-collapse:collapse;width:100%;font-size:14px;margin:12px 0}}
 table.prose th,table.prose td{{border:1px solid var(--line2);padding:7px 10px;text-align:left}}
 table.prose th{{background:var(--raise);color:var(--ink3);font-size:12px;text-transform:uppercase}}
 .katex-display{{overflow-x:auto;overflow-y:hidden;padding:2px 0;margin:10px 0}}
 .katex{{font-size:1.02em}}
</style></head><body>
<div class=top>
  <span class=brand><img src="{mark}" alt="World vs Model"> World <span class=vs>vs</span> Model <span class=bt>· {brand_suffix}</span></span>
  {nav_html}
  <button class=tgl id=th onclick="tg()" title="Toggle light / dark">☀️</button>
</div>
<div class=wrap>{body}</div>
<script>
function _ti(){{document.getElementById('th').textContent=document.documentElement.getAttribute('data-theme')==='light'?'🌙':'☀️';}}
function tg(){{var h=document.documentElement,n=h.getAttribute('data-theme')==='light'?'dark':'light';
  h.setAttribute('data-theme',n);try{{localStorage.setItem('cm-theme',n);}}catch(e){{}}_ti();}}
_ti();
</script>
{KATEX_JS}
</body></html>"""


def build_methodology_html(md_path=METHODOLOGY_MD, board_href="worldcup_board.html"):
    """The methodology page. `board_href` must match the board's hosted filename (e.g. index.html)."""
    nav = (f'<a href="{board_href}">← Board</a>'
           f'<a href="glossary.html" style="margin-left:14px">Glossary →</a>')
    return _doc_page(md_path, "Methodology · World vs Model — World Cup 2026", "Methodology", nav)


def build_glossary_html(md_path=GLOSSARY_MD, board_href="worldcup_board.html"):
    """The glossary & references page (plain-English jargon + the source papers)."""
    nav = (f'<a href="{board_href}">← Board</a>'
           f'<a href="methodology.html" style="margin-left:14px">Methodology →</a>')
    return _doc_page(md_path, "Glossary & references · World vs Model — World Cup 2026",
                     "Glossary &amp; references", nav)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="World Cup 'world vs model' board (research only)")
    ap.add_argument("--bankroll", type=float, default=1000.0)
    ap.add_argument("--power", type=float, default=1.15)
    ap.add_argument("--out", default="worldcup_board.html")
    ap.add_argument("--sims", type=int, default=20000, help="fundamental-model Monte Carlo runs")
    ap.add_argument("--no-fundamental", action="store_true", help="skip the independent Elo section")
    a = ap.parse_args(argv)
    results = load_results()                              # played matches (live re-forecast) or None
    if results:
        print(f"[board] live re-forecast: folding in {len(results)} played match(es)")
    ladder = WM.fetch_ladder()
    history = WM.fetch_win_history()                      # real CLOB win-price series (or {} if down)
    liquidity = WM.fetch_win_liquidity()                  # per-team volume + order-book liquidity
    print(f"[board] win-price history: {len(history)} series · liquidity: {len(liquidity)} markets")
    fundamental = None if a.no_fundamental else WF.fundamental_ladder(n_sims=a.sims, results=results)
    positions = None if a.no_fundamental else WF.group_positions(n_sims=a.sims, results=results)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)  # create the output dir (fresh checkout/CI)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(build_html(ladder=ladder, bankroll=a.bankroll, power=a.power, fundamental=fundamental,
                           positions=positions, history=history, liquidity=liquidity))
    print(f"[board] wrote {a.out}  (open in a browser)")
    # copy the social card next to the board so the relative og:image resolves when hosted
    _og_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "wvm_og.png")
    try:
        import shutil
        shutil.copyfile(_og_src, os.path.join(os.path.dirname(a.out) or ".", "wvm_og.png"))
    except OSError:
        print("[board] og image not found; skipped wvm_og.png")
    outdir = os.path.dirname(a.out) or "."
    for fname, builder in (("methodology.html", build_methodology_html),
                           ("glossary.html", build_glossary_html)):
        try:
            with open(os.path.join(outdir, fname), "w", encoding="utf-8") as f:
                f.write(builder(board_href=os.path.basename(a.out)))
            print(f"[board] wrote {os.path.join(outdir, fname)}")
        except FileNotFoundError:
            print(f"[board] markdown for {fname} not found; skipped")


if __name__ == "__main__":
    main()
