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
BRACKET_SCORE = os.path.join("ledger", "bracket_score.json")  # the knockout-bracket scorecard
BMA_PATH = os.path.join("ledger", "bma.json")             # per-level model weights + ensemble probs
PREDICTIONS = os.path.join("ledger", "predictions.jsonl")  # the timestamped forecast ledger
RESULTS_PATH = os.path.join("ledger", "wc_results.json")  # played matches -> live Elo re-forecast
MATCH_PRICES_PATH = os.path.join("ledger", "wc_match_prices.json")  # cached pre-match Polymarket prices

# the live site (GitHub Pages). Used for ABSOLUTE og:image / og:url — social scrapers (LinkedIn in
# particular) won't resolve a relative image, so the share card needs the full URL.
SITE_URL = "https://mli3w.github.io/world-vs-model"
AUTHOR_NAME = "Marcus Liew"
AUTHOR_URL = "https://www.linkedin.com/in/marcusliewjy/"

# Optional fan-poll backend (Cloudflare Worker, see poll-worker/). When set, the board renders a
# bottom-left "Who wins?" bubble that reads/writes the live tally; when empty, the bubble is omitted
# so nothing half-built ships. Set via env (WVM_POLL_ENDPOINT) or paste the workers.dev URL here.
POLL_ENDPOINT = os.environ.get("WVM_POLL_ENDPOINT", "").strip().rstrip("/")

# Optional cookieless web analytics (Cloudflare Web Analytics). When the beacon token is set, a tiny
# privacy-preserving beacon is injected on every page so we can see traffic + referrers (which channel
# sent visitors); when empty, nothing is added. No cookies, no PII. Set via env (WVM_CF_BEACON) or here.
CF_BEACON_TOKEN = os.environ.get("WVM_CF_BEACON", "").strip()


def _analytics_beacon(token=None):
    """Cloudflare Web Analytics beacon (cookieless). Renders only when a token is configured."""
    token = CF_BEACON_TOKEN if token is None else token
    if not token:
        return ""
    return ('<script defer src="https://static.cloudflareinsights.com/beacon.min.js" '
            f'data-cf-beacon=\'{{"token": "{token}"}}\'></script>')


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


def _scorecard_tiles(path=SCORECARD, results_path=RESULTS_PATH, today=None):
    """Track-record tiles for the credibility strip. Reads the resolved-out-of-sample scorecard
    AND the played-match ledger; honestly distinguishes three states:
       • PRE-KICKOFF  — before Jun 11, nothing yet
       • GROUP STAGE  — tournament running, advance level still resolving
       • LIVE         — at least one round has fully resolved → hit rate / Brier / lift
    """
    try:
        import json as _json
        with open(path) as f:
            d = _json.load(f)
    except Exception:
        return [("track record", "arming", "scores after kickoff")]
    n_res, n_tot = d.get("n_resolved", 0), d.get("n_total", 0)
    today = today or dt.date.today()

    if n_res:                                                  # rounds have resolved → real metrics
        ov = d.get("overall", {})
        hit, lift, brier = ov.get("hit_rate"), ov.get("lift"), ov.get("brier")
        return [("hit rate", f"{hit*100:.0f}%" if hit is not None else "—", f"{n_res} resolved"),
                ("lift vs chance", f"{lift:+.2f}x" if lift is not None else "—", "skill over base rate"),
                ("brier score", f"{brier:.3f}" if brier is not None else "—", "lower is better")]

    if today < KICKOFF:                                        # truly pre-tournament
        return [("claims registered", str(n_tot), "timestamped, falsifiable"),
                ("resolved so far", "0", "skill is scored, not claimed"),
                ("status", "PRE-KICKOFF", "scorecard arms Jun 11")]

    # Tournament has started but no round has fully resolved yet (group stage in progress)
    n_played = 0
    try:
        with open(results_path) as f:
            n_played = len((_json.load(f) or []))
    except Exception:
        pass
    return [("claims registered", str(n_tot), "timestamped, falsifiable"),
            ("matches played", str(n_played), "feed live results → re-forecast"),
            ("status", "GROUP STAGE", "advance scored after Jun 27")]


def _bracket_score_html(path=BRACKET_SCORE):
    """The knockout-bracket scorecard: a round-weighted points race (market vs both models) plus,
    per round, each side's headline pick and — once that round resolves — how many it got right.
    Frozen pre-tournament; arms at the Round of 32. Returns '' if the scorecard file is absent."""
    try:
        import json as _json
        with open(path) as f:
            d = _json.load(f)
    except Exception:
        return ""
    # The bracket POINTS race is Market vs the Informed (Elo) model. The zero-knowledge model only
    # re-shapes the market's own prices (a monotonic de-vig), so its *ranking* — and therefore its
    # whole bracket — is identical to the market's by construction; it can't disagree on who goes how
    # far. ZK instead earns its score on calibration (Brier, magnitudes), shown on the Methodology
    # scorecard. So we show the one genuine bracket disagreement here.
    PLAYERS = [("market", "Market", "world"), ("elo", "Informed · Elo", "eloc")]
    pts = d.get("points", {})
    n_res = d.get("n_resolved", 0)
    pills = "".join(
        f'<div class="bsp {cls}"><span class=bspl>{lbl}</span>'
        f'<span class=bspv>{pts.get(key, 0)}</span><span class=bspu>pts</span></div>'
        for key, lbl, cls in PLAYERS)
    champ = d.get("champions", {})
    champ_row = " · ".join(
        f'{lbl}: {WM.flag_img(champ[key])}<b>{WM.code(champ[key])}</b>'
        for key, lbl, _c in PLAYERS if champ.get(key))

    def _chips(teams, cls):
        return "".join(f'<span class="bsc {cls}">{WM.flag_img(t)}{WM.code(t)}</span>' for t in teams) or "—"

    rows = []
    for r in d.get("levels", []):
        k = r["slots"]
        agree = r.get("agree", k)
        if r.get("resolved"):                              # scored: show each side's hit count
            mid = "".join(
                f'<span class="bshit {"pos" if r["hits"].get(key) else "neg"}" title="{lbl}">'
                f'{r["hits"].get(key, 0)}/{k}</span>' for key, lbl, _c in PLAYERS)
            mid = f'<td class=bsmid>{mid}</td>'
        else:                                              # pre-result: where the brackets disagree
            con = r.get("contested", {})
            cm, ck = con.get("model", []), con.get("market", [])
            diff = (f'{_chips(cm, "model")}{" vs " if cm and ck else ""}{_chips(ck, "world")}'
                    if (cm or ck) else '<span class=sub>identical picks</span>')
            mid = f'<td class=bsmid><span class=bsa>agree {agree}/{k}</span> {diff}</td>'
        rows.append(f'<tr><td class=team>{r["label"]}</td><td class=sub>×{r["weight"]}</td>{mid}</tr>')

    status = (f'<b>{n_res}</b> round{"s" if n_res != 1 else ""} scored — points are live'
              if n_res else 'arms at the <b>Round of 32</b> (Jun 28) — frozen now, scored as it plays')
    head = ('<th class=l>Round</th><th>Wt</th><th>Model vs market &amp; result</th>' if n_res
            else '<th class=l>Round</th><th>Wt</th><th>Where the brackets disagree '
                 '<span class=sub>(<span class=eloc>model</span> picks vs <span class=world>market</span> picks)</span></th>')
    return (
        '<h2 id=bracketscore>Bracket score '
        '<span class=sub>— scoring the knockout call, market vs model</span></h2>'
        '<p class=note>The bracket above is a projection; this keeps it honest. Each side fills the '
        'bracket from its <i>own</i> probabilities (the top teams per round); a correctly placed team '
        'scores that round\'s weight — <b>Last-32 ×1 · QF ×4 · SF ×8 · Final ×16 · Champion ×32</b>. '
        f'Forecasts are timestamped pre-tournament; {status}.</p>'
        f'<div class=bsrace>{pills}</div>'
        + (f'<p class=note>🏆 To lift the trophy — {champ_row} '
           f'<span class=sub>(they can agree on the favourite yet score very differently on the '
           f'<i>path</i> there)</span></p>' if champ_row else "")
        + f'<table class="bstab"><thead><tr>{head}</tr></thead><tbody>'
        + "".join(rows) + '</tbody></table>'
        '<p class="note sub">Only the <span class=eloc>informed</span> model and the market appear '
        'here: the <span class=model>zero-knowledge</span> model just re-shapes the market\'s own '
        'prices, so its bracket is <i>identical to the market\'s</i> by construction — it competes on '
        'calibration (Brier), not on picks. And one bracket is a single high-variance draw, so the '
        'round-by-round <a href="methodology.html">Brier scores</a> are the meaningful verdict; this '
        'points race is the legible one.</p>')


_UNFOLD_PHRASE = {"advance": "into the last 32", "reach_QF": "into the quarters",
                  "reach_SF": "into the semis", "reach_F": "into the final", "win": "to the title"}


_BMA_LEVELS = [("advance", "Last 32"), ("reach_QF", "Quarters"), ("reach_SF", "Semis"),
               ("reach_F", "Final"), ("win", "Champion")]
_BMA_MODEL_LABEL = {"zero_knowledge": "Zero-knowledge", "elo": "Informed · Elo"}
_BMA_MODEL_CLS = {"zero_knowledge": "model", "elo": "eloc"}


def _bma_html(path=BMA_PATH):
    """The ensemble (Bayesian model averaging) panel: per-rung model weights that drift with the
    scorecard, plus a plain-English explainer. Pre-tournament every weight is 50/50 and the panel
    states so; once rounds resolve the bars shift and we surface the leader per rung."""
    try:
        import json as _json
        with open(path) as f:
            d = _json.load(f)
    except Exception:
        return ""
    weights = d.get("weights", {})
    n_res = d.get("n_resolved", 0)
    models = d.get("models", ["zero_knowledge", "elo"])
    rows = []
    for lvl, lbl in _BMA_LEVELS:
        w = weights.get(lvl, {})
        if not w:
            continue
        cells = []
        for m in models:
            wv = w.get(m, 0)
            cls = _BMA_MODEL_CLS.get(m, "")
            cells.append(f'<div class="bmab {cls}" style="flex:{max(wv,0.001):.3f}" '
                         f'title="{_BMA_MODEL_LABEL.get(m, m)} weight">{wv*100:.0f}%</div>')
        leader = max(w, key=w.get) if w else None
        diff = abs(max(w.values()) - 0.5) if w else 0
        note = (f'<span class=sub>tied</span>' if diff < 0.01 else
                f'<span class="bmal {_BMA_MODEL_CLS.get(leader, "")}">'
                f'{_BMA_MODEL_LABEL.get(leader, "—").split(" · ")[0]} ahead</span>')
        rows.append(f'<tr><td class=team>{lbl}</td>'
                    f'<td class=bmabarcell><div class=bmabar>{"".join(cells)}</div></td>'
                    f'<td class=l>{note}</td></tr>')
    status = (f'<b>{n_res}</b> forecast{"s" if n_res != 1 else ""} scored — weights are drifting'
              if n_res else 'tied 50/50 per rung — will start drifting once the first round resolves')
    return (
        '<h2 id=ensemble>The ensemble '
        '<span class=sub>— a third forecast: Bayesian model averaging</span></h2>'
        '<p class=note>Rather than commit to one model, the <b>ensemble</b> averages both — weighted '
        'by each model\'s <b>per-round Brier track record</b>. The weight at each rung self-corrects: '
        'whichever model is better-calibrated <i>at that rung</i> earns a bigger share. '
        f'Pre-tournament both weight 0.5; {status}.</p>'
        '<table class="bmatab"><thead><tr><th class="l team">Round</th>'
        '<th>Model confidence (Zero-knowledge ←→ Informed · Elo)</th><th class=l>Leader</th></tr>'
        '</thead><tbody>' + "".join(rows) + '</tbody></table>'
        '<p class="note sub">Why average? Combined forecasts beat their components on average — a '
        'replicated finding across forecasting (IPCC averages climate models, BoE averages inflation '
        'models, ensembles routinely win Kaggle). The catch with one tournament: weights move modestly '
        'and the ensemble itself is now a third <a href="methodology.html">falsifiable</a> claim.</p>')


def _evolution_html(fundamental, pred_path=PREDICTIONS, results_path=RESULTS_PATH):
    """The 'as it unfolds' panel — how the model has moved since kickoff + the biggest shocks.
    Dormant until games are played (so it never looks broken pre-tournament)."""
    import json as _json
    import wc_evolution as EV

    results = load_results(results_path)
    head = ('<h2 id=unfolds>As it unfolds '
            '<span class=sub>— how the model moved since kickoff, and the biggest shocks</span></h2>')
    if not results:                                          # pre-tournament: dormant, but inviting
        return (head + '<p class=note>🔮 Lights up once the first games are played. The informed model '
                're-forecasts after every result, so this will show <b>how it changed its mind</b> '
                '(title odds rising and falling) and the <b>biggest surprises</b> — with whether the '
                '<span class=eloc>model</span> or the <span class=world>market</span> saw them coming. '
                'World Cups always spring a few.</p>')

    KICK = KICKOFF.isoformat()
    preds = []
    try:
        with open(pred_path, encoding="utf-8") as f:
            preds = [_json.loads(l) for l in f if l.strip()]
    except (FileNotFoundError, ValueError):
        preds = []
    committed = {}                                           # the kickoff-frozen forecast per (model,level,team)
    for p in preds:
        if p.get("date", "9999") <= KICK:
            k = (p["model"], p["level"], p["team"])
            if k not in committed or p["date"] >= committed[k]["date"]:
                committed[k] = p
    nz = WM.WL._norm
    frozen_win = {t: r["prob"] for (m, l, t), r in committed.items() if m == "elo" and l == "win"}
    live_win = {nz(t): v for t, v in fundamental.get("win", {}).items()}
    # 0.005 (0.5pp) is the right threshold for the in-tournament phase: title-odds barely move per
    # match because most groups have 4+ matches still to play; 2pp would only fire after the QFs.
    moves = EV.forecast_moves(frozen_win, live_win, top=6, min_delta=0.005)
    # Match-level upsets: each played match's actual outcome scored against its pre-match prior.
    # Prefer cached Polymarket pre-match prices (sharper than Elo, since they integrate every
    # trader's info); fall back to Elo where we don't have a Polymarket snapshot.
    # Use UNSHRUNK Elo (raw eloratings.net + host bonus) for the single-match prior. The default
    # `WF.ratings()` shrinks toward the field mean — appropriate for full-tournament Monte Carlo
    # paths, but it collapses Spain↔Cape Verde to ~half its real Elo gap and severely
    # under-rates the surprise of a draw there. `shrink=1.0` keeps the real gap.
    ratings = WF.ratings(shrink=1.0)
    polymarket_prices = {}
    try:
        with open(MATCH_PRICES_PATH, encoding="utf-8") as f:
            cache = _json.load(f) or {}
        for _key, entry in cache.items():
            if entry.get("source") != "polymarket":
                continue
            a_lc, b_lc = (entry.get("a") or "").lower(), (entry.get("b") or "").lower()
            sorted_key = tuple(sorted([a_lc, b_lc]))
            # store as (pa, pd, pb) ALPHABETIZED order
            if a_lc < b_lc:
                polymarket_prices[sorted_key] = (entry["pa"], entry["pd"], entry["pb"])
            else:
                polymarket_prices[sorted_key] = (entry["pb"], entry["pd"], entry["pa"])
    except (FileNotFoundError, ValueError):
        polymarket_prices = {}
    upsets = EV.match_upsets(results, ratings, prices=polymarket_prices, top=6, min_bits=0.8)

    def _chip(t):
        return f'{WM.flag_img(t)}<b>{WM.code(t)}</b>'

    mv_html = "".join(
        f'<li>{_chip(m["team"])} <span class="{"pos" if m["delta"]>0 else "neg"}">'
        f'{m["delta"]*100:+.1f} pp</span> to win '
        f'<span class=sub>({m["frozen"]*100:.1f}% → {m["live"]*100:.1f}%)</span></li>'
        for m in moves) or '<li class=sub>no notable swings in title odds yet</li>'
    def _src_label(u):
        return ("pre-match Polymarket" if u.get("source") == "polymarket"
                else "pre-match Elo")
    up_html = "".join(
        '<li>' + (
            f'{_chip(u["winner"])} <b>{u["ga"]}-{u["gb"]}</b> '
            f'{_chip(u["b"] if u["winner"]==u["a"] else u["a"])}'
            if u["winner"] else
            f'{_chip(u["a"])} <b>{u["ga"]}-{u["gb"]}</b> {_chip(u["b"])} (draw)'
        ) + (
            f' <span class=sub>({_src_label(u)}: '
            f'<span class="{"pos" if u["winner"]==u["a"] else ""}">{u["pa"]*100:.0f}%</span>'
            f' / draw {u["pd"]*100:.0f}% / '
            f'<span class="{"pos" if u["winner"]==u["b"] else ""}">{u["pb"]*100:.0f}%</span>'
            f' · <b>{u["bits"]:.1f} bits</b>)</span></li>'
        ) for u in upsets) or '<li class=sub>no big upsets yet — the favourites are holding</li>'
    return (head
            + '<div class=grid><div><h3>Biggest forecast moves <span class=sub>(title odds since '
            'kickoff)</span></h3><ul class=evlist>' + mv_html + '</ul></div>'
            '<div><h3>Biggest match upsets <span class=sub>(played matches the markets didn\'t see '
            'coming)</span></h3><ul class=evlist>' + up_html + '</ul></div></div>'
            '<p class="note sub">Surprise is measured in <b>bits</b> (−log₂ of the chance given) — a '
            'coin-flip that lands is 1 bit, a 1-in-8 is 3. Each upset shows the prior used: '
            '<b>pre-match Polymarket</b> when we have a captured pre-match snapshot from the CLOB '
            'history (the sharper benchmark — real money, integrating every trader\'s info), '
            'otherwise <b>pre-match Elo</b> (a reproducible fallback). The frozen kickoff call is '
            'the headline; this is the living companion.</p>')


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


SURV_LABELS = ("Out in groups", "Round of 32", "Round of 16", "Quarter-final",
               "Semi-final", "Runner-up", "Champion")


def _title_race(groups, paths, top=12):
    """The champion distribution as a sorted bar list, plus the single most-likely final (and how
    rare even that is) — reframing the projection from a prediction into a distribution."""
    nz = WM.WL._norm
    ch = paths.get("champions", {})
    field = [t for ts in groups.values() for t in ts]
    teams = sorted(field, key=lambda t: -ch.get(nz(t), 0))[:top]
    mx = max((ch.get(nz(t), 0) for t in teams), default=0) or 1
    rows = "".join(
        f'<div class=tracerow><span class=trk>{WM.flag_img(t)}<b>{WM.code(t)}</b></span>'
        f'<span class=ttrack><span class=tfill style="width:{ch.get(nz(t), 0) / mx * 100:.1f}%"></span></span>'
        f'<span class=tpc>{ch.get(nz(t), 0) * 100:.1f}%</span></div>' for t in teams)
    fin = paths.get("finals", [])
    fact = ""
    if fin:
        a, b, fp = fin[0]
        fact = (f'<div class=finfact>📊 Most-likely final: <b>{_disp(a)}</b> vs <b>{_disp(b)}</b> '
                f'&mdash; yet that exact pairing lands in only <b>{fp * 100:.1f}%</b> of the runs. '
                f'No single outcome is likely; the spread <i>is</i> the forecast. These bars are the whole '
                f'distribution &mdash; the bracket lower down is just its one most-likely path.</div>')
    return fact + f'<div class=trace>{rows}</div>'


def _survival(groups, paths):
    """Each team's EXIT-round distribution as one stacked bar — the canonical 'how far does this
    team go' view, faithful to all 20k runs. Sorted by title odds (champion %) so the order matches
    the shareable distribution chart; expected depth breaks ties for teams with ~0 title odds."""
    nz = WM.WL._norm
    dep = paths.get("depth", {})
    field = [t for ts in groups.values() for t in ts]

    def champ_p(t):
        d = dep.get(nz(t), [])
        return d[-1] if d else 0.0

    def edepth(t):
        return sum(i * p for i, p in enumerate(dep.get(nz(t), [])))
    rows = []
    for t in sorted(field, key=lambda t: (-champ_p(t), -edepth(t))):
        d = dep.get(nz(t), [])
        if not d:
            continue
        segs = "".join(
            f'<span class="sv s{i}" style="width:{p * 100:.2f}%" title="{SURV_LABELS[i]}: {p * 100:.0f}%"></span>'
            for i, p in enumerate(d) if i < len(SURV_LABELS))
        rows.append(
            f'<div class=survrow><span class=survteam>{WM.flag_img(t)}<b>{WM.code(t)}</b></span>'
            f'<span class=survbar>{segs}</span>'
            f'<span class=survpc title="champion %">{(d[-1] if d else 0) * 100:.0f}%</span></div>')
    legend = '<div class=survleg>' + "".join(
        f'<span class=slg><span class="sdot s{i}"></span>{lab}</span>'
        for i, lab in enumerate(SURV_LABELS)) + '</div>'
    return legend + f'<div class=surv>{"".join(rows)}</div>'


def _progression(fundamental, groups, top=10):
    """The field narrowing round by round: each knockout round is a full bar (its slots), filled by
    each leading team's share = P(reach that round). A fixed colour per contender turns it into a
    'flow' — you watch the favourites' slivers widen as the field thins toward one champion."""
    nz = WM.WL._norm
    ROUNDS = [("advance", "Round of 32", 32), ("reach_R16", "Round of 16", 16),
              ("reach_QF", "Quarter-finals", 8), ("reach_SF", "Semi-finals", 4),
              ("reach_F", "Final", 2), ("win", "Champion", 1)]
    PAL = ["#4f7ce8", "#3fd9a3", "#8b6dff", "#e9b949", "#f2876c", "#5aa0e0",
           "#b1a1ff", "#63e6b8", "#f0bf49", "#9aa7c7"]
    win = fundamental.get("win", {})
    field = [t for ts in groups.values() for t in ts]
    leaders = sorted(field, key=lambda t: -win.get(nz(t), 0))[:top]
    color = {nz(t): PAL[i % len(PAL)] for i, t in enumerate(leaders)}
    rows = []
    for lvl, lab, slots in ROUNDS:
        d = fundamental.get(lvl, {})
        segs, used = [], 0.0
        for t in leaders:
            p = d.get(nz(t), 0.0)
            if p <= 0:
                continue
            w = p / slots * 100
            used += w
            lbl = WM.code(t) if w >= 7 else ""
            segs.append(f'<span class=pseg style="width:{w:.2f}%;background:{color[nz(t)]}" '
                        f'title="{html.escape(_name(nz(t)))}: {p*100:.0f}% to reach the {lab}">{lbl}</span>')
        rest = max(0.0, 100 - used)
        if rest > 0.2:
            segs.append(f'<span class="pseg field" style="width:{rest:.2f}%" title="the rest of the field">'
                        f'{"field" if rest >= 12 else ""}</span>')
        rows.append(f'<div class=progrow><span class=proglab>{lab}'
                    f'<span class=progn>{slots} {"slot" if slots == 1 else "slots"}</span></span>'
                    f'<span class=progbar>{"".join(segs)}</span></div>')
    leg = "".join(f'<span class=plg><span class=pdot style="background:{color[nz(t)]}"></span>{WM.code(t)}</span>'
                  for t in leaders)
    return (f'<div class=progleg>{leg}<span class=plg><span class="pdot field"></span>field</span></div>'
            f'<div class=prog>{"".join(rows)}</div>')


def _outcome_map(fundamental, positions, groups, n_sims=20000, paths=None):
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
                f'{WM.flag_img(team)}<span class=bc>{WM.code(team)}</span>'
                f'<span class=bnf style="width:{p*100:.0f}%"></span></div>')

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
    dist = ""
    if paths:
        dist = (
            f'<h3>Title race <span class=sub>— P(win the cup) across {n_sims//1000}k simulations</span></h3>'
            f'{_title_race(groups, paths)}'
            f'<h3>How far each team goes <span class=sub>— the full distribution of where the model has '
            f'each team bow out (champion % at right)</span></h3>'
            f'{_survival(groups, paths)}'
            f'<h3>The field narrows <span class=sub>— who fills each round\'s slots; one colour per '
            f'contender, so each is a stream you can follow</span></h3>'
            f'{_progression(fundamental, groups)}')
    return (
        f'<h2 id=outcome>Outcome map '
        f'<span class=sub>— the <span class=eloc>informed</span> model\'s projection</span></h2>'
        f'<p class=note>What the informed Elo model expects, from <b>{n_sims//1000}k simulations</b> of the '
        f'verified bracket — these are the <b>model\'s</b> probabilities, not the market\'s. A 20k-run '
        f'simulation is a <b>distribution</b>, not a single prediction, so we lead with the spread of '
        f'outcomes and keep the single most-likely bracket for last.</p>'
        f'{dist}'
        f'<h3>Projected group stage <span class=sub>(advance %)</span></h3>'
        f'<p class=note><span class=qd></span> top-2 qualify, <span class=md></span> 3rd may sneak through '
        f'as a best-third; order is the model\'s expected finish.</p>'
        f'<div class=groups>{"".join(gcards)}</div>'
        f'<h3>The single most-likely bracket <span class=sub>— one path among many; node shading = % to '
        f'reach that round, real FIFA R32 slots, model placement</span></h3>{bracket}'
        f'<p class=note>This is the <b>modal</b> path — it plays out in only a minority of runs. The '
        f'<b>title race</b> and <b>how-far-each-team-goes</b> charts above are the fuller, more honest read '
        f'of the simulation.</p>'
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
 .wvp-pill{display:flex;align-items:center;gap:8px;border:1.5px solid var(--model);background:var(--panel);
   color:var(--ink);border-radius:22px;padding:10px 15px;font-size:13.5px;cursor:pointer;
   box-shadow:0 6px 22px rgba(0,0,0,.3);animation:wvp-glow 2.4s ease-in-out infinite}
 .wvp-pill:hover{transform:translateY(-1px);animation:none;box-shadow:0 9px 28px rgba(0,0,0,.4)}
 .wvp-go{background:var(--model);color:#fff;border-radius:7px;padding:2px 9px;font-weight:700;font-size:12px}
 @keyframes wvp-glow{0%,100%{box-shadow:0 6px 22px rgba(0,0,0,.3),0 0 0 0 rgba(79,124,232,.55)}
   55%{box-shadow:0 6px 22px rgba(0,0,0,.3),0 0 0 8px rgba(79,124,232,0)}}
 @media(prefers-reduced-motion:reduce){.wvp-pill{animation:none}}
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
 .wvp-fill{display:block;height:100%;background:#f0bf49;border-radius:4px}
 .wvp-tick{position:absolute;top:-2px;width:2px;height:20px}
 .wvp-pc{width:34px;flex:none;text-align:right;font-weight:700;color:#f0bf49}
 .wvp-foot{font-size:10.5px;color:var(--ink3);margin-top:9px;display:flex;justify-content:space-between;align-items:center}
 .wvp-foot a{color:var(--ink3)} .wvp-key{font-size:10px;color:var(--ink3);margin:2px 0 0}
 .wvp-key b{font-weight:700}
 @media(max-width:600px){.wvp-card{width:calc(100vw - 32px)}}
</style>
<div id="wvp">
 <button class="wvp-pill" id="wvp-pill">&#128499;&#65039; <b>Who wins the Cup?</b> <span class="wvp-go">Vote</span></button>
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
 byMkt.slice(0,7).forEach(function(t){
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
  // text/plain keeps this a CORS "simple request" (no preflight); the Worker parses the body as JSON regardless.
  fetch(EP+"/vote",{method:"POST",headers:{"Content-Type":"text/plain"},body:JSON.stringify({team:chosen})})
   .then(function(r){return r.json();}).then(function(d){
     try{localStorage.setItem("wvm-vote-2026",chosen);}catch(e){} voted=chosen; render(d);
   }).catch(function(){voteB.textContent="Vote";voteB.classList.add("on");res.hidden=false;res.innerHTML='<div class="wvp-key">Couldn’t reach the poll &mdash; a browser extension or your network/firewall may be blocking it. Try a different network, or allow this site, then reload.</div>';});
 };
 function load(force){ fetch(EP+"/results").then(function(r){return r.json();}).then(render)
   .catch(function(){show(res,true);res.innerHTML='<div class="wvp-key">Couldn’t load results &mdash; a browser extension or your network/firewall may be blocking the poll. Try a different network, or allow this site, then reload.</div>';}); }
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
               elo_core_path=ELO_CORE_LEDGER, elo_live_path=ELO_LIVE_LEDGER, paths=None):
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
                       "re-evaluated daily; it <b>cuts</b> a leg the model turns against, <b>rotates</b> "
                       "into a clearly bigger edge, and <b>rides winners to settlement</b> — any day, not "
                       "only matchdays. Open positions marked to today's prices."))
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
                       "<b>cuts</b> a leg the model turns against, <b>rotates</b> into a clearly bigger "
                       "edge, and otherwise <b>rides winners to settlement</b> — so it tracks Buy &amp; "
                       "Hold until the first trigger."))
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
                    're-checked daily; a step (settle a resolved market · cut a leg the model turns against · '
                    'rotate into a clearly bigger edge · redeploy the freed, same-side capital) appears here '
                    'whenever a trigger clears the cost buffer — any day, not only matchdays.</p>')

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
    bracket_score_html = _bracket_score_html()               # the knockout bracket scorecard
    bma_html = _bma_html()                                   # the ensemble (BMA) panel
    evolution_html = _evolution_html(fundamental) if fundamental else ""   # 'as it unfolds' (dormant pre-tournament)
    outcome_html = (_outcome_map(fundamental, positions, WM.WL.GROUPS_2026, paths=paths)
                    if (fundamental and positions) else "")
    fixtures_html = _fixtures(WM.WL.GROUPS_2026)
    poll_widget = _poll_widget(POLL_ENDPOINT)                 # bottom-left fan poll (only if configured)

    # ---- the evidence, gathered into ONE segmented surface (board · vig · outcome · bracket ·
    #      fixtures). Leading with the scoreboard and tucking the dense tables behind tabs is what
    #      keeps the page from reading as a wall of numbers — only one view is on screen at a time.
    legend_html = (
        '<div class=legend><span class="dot" style="background:var(--world)"></span><b>Market</b> = live '
        '<a href="https://polymarket.com/sports/world-cup" target=_blank rel="noopener noreferrer">Polymarket ↗</a> '
        'prices, de-vigged so each round sums to its slots (32 advance · 8 QF · 4 SF · 2 final · 1 win). '
        '<span class="dot" style="background:var(--model)"></span><b>Model</b> = pick one below. '
        '<b>Edge</b> = model − market.'
        '<button class=rst onclick="resetSort()" title="Reset table sorting">↺ reset sort</button></div>')
    mhint_html = ('<div class=mhint>↔ swipe the table sideways · the QF/SF/final columns are hidden on '
                  'small screens (tap a team for its full route)</div>')
    board_pane = f'{legend_html}{model_toggle}<div class=scroll>{board}</div>{mhint_html}'
    vig_pane = (
        '<div class=grid><div><h3>The market’s hidden vig</h3>'
        '<details class=exp><summary>How to read this</summary>'
        '<p class=note>Add up every team’s price in a round and it sums to <i>more</i> than the real '
        'number of slots (32 advance, 1 champion…). That excess is the market’s built-in margin — the '
        '<b>overround</b>, or <b>vig</b>; a bigger overround means a fatter, less efficient market. We '
        'strip it out (de-vig) before comparing anyone to the crowd.</p></details>'
        '<table class="vig sortable"><thead><tr><th class="team l" data-c=0>Round</th>'
        '<th data-c=1>Sums to</th><th data-c=2>Slots</th><th data-c=3>Overround</th></tr></thead>'
        f'<tbody>{vig}</tbody></table></div>'
        '<div><h3>Riskless inconsistencies <span class=sub>— checked daily; tradeable any day</span></h3>'
        '<details class=exp><summary>What this means</summary>'
        '<p class=note>Where the ladder’s own prices break nesting (a team priced likelier to go far '
        'than to go less far) — a risk-free edge that can open on a quiet day, not just a matchday.</p>'
        f'</details><ul>{arbs}</ul></div></div>')
    # The hero VISUALS (outcome map + bracket scorecard) are promoted to their own top-level sections
    # (see the body below) so they're discoverable in one click — not buried behind a tab. The Evidence
    # control keeps only the *dense data* tables: the board, the vig/gaps, the fixtures.
    segs = [("board", "⚽ The board", board_pane), ("vig", "💸 Vig &amp; gaps", vig_pane),
            ("fixtures", "📅 Fixtures", fixtures_html)]
    seg_btns = "".join(
        f'<button class="sgb{" on" if i == 0 else ""}" id=sg-{k} onclick="seg(\'{k}\')">{lbl}</button>'
        for i, (k, lbl, _b) in enumerate(segs))
    seg_panes = "".join(
        f'<div class="epane{"" if i == 0 else " hidden"}" id=ev-{k}>{b}</div>'
        for i, (k, _l, b) in enumerate(segs))
    evidence_html = (
        '<section id=evidence class=secsec><span class=eyebrow>The underlying data</span>'
        '<h2 id=board>The evidence <span class=sub>— market vs model, one view at a time</span></h2>'
        '<div class=seghint>👆 tap a tab to switch view</div>'
        f'<div class=seg role=tablist>{seg_btns}</div>{seg_panes}</section>')
    # the promoted hero sections (rendered high on the page, right after the disagreements)
    outcome_section = (f'<section id=outcomesec>{outcome_html}</section>' if outcome_html else "")
    bracket_section = (f'<section id=bracketsec>{bracket_score_html}</section>' if bracket_score_html else "")
    bma_section = (f'<section id=bmasec>{bma_html}</section>' if bma_html else "")

    icon = BRAND_ICON                                         # crisp tiny favicon
    mark = _brand_mark()                                      # the Canva emblem (brand + hero)
    desc = ("Can a model beat the World Cup market? A zero-knowledge model (price structure) and an "
            "informed model (Elo) take on the crowd across all 240 markets — scored publicly. Research only.")
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">{_analytics_beacon()}
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
 .nav{{display:flex;gap:13px;margin-left:auto;font-size:13px;flex-wrap:nowrap}}
 .nav a{{color:var(--ink3);text-decoration:none;white-space:nowrap}}
 .nav a:hover{{color:var(--ink)}}
 .burger{{display:none;margin-left:auto;background:var(--raise);border:1px solid var(--line3);color:var(--ink);
   border-radius:8px;width:34px;height:30px;cursor:pointer;font-size:15px;line-height:1;
   align-items:center;justify-content:center}}
 @media(max-width:880px){{
   .burger{{display:flex}}
   .nav{{position:absolute;top:100%;left:0;right:0;margin:0;display:none;flex-direction:column;gap:0;
     background:var(--bg);border-bottom:1px solid var(--line2);box-shadow:0 12px 26px rgba(0,0,0,.28);padding:4px 0}}
   .top.open .nav{{display:flex}}
   .nav a{{padding:12px 22px;font-size:15px;border-top:1px solid var(--line)}}
 }}
 @media(max-width:480px){{.brand .bt{{display:none}}}}
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
 .bsrace{{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 4px}}
 .bsp{{flex:1 1 150px;border:1px solid var(--line2);border-radius:11px;padding:9px 12px;background:var(--panel);
   display:flex;align-items:baseline;gap:7px;border-left:3px solid var(--ink3)}}
 .bsp.world{{border-left-color:var(--world)}} .bsp.model{{border-left-color:var(--model)}} .bsp.eloc{{border-left-color:var(--elo)}}
 .bsp .bspl{{font-size:11px;color:var(--ink2);font-weight:600;flex:1}} .bsp .bspv{{font-size:24px;font-weight:800;letter-spacing:-.5px}}
 .bsp .bspu{{font-size:11px;color:var(--ink3)}}
 table.bstab{{width:100%;margin:6px 0}} table.bstab th,table.bstab td{{padding:6px 7px;text-align:left;vertical-align:middle}}
 table.bstab td.sub{{text-align:center;color:var(--ink3)}} table.bstab td.team{{font-weight:600;white-space:nowrap}}
 table.bstab img.flag{{vertical-align:-2px;margin-right:2px}}
 .bsmid{{font-size:12px}} .bsa{{color:var(--ink3);font-size:11px;margin-right:6px}}
 .bsc{{display:inline-flex;align-items:center;gap:2px;font-weight:700;font-size:11px;border:1px solid var(--line2);
   border-radius:6px;padding:1px 6px;margin:1px 3px 1px 0}}
 .bsc.model{{border-color:var(--model);color:var(--ink)}} .bsc.world{{border-color:var(--world);color:var(--ink)}}
 .bshit{{font-weight:700;font-size:12px;padding:1px 7px;border-radius:6px;border:1px solid var(--line2);margin-right:5px}}
 .bshit.pos{{color:var(--pos);border-color:var(--pos)}} .bshit.neg{{color:var(--neg)}}
 /* ---- BMA panel: the model-weights bar that drifts as forecasts resolve ---- */
 table.bmatab{{width:100%;margin:8px 0}} table.bmatab td,table.bmatab th{{padding:7px 8px;vertical-align:middle}}
 table.bmatab th.l,table.bmatab td.l,table.bmatab td.team{{text-align:left}}
 .bmabarcell{{padding:6px 8px}}
 .bmabar{{display:flex;height:18px;border:1px solid var(--line2);border-radius:6px;overflow:hidden;min-width:160px}}
 .bmab{{display:flex;align-items:center;justify-content:center;color:#fff;font-size:11px;font-weight:700;
   transition:flex .4s ease}}
 .bmab.model{{background:var(--model)}} .bmab.eloc{{background:var(--elo)}}
 .bmal{{font-weight:700;font-size:12px}} .bmal.model{{color:var(--model)}} .bmal.eloc{{color:var(--eloink)}}
 ul.evlist{{list-style:none;padding:0;margin:4px 0}} ul.evlist li{{padding:6px 0;border-bottom:1px solid var(--line);font-size:13px}}
 ul.evlist li img.flag{{vertical-align:-2px;margin-right:4px}} ul.evlist .sub{{color:var(--ink3)}}
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
 .bwrap{{overflow-x:auto;-webkit-overflow-scrolling:touch;
   /* break the bracket out of the centred column so it fits without scrolling on wide screens,
      capped so it doesn't sprawl on huge monitors and never wider than the viewport */
   width:min(100vw - 24px, 1320px);margin:6px 0 6px 50%;transform:translateX(-50%)}}
 .blabels{{display:flex;min-width:1120px;margin-bottom:5px}}
 .blabels span{{flex:1;text-align:center;color:var(--ink3);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px}}
 .bracket{{display:flex;min-width:1120px;align-items:stretch}}
 .bcol{{flex:1;display:flex;flex-direction:column;justify-content:space-around;gap:5px;padding:0 3px}}
 .bcol.bmid{{flex:1.25;justify-content:center}}
 .bn{{display:flex;align-items:center;justify-content:center;gap:5px;background:var(--panel);
   border:1px solid var(--line2);border-radius:7px;padding:4px 5px;white-space:nowrap;position:relative;overflow:hidden}}
 .bnf{{position:absolute;left:0;bottom:0;height:3px;background:var(--elo);opacity:.6}}
 .bn .bc{{font-weight:700;color:var(--ink2);font-size:11px;letter-spacing:.3px}}
 .bn.bne{{opacity:.35;color:var(--ink3)}}
 .bn img.flag{{margin:0}}
 .bchamp{{background:var(--elowash);border:1.5px solid var(--elo);border-radius:12px;padding:10px 8px;text-align:center}}
 .bchamp img.flag{{margin:0 auto 4px;display:block;width:33px;height:25px}}
 .bchamp .bcn{{font-weight:700;font-size:14px;font-family:'Space Grotesk',Inter,sans-serif}}
 .bchamp .bct{{color:var(--eloink);font-weight:700;font-size:11px;text-transform:uppercase;letter-spacing:.4px;margin-top:2px}}
 /* ---- title race: champion distribution as sorted bars + the most-likely-final fact ---- */
 .finfact{{background:var(--panel);border:1px solid var(--line2);border-left:3px solid var(--elo);
   border-radius:10px;padding:9px 12px;font-size:12.5px;color:var(--ink2);margin:6px 0 12px;line-height:1.5}}
 .finfact b{{color:var(--ink)}}
 .trace,.surv{{margin:4px 0 6px}}
 .tracerow,.survrow{{display:flex;align-items:center;gap:9px;margin:3px 0}}
 .trk,.survteam{{width:62px;flex:none;font-size:12px;font-weight:600;display:flex;align-items:center;gap:5px}}
 .ttrack{{flex:1;height:14px;background:var(--bg);border:1px solid var(--line);border-radius:5px;overflow:hidden}}
 .tfill{{display:block;height:100%;background:linear-gradient(90deg,#caa23a,#e9b949);border-radius:4px}}
 .tpc,.survpc{{width:46px;flex:none;text-align:right;font-weight:700;font-size:12px;color:#e9b949;
   font-variant-numeric:tabular-nums}}
 /* ---- survival: each team's exit-round distribution as one stacked bar ---- */
 .survbar{{flex:1;height:14px;display:flex;border-radius:4px;overflow:hidden;background:var(--bg);border:1px solid var(--line)}}
 .survbar .sv{{height:100%;display:block}}
 .slg{{display:flex;align-items:center;gap:5px}}
 .sdot{{width:10px;height:10px;border-radius:2px;display:inline-block;flex:none}}
 .s0{{background:var(--line3)}} .s1{{background:#3a5a9c}} .s2{{background:#4f7ce8}} .s3{{background:#5aa0e0}}
 .s4{{background:#8b6dff}} .s5{{background:#c4ccdb}} .s6{{background:#e9b949}}
 /* ---- progression funnel: who fills each round's slots, one colour per contender ---- */
 .prog{{margin:4px 0 6px}}
 .progrow{{display:flex;align-items:center;gap:9px;margin:3px 0}}
 .proglab{{width:112px;flex:none;font-size:12px;font-weight:600;display:flex;flex-direction:column;line-height:1.25}}
 .progn{{font-size:10px;color:var(--ink4);font-weight:400}}
 .progbar{{flex:1;height:18px;display:flex;border-radius:4px;overflow:hidden;background:var(--bg);border:1px solid var(--line)}}
 .pseg{{height:100%;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:800;
   color:#0c1424;overflow:hidden;white-space:nowrap}}
 .pseg.field{{background:var(--line3);color:var(--ink3)}}
 .progleg,.survleg{{display:flex;flex-wrap:wrap;gap:6px 12px;margin:8px 0;font-size:11px;color:var(--ink3)}}
 .plg{{display:flex;align-items:center;gap:4px}}
 .pdot{{width:10px;height:10px;border-radius:2px;display:inline-block;flex:none}} .pdot.field{{background:var(--line3)}}
 @media(max-width:560px){{.trk,.survteam{{width:50px}} .proglab{{width:78px}}}}
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
 /* ---- hero text block ---- */
 .herotext{{flex:1 1 320px;min-width:260px}} .herotext h1{{margin:0 0 4px}}
 /* ---- scoreboard: the three contestants, leading the page ---- */
 .sboard{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:10px 0 12px}}
 @media(max-width:620px){{.sboard{{grid-template-columns:1fr}}}}
 .sbc{{background:var(--panel);border:1px solid var(--line2);border-left:3px solid var(--ink3);
   border-radius:11px;padding:11px 14px}}
 .sbc.world{{border-left-color:var(--world)}} .sbc.model{{border-left-color:var(--model)}}
 .sbc.elo{{border-left-color:var(--elo)}}
 .sbc .sbk{{font-size:11px;font-weight:800;letter-spacing:.4px}}
 .sbc.world .sbk{{color:var(--worldink)}} .sbc.model .sbk{{color:var(--modelink)}} .sbc.elo .sbk{{color:var(--eloink)}}
 .sbc .sbv{{font-size:15px;font-weight:800;font-family:'Space Grotesk',Inter,sans-serif;margin:3px 0 1px}}
 .sbc .sbn{{font-size:11px;color:var(--ink4)}}
 /* ---- segmented control + evidence panes (one view at a time) ---- */
 .seghint{{font-size:11px;color:var(--ink3);font-weight:600;margin:2px 0 2px}}
 .seg{{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 6px;overflow-x:auto;-webkit-overflow-scrolling:touch}}
 .sgb{{background:var(--panel);border:1.5px solid var(--line2);color:var(--ink2);border-radius:10px;
   padding:11px 17px;cursor:pointer;font-size:14px;font-weight:700;white-space:nowrap;transition:transform .08s}}
 .sgb:hover{{color:var(--ink);border-color:var(--ink3);transform:translateY(-1px)}}
 .sgb.on{{color:#fff;border-color:var(--model);background:var(--model)}}
 @media(max-width:600px){{.sgb{{padding:9px 12px;font-size:13px}} .seghint{{font-size:10px}}}}
 .epane.hidden{{display:none}} #evidence h3{{margin-top:6px}}
 /* ---- mobile quick-jumps: chips just under the hero so the key sections are 1 tap away ---- */
 .qjump{{display:none;gap:8px;flex-wrap:wrap;margin:8px 0 2px}}
 .qjump a{{flex:1 1 calc(50% - 4px);text-align:center;background:var(--panel);border:1.5px solid var(--line2);
   color:var(--ink);border-radius:10px;padding:11px 8px;font-size:13px;font-weight:700;text-decoration:none;white-space:nowrap}}
 .qjump a:active{{background:var(--modelwash)}}
 @media(max-width:880px){{.qjump{{display:flex}}}}
 /* ---- collapsible 'how to read this' explainers keep the default view clean ---- */
 details.exp{{margin:6px 0 10px;border:1px solid var(--line2);border-radius:10px;background:var(--panel);padding:0 12px}}
 details.exp>summary{{cursor:pointer;color:var(--ink2);font-size:12px;font-weight:600;padding:9px 0;list-style:none}}
 details.exp>summary::-webkit-details-marker{{display:none}}
 details.exp>summary::before{{content:'\\24D8  ';color:var(--ink4)}}
 details.exp[open]>summary::before{{content:'\\25BE  '}}
 details.exp .note,details.exp ul{{margin:0 0 10px}}
 /* ---- the paper books, demoted to a clearly-secondary 'what-if' card ---- */
 .secsec{{margin-top:30px;border:1px solid var(--line2);border-radius:14px;background:var(--panel2);padding:2px 16px 16px}}
 .secsec h2{{border-bottom-color:var(--line3)}}
 .eyebrow{{display:inline-block;font-size:10px;font-weight:800;letter-spacing:.6px;text-transform:uppercase;
   color:var(--ink4);background:var(--raise);border:1px solid var(--line2);border-radius:20px;padding:2px 10px;margin:14px 0 0}}
 /* searching focuses the board: drop the surrounding furniture so results stand alone */
 body.searching #booksec,body.searching #fundamental,body.searching #evidence .seg,
 body.searching #outcomesec,body.searching #bracketsec,body.searching #bmasec,
 body.searching .sboard{{display:none}}
</style></head><body>
<div class=top>
  <span class=brand><img src="{mark}" alt="World vs Model"> World <span class=vs>vs</span> Model <span class=bt>· World Cup 2026</span></span>
  <nav class=nav><a href="#record">Scoreboard</a><a href="#cards">Disagreements</a>
    <a href="#outcome">🔮 Outcome map</a><a href="#bracketscore">🏆 Bracket score</a><a href="#ensemble">🤝 Ensemble</a><a href="#board">Board</a>
    <a href="#book">Books</a><a href="#fundamental">Model</a>
    <a href="methodology.html">Method</a><a href="faq.html">FAQ</a></nav>
  <button class=burger id=burger onclick="toggleMenu()" aria-label="Open menu" aria-expanded="false">☰</button>
  <button class=tgl id=th onclick="tg()" title="Toggle light / dark">☀️</button>
</div>
<div class=wrap>
 <div class=hero><img class=hmark src="{mark}" alt="World vs Model logo">
   <div class=herotext>
     <h1>World Cup 2026 — Can a model beat the market?</h1>
     <div class=sub2>Two transparent models take on the crowd across all 240 markets — one knows
       <b style="color:var(--worldink)">zero football</b> (just price structure), one is
       <b style="color:var(--eloink)">informed</b> (Elo ratings). We keep a public, out-of-sample scorecard.
       <a href="methodology.html">How this works →</a> &nbsp;·&nbsp; <a href="glossary.html">Glossary &amp; references →</a></div></div>
   <span class=kick>{kick}</span></div>
 <div class=byline>A research experiment by
   <a href="{AUTHOR_URL}" target=_blank rel="noopener noreferrer">{AUTHOR_NAME} ↗</a>
   &nbsp;·&nbsp; <span class=pill>updated <b>{stamp}</b></span>
   <span class=pill><b>240</b> markets · 48 teams</span>
   <span class=pill>scored <b>vs the market</b></span></div>
 {keydates}
 <div class=qjump aria-label="Quick jumps">
   <a href="#outcome">🔮 Outcome map</a><a href="#bracketscore">🏆 Bracket score</a>
   <a href="#board">⚽ Board</a><a href="#book">💰 Books</a>
 </div>
 <section id=recordsec><h2 id=record>The scoreboard
   <span class=sub>— Track record, scored out of sample as results land</span></h2>
   <div class=sboard>
     <div class="sbc world"><div class=sbk>THE MARKET</div><div class=sbv>the line to beat</div>
       <div class=sbn>live Polymarket, de-vigged</div></div>
     <div class="sbc model"><div class=sbk>ZERO-KNOWLEDGE</div><div class=sbv>price structure</div>
       <div class=sbn>knows no football</div></div>
     <div class="sbc elo"><div class=sbk>INFORMED · ELO</div><div class=sbv>ratings + simulation</div>
       <div class=sbn>independent of the market</div></div>
   </div>
   <div class=record>{record}</div></section>
 {evolution_html}
 <div class=searchbar><span class=ball2 onclick="focusFind()" title="Find a team">⚽</span>
   <input class=find id=find type=search placeholder="Find a country or trade — e.g. France, Japan, Brazil…"
     oninput="fq(this.value)" aria-label="Find a country or trade">
   <button class=clr id=clr onclick="clearFind()" title="Clear filter" hidden>✕ reset</button>
   <span class=boot onclick="kick()" title="Kick the ball!">🦵</span></div>
 <div class=nores id=nores hidden>No team matches — try a country like <b>France</b>, <b>Japan</b> or <b>Brazil</b>.</div>
 <section id=disagree><h2 id=cards>The <span style="color:var(--world)">zero-knowledge</span> model's biggest disagreements</h2>
 {cardstrip}</section>
 {outcome_section}
 {bracket_section}
 {bma_section}
 {elo_intro_section}
 {evidence_html}
 <section id=booksec class=secsec>
   <span class=eyebrow>Secondary · what-if</span>
   <h2 id=book>If you'd traded it <span class=sub>— a paper book to keep score, not advice</span></h2>
   <details class=exp><summary>How the paper books work</summary>
   <p class=note><b>A secondary, "what-if" view</b> — purely to put a number on the disagreements above.
     No real money: a $1,000 <i>paper</i> book, conviction-weighted and dollar-neutral. Edges are shown
     <b>net of a ~{half_spread_c:.0f}c half-spread</b> — a gap that doesn't clear the cost to trade it is
     sized to zero (that half-spread is the <b>cost buffer</b>). <b>Buy &amp; Hold</b> enters once at day 0
     and holds to resolution; <b>Active Trading</b> is re-evaluated daily and rebalances whenever a market
     settles or a fresh edge clears that buffer — any day, not only matchdays (a riskless inconsistency is
     the clearest example). <a href="methodology.html">Methodology →</a></p></details>
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
 </section>
 <div class=about><img class=amark src="{mark}" alt="">
   <div><b>About.</b> A solo research &amp; education project by
   <a href="{AUTHOR_URL}" target=_blank rel="noopener noreferrer">{AUTHOR_NAME} ↗</a> — an open test of
   whether transparent models can beat a liquid market, with an honest public scorecard. Built in the
   open, scored against the crowd; <b>no positions, no capital, no advice</b>.
   <a href="faq.html">Common questions (FAQ) →</a> &nbsp;·&nbsp;
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
  if(v&&typeof seg==='function')seg('board');        // make sure the board is the visible evidence view
  if(v){{var sb=document.querySelector('.searchbar'),t=sb.getBoundingClientRect().top;
    if(t<0||t>150)sb.scrollIntoView({{behavior:'smooth',block:'start'}});}}}}
function clearFind(){{var f=document.getElementById('find');if(f){{f.value='';fq('');f.focus();}}}}
function tab(n){{document.querySelectorAll('.pane').forEach(function(p){{p.hidden=p.id!=='pane-'+n;}});
  document.querySelectorAll('.tab').forEach(function(b){{b.classList.toggle('on',b.id==='tb-'+n);b.classList.remove('pulse');}});}}
function seg(n){{document.querySelectorAll('.epane').forEach(function(p){{p.classList.toggle('hidden',p.id!=='ev-'+n);}});
  document.querySelectorAll('.sgb').forEach(function(b){{b.classList.toggle('on',b.id==='sg-'+n);}});}}
function _setMenu(open){{var t=document.querySelector('.top'),b=document.getElementById('burger');
  if(!t)return;t.classList.toggle('open',open);
  if(b){{b.setAttribute('aria-expanded',open?'true':'false');b.textContent=open?'✕':'☰';}}}}
function toggleMenu(){{_setMenu(!document.querySelector('.top').classList.contains('open'));}}
document.querySelectorAll('.nav a').forEach(function(a){{a.addEventListener('click',function(){{_setMenu(false);}});}});
(function(){{var K=['board','vig','fixtures'];var h=(location.hash||'').replace('#','');   // deep-link an Evidence tab
  if(K.indexOf(h)>=0&&typeof seg==='function'){{seg(h);var el=document.getElementById('ev-'+h);if(el)el.scrollIntoView();}}}})();
document.addEventListener('click',function(e){{var t=document.querySelector('.top');
  if(t&&t.classList.contains('open')&&!t.contains(e.target))_setMenu(false);}});
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
FAQ_MD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "docs", "faq-worldcup.md")


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
<meta name=viewport content="width=device-width,initial-scale=1">{_analytics_beacon()}
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
           f'<a href="glossary.html" style="margin-left:14px">Glossary →</a>'
           f'<a href="faq.html" style="margin-left:14px">FAQ →</a>')
    return _doc_page(md_path, "Methodology · World vs Model — World Cup 2026", "Methodology", nav)


def build_glossary_html(md_path=GLOSSARY_MD, board_href="worldcup_board.html"):
    """The glossary & references page (plain-English jargon + the source papers)."""
    nav = (f'<a href="{board_href}">← Board</a>'
           f'<a href="methodology.html" style="margin-left:14px">Methodology →</a>'
           f'<a href="faq.html" style="margin-left:14px">FAQ →</a>')
    return _doc_page(md_path, "Glossary & references · World vs Model — World Cup 2026",
                     "Glossary &amp; references", nav)


def write_share_redirects(outdir, campaign="kickoff"):
    """Tiny meta-refresh redirect pages so we can share brandable short URLs that still tag with UTMs.

    Maps `outdir/go/<channel>.html` → SITE_URL/?utm_source=<channel>&utm_medium=social&utm_campaign=…#outcome
    so a post can carry `mli3w.github.io/world-vs-model/go/linkedin` instead of an ugly query string —
    LinkedIn (which suppresses preview cards when images are attached) gets a clean visible URL, and
    Cloudflare Web Analytics still attributes the click to its channel. Reddit/X are wired the same.
    """
    go = os.path.join(outdir, "go")
    os.makedirs(go, exist_ok=True)
    for channel in ("linkedin", "reddit", "x"):
        url = f"{SITE_URL}/?utm_source={channel}&utm_medium=social&utm_campaign={campaign}#outcome"
        html = (f'<!doctype html><html lang=en><head><meta charset=utf-8>'
                f'<title>Redirecting to World vs Model…</title>'
                f'<meta http-equiv=refresh content="0;url={url}">'
                f'<link rel=canonical href="{SITE_URL}/">'
                f'<meta name=robots content="noindex">'
                f'<style>body{{font:14px/1.5 system-ui,sans-serif;background:#0c1424;color:#e9edf8;'
                f'padding:48px;text-align:center}}a{{color:#4f7ce8}}</style></head>'
                f'<body>Redirecting to <a href="{url}">World vs Model</a>…'
                f'<script>location.replace({_json_dumps(url)});</script></body></html>')
        with open(os.path.join(go, f"{channel}.html"), "w", encoding="utf-8") as f:
            f.write(html)


def _json_dumps(s):
    import json as _json
    return _json.dumps(s)


def build_faq_html(md_path=FAQ_MD, board_href="worldcup_board.html"):
    """The FAQ page (plain-language answers — distinct from the methodology and glossary)."""
    nav = (f'<a href="{board_href}">← Board</a>'
           f'<a href="methodology.html" style="margin-left:14px">Methodology →</a>'
           f'<a href="glossary.html" style="margin-left:14px">Glossary →</a>')
    return _doc_page(md_path, "FAQ · World vs Model — World Cup 2026", "FAQ", nav)


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
    paths = None if a.no_fundamental else WF.fundamental_paths(n_sims=a.sims, results=results)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)  # create the output dir (fresh checkout/CI)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(build_html(ladder=ladder, bankroll=a.bankroll, power=a.power, fundamental=fundamental,
                           positions=positions, history=history, liquidity=liquidity, paths=paths))
    print(f"[board] wrote {a.out}  (open in a browser)")
    # copy the social card next to the board so the relative og:image resolves when hosted
    _og_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "wvm_og.png")
    try:
        import shutil
        shutil.copyfile(_og_src, os.path.join(os.path.dirname(a.out) or ".", "wvm_og.png"))
    except OSError:
        print("[board] og image not found; skipped wvm_og.png")
    outdir = os.path.dirname(a.out) or "."
    write_share_redirects(outdir)                          # /go/{linkedin,reddit,x}.html → tagged URL
    for fname, builder in (("methodology.html", build_methodology_html),
                           ("glossary.html", build_glossary_html),
                           ("faq.html", build_faq_html)):
        try:
            with open(os.path.join(outdir, fname), "w", encoding="utf-8") as f:
                f.write(builder(board_href=os.path.basename(a.out)))
            print(f"[board] wrote {os.path.join(outdir, fname)}")
        except FileNotFoundError:
            print(f"[board] markdown for {fname} not found; skipped")


if __name__ == "__main__":
    main()
