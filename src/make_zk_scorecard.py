"""
make_zk_scorecard.py — the one-image LinkedIn share for the zero-knowledge book
==============================================================================
Renders `assets/wvm_zk_scorecard.png` (1200×1200, brand palette) — a clean,
single image that compresses the entire finding into one glance:

  • brand strip (logo + title in the on-board styling)
  • headline hit-rate (e.g. "13 / 26 calls correct")
  • the favourite-longshot formula (rendered mathtext)
  • two-column ledger: LONGS (favourites) left, SHORTS (longshots) right
  • per-row: team flag · FIFA code · entry price · ✓/✗ marker
  • brand footer with the live-board URL

Reads `ledger/wc_core.jsonl` + `ledger/wc_results.json` so the image always
matches the live book. Flags cached once under `assets/flags/`.

PnL deliberately NOT shown on the image — the advance markets are still trading,
so mark-to-market fluctuates. The hit-rate is the unambiguous headline. Once MD3
closes, the realised PnL goes in the post text from the live board.

    python src/make_zk_scorecard.py

Research/education only.
"""
import os
import sys
import json
import io
from collections import defaultdict

import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.offsetbox import OffsetImage, AnnotationBbox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import worldcup_fundamental as WF                            # noqa: E402
import worldcup_markets as WM                                # noqa: E402
from worldcup_live import _norm as _WL_NORM                  # noqa: E402  (same key used by register)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "ledger", "wc_core.jsonl")
RESULTS = os.path.join(ROOT, "ledger", "wc_results.json")
OUT = os.path.join(ROOT, "assets", "wvm_zk_scorecard.png")
FLAG_DIR = os.path.join(ROOT, "assets", "flags")
EMBLEM = os.path.join(ROOT, "assets", "wvm_mark.png")

# Brand palette — matches the live board's CSS variables
BG    = "#0a121c"          # background — slightly deeper than NAVY for poster contrast
NAVY  = "#0c1424"
INK   = "#f0f4ff"          # primary text
INK2  = "#aab6d4"          # secondary
INK3  = "#7c90b3"          # muted
TEAL  = "#3fd9a3"          # model green (✓ hits, longs)
BLUE  = "#4f7ce8"          # data-bar blue
VIOL  = "#8b6dff"          # brand violet (the "vs")
RED   = "#ff6470"          # ✗ misses
LINE  = "#2c3c5a"


def _fetch_flag(iso2):
    """Download flagcdn flag PNG (64×48 retina) and cache under assets/flags/."""
    if not iso2:
        return None
    os.makedirs(FLAG_DIR, exist_ok=True)
    safe = iso2.replace("/", "_")
    path = os.path.join(FLAG_DIR, f"{safe}.png")
    if os.path.exists(path):
        return path
    url = f"https://flagcdn.com/64x48/{iso2}.png"               # retina-friendly
    try:
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            with open(path, "wb") as f:
                f.write(r.content)
            return path
    except requests.RequestException:
        return None
    return None


def _compute_standings(results):
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


def _resolved_advancers(table):
    """Return (advanced, eliminated) under the 2026 format: top 2 per group + 8 best thirds.
    Third-placed teams are ranked across all 12 groups (Pts → GD → GF) and the top 8 advance —
    so we can only finalise them once ALL 12 groups have completed three games."""
    advanced, eliminated = set(), set()
    thirds = []                                                    # (team, stats)
    all_groups_done = all(
        min(table[t]["P"] for t in ts) >= 3 for ts in WF.GROUPS_2026.values())
    for g, teams in WF.GROUPS_2026.items():
        if min(table[t]["P"] for t in teams) < 3:
            continue
        standing = sorted([(t, table[t]) for t in teams],
                           key=lambda x: (-x[1]["Pts"],
                                          -(x[1]["GF"] - x[1]["GA"]),
                                          -x[1]["GF"]))
        advanced.update([standing[0][0], standing[1][0]])
        thirds.append(standing[2])                                # 3rd place — pending until all done
        eliminated.add(standing[3][0])                            # 4th — eliminated, definite
    if all_groups_done:
        thirds.sort(key=lambda x: (-x[1]["Pts"], -(x[1]["GF"]-x[1]["GA"]), -x[1]["GF"]))
        for (t, _s) in thirds[:8]:                                # 8 best thirds advance
            advanced.add(t)
        for (t, _s) in thirds[8:]:                                # bottom 4 eliminated
            eliminated.add(t)
    return advanced, eliminated


def _score_book(ledger_path, top2, eliminated):
    """Score every ADVANCE bet, returning longs & shorts separately for two-column layout."""
    rows = [json.loads(l) for l in open(ledger_path, encoding="utf-8") if l.strip()]
    advance = [r for r in rows if r["level"] == "advance"]
    # Use the SAME normalisation worldcup_register uses to write the ledger — handles edge cases
    # like "DR Congo" → "congodr" (Polymarket spells it "Congo DR") that a generic strip won't.
    name_lookup = {_WL_NORM(t): t for t in (top2 | eliminated)}
    longs, shorts, pending = [], [], 0
    for r in advance:
        real_name = name_lookup.get(_WL_NORM(r["team"]))
        is_long = r["shares"] > 0
        if real_name is None:
            pending += 1
            continue
        advanced = real_name in top2
        hit = (is_long == advanced)
        bucket = longs if is_long else shorts
        bucket.append(dict(team=real_name, entry=r["entry"], hit=hit,
                           outcome="advanced" if advanced else "out"))
    longs.sort(key=lambda r: -r["entry"])                          # favourites top
    shorts.sort(key=lambda r: r["entry"])                          # longshots top
    return dict(longs=longs, shorts=shorts, pending=pending,
                n_resolved=len(longs) + len(shorts), n_total=len(advance))


def _draw_emblem(fig, ax, x, y, size):
    """Place the brand emblem (wvm_mark.png) as a small image inside an axes overlay."""
    if not os.path.exists(EMBLEM):
        return
    img = mpimg.imread(EMBLEM)
    im = OffsetImage(img, zoom=size)
    ab = AnnotationBbox(im, (x, y), xycoords="axes fraction",
                         frameon=False, box_alignment=(0.5, 0.5))
    ax.add_artist(ab)


def _draw_flag(ax, iso2, x, y, zoom=0.32):
    path = _fetch_flag(iso2)
    if not path:
        return
    try:
        img = mpimg.imread(path)
    except Exception:
        return
    im = OffsetImage(img, zoom=zoom)
    ab = AnnotationBbox(im, (x, y), frameon=False,
                         box_alignment=(0.5, 0.5), pad=0)
    ax.add_artist(ab)


def _draw_row(ax, rec, x_left, y, row_h, bar_max_w):
    """One ledger row: flag · code · bar to entry-% · entry-% · ✓/✗.
    `x_left` is the leftmost pixel of the row; bar starts after flag+code."""
    nz = WM.WL._norm
    iso, _rank, _titles = WM.TEAM_INFO.get(nz(rec["team"]), ("", None, 0))
    code = WM.TEAM_CODE.get(nz(rec["team"]), rec["team"][:3].upper())
    colour = TEAL if rec["hit"] else RED

    # Flag (positioned centred vertically)
    _draw_flag(ax, iso, x_left + 1.4, y + row_h * 0.5, zoom=0.28)
    # 3-letter code
    ax.text(x_left + 3.4, y + row_h * 0.5, code,
            ha="left", va="center", color=INK, fontsize=10.5, weight="bold")
    # Bar
    bar_w = rec["entry"] * bar_max_w
    bar_x = x_left + 7.5
    ax.add_patch(FancyBboxPatch((bar_x, y + row_h * 0.18),
                                  bar_w, row_h * 0.62,
                                  boxstyle="round,pad=0.02,rounding_size=0.25",
                                  facecolor=colour, edgecolor="none", alpha=0.85))
    # Entry % at end of bar
    ax.text(bar_x + bar_w + 0.7, y + row_h * 0.5,
            f"{rec['entry']*100:.0f}%",
            ha="left", va="center", color=INK2, fontsize=9)
    # Outcome marker
    mark = "✓" if rec["hit"] else "✗"
    ax.text(x_left + bar_max_w + 12.5, y + row_h * 0.5, mark,
            ha="center", va="center", color=colour, fontsize=14, weight="bold")


def render(out_path=OUT):
    with open(RESULTS) as f:
        results = json.load(f) or []
    table = _compute_standings(results)
    top2, eliminated = _resolved_advancers(table)
    book = _score_book(LEDGER, top2, eliminated)
    n_complete_groups = sum(
        1 for g, teams in WF.GROUPS_2026.items()
        if min(table[t]["P"] for t in teams) >= 3)

    fig, ax = plt.subplots(figsize=(12, 12), dpi=100)
    fig.patch.set_facecolor(BG)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values(): s.set_visible(False)
    ax.set_facecolor(BG)

    # ---- top brand strip (gradient bar)
    for i in range(100):
        # Linear interp teal → blue → violet
        t = i / 99
        if t < 0.5:
            f = t * 2
            r = int(0x3f + (0x4f - 0x3f) * f); g = int(0xd9 + (0x7c - 0xd9) * f); b = int(0xa3 + (0xe8 - 0xa3) * f)
        else:
            f = (t - 0.5) * 2
            r = int(0x4f + (0x8b - 0x4f) * f); g = int(0x7c + (0x6d - 0x7c) * f); b = int(0xe8 + (0xff - 0xe8) * f)
        ax.add_patch(Rectangle((i, 99), 1, 1, facecolor=f"#{r:02x}{g:02x}{b:02x}", edgecolor="none"))

    # ---- header: emblem + wordmark + subtitle
    _draw_emblem(fig, ax, x=0.10, y=0.91, size=0.22)
    # Three independent text calls for the wordmark so the "vs" can take the brand-violet accent.
    # x positions hand-tuned at fontsize=30 — small gaps between tokens for readable spacing.
    ax.text(19.0, 94.5, "World", ha="left", va="center", color=INK,
            fontsize=30, weight="bold", family="sans-serif")
    ax.text(35.0, 94.5, "vs", ha="left", va="center", color=VIOL,
            fontsize=30, weight="bold", family="sans-serif", style="italic")
    ax.text(42.5, 94.5, "Model", ha="left", va="center", color=INK,
            fontsize=30, weight="bold", family="sans-serif")
    ax.text(19, 89.5, "2026 FIFA World Cup  ·  zero-knowledge book  ·  group stage",
            ha="left", va="center", color=INK2, fontsize=12, style="italic")

    # ---- hero hit-rate
    hit_rate = book["n_resolved"] and (
        (sum(1 for r in book["longs"] if r["hit"]) +
         sum(1 for r in book["shorts"] if r["hit"])) / book["n_resolved"]) or 0
    hits_total = sum(1 for r in book["longs"] if r["hit"]) + sum(1 for r in book["shorts"] if r["hit"])
    ax.text(50, 80, f"{hits_total} / {book['n_resolved']}",
            ha="center", va="center", color=TEAL, fontsize=78, weight="bold")
    ax.text(50, 72.5, f"advance calls correct  ·  {hit_rate*100:.0f}% hit rate",
            ha="center", va="center", color=INK, fontsize=15)
    ax.text(50, 69.5, f"({n_complete_groups}/12 groups resolved · "
                       f"{book['pending']} bets pending)",
            ha="center", va="center", color=INK3, fontsize=11, style="italic")

    # ---- formula
    ax.text(50, 61.5, r"$\widehat{p}_{i} \;=\; p_{i}^{\,\alpha}\,/\,\sum_{j} p_{j}^{\,\alpha}"
                      r"\qquad \alpha \approx 1.15$",
            ha="center", va="center", color=INK, fontsize=22)
    ax.text(50, 57, "no team names · no Elo · just one shape correction — the favourite–longshot bias "
                    "(Griffith 1949, Thaler & Ziemba 1988)",
            ha="center", va="center", color=INK3, fontsize=10, style="italic")

    # ---- column headers
    ax.text(25, 51.5, "LONGS  ·  favourites the model bought",
            ha="center", va="center", color=TEAL, fontsize=11, weight="bold")
    ax.text(75, 51.5, "SHORTS  ·  longshots the model faded",
            ha="center", va="center", color=BLUE, fontsize=11, weight="bold")
    # subtle separator
    ax.plot([50, 50], [49, 9], color=LINE, lw=0.8, alpha=0.6)

    # ---- two-column ledger
    rows_per_col = max(len(book["longs"]), len(book["shorts"]), 1)
    y_top, y_bot = 49, 9
    row_h = (y_top - y_bot) / max(rows_per_col, 1) * 0.85
    gap   = (y_top - y_bot) / max(rows_per_col, 1) * 0.15

    bar_max_w = 22                                                # of 50-wide column
    for i, r in enumerate(book["longs"]):
        y = y_top - (i + 1) * (row_h + gap)
        _draw_row(ax, r, x_left=1, y=y, row_h=row_h, bar_max_w=bar_max_w)
    for i, r in enumerate(book["shorts"]):
        y = y_top - (i + 1) * (row_h + gap)
        _draw_row(ax, r, x_left=51, y=y, row_h=row_h, bar_max_w=bar_max_w)

    # ---- footer
    ax.text(50, 5.0, "mli3w.github.io/world-vs-model",
            ha="center", va="center", color=INK, fontsize=11, weight="bold")
    ax.text(50, 2.2, "research / education only  ·  no real capital invested  ·  not financial advice",
            ha="center", va="center", color=INK3, fontsize=9)

    fig.savefig(out_path, dpi=100, facecolor=BG, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print(f"[zk-scorecard] wrote {out_path}")

    # Print clean numbers for the post body
    print("\n" + "=" * 60)
    print("POST NUMBERS")
    print("=" * 60)
    n_h = hits_total; n_r = book["n_resolved"]
    print(f"  Hit rate (now):          {n_h} / {n_r} ({hit_rate*100:.0f}%)")
    print(f"  Pending (Group J/K/L):   {book['pending']}")
    print(f"  After MD3 the total is:  {book['n_total']} advance bets")
    print(f"  Groups complete:         {n_complete_groups} / 12")
    print()
    print("  Grab PnL from the LIVE board after MD3 closes — it'll show the")
    print("  realised number once advance markets settle to 0/1.")
    print()
    return out_path


if __name__ == "__main__":
    render()
