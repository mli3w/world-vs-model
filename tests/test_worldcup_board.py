"""Tests for the World-vs-Model board generator (src/worldcup_board.py) — data-free."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
B = pytest.importorskip("worldcup_board")

# win level populated (slots=1) with a favorites->longshots spread; deeper levels empty.
LADDER = {"advance": {}, "reach_QF": {}, "reach_SF": {}, "reach_F": {},
          "win": {"fav": 0.40, "strong": 0.25, "mid": 0.12, "weak": 0.04, "dog": 0.01}}


def test_evolution_panel_dormant_then_lights_up(tmp_path):
    import json
    nz = B.WM.WL._norm
    # dormant when there are no played results
    dorm = B._evolution_html({"win": {}}, pred_path=str(tmp_path / "none.jsonl"),
                             results_path=str(tmp_path / "none.json"))
    assert "id=unfolds" in dorm and "Lights up once the first games" in dorm

    # lights up once results exist: a frozen forecast + a resolved upset, and a live swing
    pred = tmp_path / "predictions.jsonl"
    rows = [
        {"date": "2026-06-07", "model": "elo", "level": "win", "team": nz("Spain"),
         "prob": 0.17, "market": 0.16, "outcome": None},
        {"date": "2026-06-07", "model": "elo", "level": "win", "team": nz("Morocco"),
         "prob": 0.02, "market": 0.02, "outcome": None},
        {"date": "2026-06-07", "model": "elo", "level": "advance", "team": nz("Saudi Arabia"),
         "prob": 0.18, "market": 0.14, "outcome": 1},        # an upset that resolved
    ]
    pred.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    res = tmp_path / "wc_results.json"
    res.write_text(json.dumps([{"a": "Spain", "b": "Morocco", "ga": 1, "gb": 0, "stage": "group"}]), encoding="utf-8")
    live = {"win": {nz("Spain"): 0.15, nz("Morocco"): 0.16}}  # Morocco surged since kickoff
    h = B._evolution_html(live, pred_path=str(pred), results_path=str(res))
    assert "Lights up once" not in h                          # not dormant
    assert "pp</span> to win" in h                            # a forecast move rendered
    assert "made it into the last 32" in h                    # the upset surfaced as a surprise


def test_analytics_beacon_is_opt_in():
    assert B._analytics_beacon("") == ""                          # no token -> no beacon
    b = B._analytics_beacon("abc123token")
    assert "static.cloudflareinsights.com/beacon.min.js" in b     # the cookieless beacon
    assert "abc123token" in b                                     # token injected


def test_poll_widget_is_opt_in():
    assert B._poll_widget("") == ""                              # no endpoint -> nothing renders
    w = B._poll_widget("https://wvm-poll.example.workers.dev/")
    assert "wvp-pill" in w                                       # the bubble is present
    assert "https://wvm-poll.example.workers.dev" in w          # endpoint injected
    assert "not betting" in w                                    # disclaimer carried


def test_sized_book_is_bounded_and_two_sided():
    bk = B.sized_book(LADDER, bankroll=1000.0, top=3, cost=0.0)   # pure sizing (no cost netting)
    total = sum(t["stake"] for t in bk)
    assert 0 < total <= 1000.0 + 1e-6                  # capital deployed never exceeds the bankroll
    assert any(t["side"] == "LONG" for t in bk)        # favorites long
    assert any(t["side"] == "SHORT" for t in bk)       # longshots short
    for t in bk:
        assert (t["shares"] > 0) == (t["side"] == "LONG")


def test_sized_book_drops_subspread_trades():
    """With the half-spread netted, gross edges that don't clear the cost to trade are sized out."""
    gross = B.sized_book(LADDER, bankroll=1000.0, top=5, cost=0.0)
    net = B.sized_book(LADDER, bankroll=1000.0, top=5, cost=0.05)   # a big spread kills small edges
    assert len(net) < len(gross)                        # some trades fall below the spread
    assert all(abs(t["edge"]) > 0 for t in net)         # nothing sized on a zero net edge


def test_methodology_renders_latex_via_katex():
    """The methodology page wires KaTeX and the math spans survive the markdown renderer intact."""
    h = B.build_methodology_html()
    assert "katex.min.css" in h and "renderMathInElement" in h     # KaTeX is loaded + auto-rendered
    assert "@@MATH" not in h                                        # math placeholder tokens restored
    assert "$$" in h and "\\frac" in h and "\\alpha" in h          # raw LaTeX present for KaTeX


def test_methodology_back_link_matches_board_filename():
    """The 'back to the board' link must point at the board's actual hosted filename, not a default."""
    assert 'href="index.html"' in B.build_methodology_html(board_href="index.html")
    assert 'href="worldcup_board.html"' in B.build_methodology_html()   # default preserved


def test_protect_restore_math_is_lossless():
    md = r"text \(a+b\) more $$\frac{x}{y}$$ and a literal $1,000 price."
    prot, spans = B._protect_math(md)
    assert "\\(" not in prot and "$$" not in prot                  # math hidden behind tokens
    assert "$1,000" in prot                                        # a single $ amount is NOT math
    assert B._restore_math(prot, spans) == md                      # round-trips exactly


def test_build_html_has_core_sections():
    h = B.build_html(ladder=LADDER, bankroll=1000.0)
    assert "Can a model beat the market?" in h           # the reframed headline
    assert 'class="board sortable"' in h and 'class="trades sortable"' in h
    assert "not financial advice" in h                  # disclaimer present
    assert h.count("<table") == h.count("</table>")     # balanced


def test_build_html_v2_affordances():
    # a real team name so a flag renders; clarity legend + UTC timestamp + grouped header.
    ladder = dict(LADDER)
    ladder["win"] = {"Argentina": 0.30, "Spain": 0.18, "Japan": 0.08, "Panama": 0.02}
    h = B.build_html(ladder=ladder, bankroll=1000.0)
    assert "🇦🇷" in h                                    # flags beside country names
    assert "UTC" in h                                    # timestamped (date + time)
    assert "What this works" not in h                    # (typo guard)
    assert "How this works" in h                         # methodology link text
    assert 'class="grp world"' in h and 'class="grp model"' in h   # World vs Model header group
    assert "Polymarket" in h and "Model" in h            # the legend names both sides
    # no tracked ledger in the test env -> the proposed-book path with an Edge column.
    assert "proposed day-0 book" in h
    assert "rebalance timeline" in h                     # wc-live timeline section present
    # the two books are presented as tabs (Buy & Hold vs Active Trading).
    assert "Buy &amp; Hold" in h and "Active Trading" in h and "function tab(" in h


def test_build_html_lookup_riskenvelope_and_pertrade():
    ladder = dict(LADDER)
    ladder["win"] = {"Argentina": 0.30, "Spain": 0.18, "Japan": 0.08, "Panama": 0.02}
    h = B.build_html(ladder=ladder, bankroll=1000.0)
    # (1) look up by country: a filter box + JS, and team-tagged rows to filter on.
    assert 'class=find' in h and "function fq" in h
    assert 'data-team="argentina"' in h
    # (2) dive deep: every trade row is click-to-expand with a 'why' (methodology) row.
    assert 'onclick="w(this)"' in h and 'class="why"' in h
    assert "favorite" in h.lower()                       # the per-trade reasoning names the signal
    # (3) per-trade max upside/downside columns.
    assert "Max&nbsp;↑" in h and "Max&nbsp;↓" in h
    # (4) book-level risk envelope on the main page.
    assert "capital at risk" in h and "book max ↑" in h and "book max ↓" in h
    # (5) catchy header: the model's biggest disagreements + the reframed contest.
    assert "biggest disagreements" in h.lower() and 'class="cards"' in h
    assert h.count("<table") == h.count("</table>")


def test_build_html_v4_brand_theme_and_record():
    ladder = dict(LADDER)   # a near-1.0 winner book so it's genuinely two-sided (a BUY and a FADE)
    ladder["win"] = {"Argentina": 0.34, "Spain": 0.22, "Brazil": 0.15,
                     "Japan": 0.12, "Panama": 0.10, "Jordan": 0.09}
    h = B.build_html(ladder=ladder, bankroll=1000.0)
    # brand header + nav anchors + favicon + share meta
    assert "World <span class=vs>vs</span> Model" in h and 'class=top' in h   # rebranded wordmark
    assert 'href="#board"' in h and 'href="#book"' in h and 'href="#record"' in h
    assert 'rel=icon' in h and 'property="og:title"' in h
    # light/dark theme: tokenized CSS + a toggle + a persisted, pre-paint init.
    assert "data-theme" in h and "html[data-theme=light]" in h and "function tg()" in h
    assert "--bg:" in h and "var(--ink)" in h
    # track record strip + countdown + curated cards + mobile scroll wrapper.
    # pre-stamp the scorecard file may be absent ("arming"); post-stamp it's PRE-KICKOFF / hit rate
    assert "Track record" in h and ("PRE-KICKOFF" in h or "hit rate" in h or "arming" in h)
    assert "Kicks off in" in h or "Kicks off today" in h or "underway" in h
    assert "MODEL HIGHER" in h and "MODEL LOWER" in h        # forecasting-forward cards (no BUY/FADE)
    assert "we BUY" not in h and "we FADE" not in h          # trading verbs removed from the headline
    assert "class=scroll" in h


def test_build_html_v5_flags_ranks_links_and_disclaimer():
    ladder = dict(LADDER)
    ladder["win"] = {"Brazil": 0.30, "Spain": 0.20, "Japan": 0.10, "Panama": 0.05}
    ladder["advance"] = {"Brazil": 0.95, "Spain": 0.93, "Japan": 0.55, "Panama": 0.20}
    h = B.build_html(ladder=ladder, bankroll=1000.0)
    # real flag IMAGES (emoji flags don't render on Windows), at a valid flagcdn size.
    assert "flagcdn.com/20x15/br.png" in h and "<img class=flag" in h
    assert 'alt="' in h                                  # emoji kept as the image alt/fallback
    # FIFA rank + World Cup titles + a link to the FIFA source.
    assert "#5" in h and "★5" in h                       # Brazil: rank #5, 5 titles
    assert "inside.fifa.com" in h
    # outbound reference link to the Polymarket market (with a jurisdiction caveat).
    assert "polymarket.com/event/" in h and "restricted in your region" in h
    # strengthened, anti-gambling disclaimer naming Singapore.
    assert "NOT gambling" in h and "Singapore" in h and "no real capital" in h
    # a little football for sharers.
    assert "⚽" in h


def test_build_html_v6_sort_resolve_search():
    ladder = dict(LADDER)
    ladder["win"] = {"Brazil": 0.30, "Spain": 0.20, "Japan": 0.10, "Panama": 0.05}
    ladder["advance"] = {"Brazil": 0.95, "Spain": 0.93, "Japan": 0.55, "Panama": 0.20}
    h = B.build_html(ladder=ladder, bankroll=1000.0)
    # sortable tables: a marker class, clickable headers with column indices, and the sort fn.
    assert "sortable" in h and "data-c=" in h and "function srt(" in h
    # a resolution-date column in the book + the round dates from worldcup_markets.
    assert "Resolves" in h and "Jul 19" in h               # the Win market resolves on the final
    # the football search: a bouncing ball entry + a floating button + a no-match hint.
    assert "class=searchbar" in h and "class=fab" in h and "function focusFind()" in h
    assert 'id=nores' in h
    # Side column is left-aligned now (fixes the cramped 'Team over a blank column' look).
    assert "td.sd" in h and "class=\"sd" in h


def test_build_html_v7_tabs_kick_and_searchscroll():
    h = B.build_html(ladder=LADDER, bankroll=1000.0)
    # two books as tabs, each its own pane, with a switcher.
    assert "id=pane-core" in h and "id=pane-live" in h
    assert "onclick=\"tab('core')\"" in h and "onclick=\"tab('live')\"" in h
    # search collapses the marketing sections and scrolls to results.
    assert "id=recordsec" in h and "id=disagree" in h and "classList.toggle('searching'" in h
    assert "scrollIntoView" in h                          # bring results into view on search
    # the kickable football easter egg: a boot trigger + a kick() animation on the floating ball.
    assert "onclick=\"kick()\"" in h and "function kick(" in h and "@keyframes kick" in h


def test_kickoff_note_counts_down_then_flips():
    import datetime as dt
    assert "10" in B._kickoff_note(dt.date(2026, 6, 1))          # 10 days before
    assert "underway" in B._kickoff_note(dt.date(2026, 6, 20))   # after kickoff


def test_methodology_page_renders_from_markdown():
    h = B.build_methodology_html()
    assert "<!doctype html>" in h and "Methodology" in h
    assert "← Board" in h and "data-theme" in h                    # themed, linked back to board
    assert 'href="glossary.html"' in h                             # cross-links to the glossary
    # the substance the page must highlight.
    assert "What we are trying to do" in h
    assert "bounded" in h.lower() and "favorite" in h.lower()      # why bounded markets / the edge
    assert "What&#x27;s missing" in h or "What's missing" in h or "missing" in h.lower()
    assert "Singapore" in h                                        # the anti-gambling caveat carried over
    assert h.count("<table") == h.count("</table>")                # balanced tables
    assert "**" not in h                                           # no leaked raw markdown bold


def test_glossary_page_renders_with_terms_and_references():
    h = B.build_glossary_html(board_href="index.html")
    assert "<!doctype html>" in h and "Glossary" in h
    assert 'href="index.html"' in h and 'href="methodology.html"' in h    # nav cross-links
    assert "Overround" in h and "Brier score" in h                        # plain-English terms
    assert "Dixon" in h and "Snowberg" in h                               # verified source papers
    assert "@@MATH" not in h and h.count("<table") == h.count("</table>")  # clean render
    assert "**" not in h                                                  # no leaked raw markdown


def test_md_inline_handles_nested_emphasis_and_links():
    assert B._md_inline("**bold *ital* x**") == "<b>bold <i>ital</i> x</b>"
    assert B._md_inline("see `code` here") == "see <code>code</code> here"
    assert '<a href="u" target=_blank' in B._md_inline("[t](u)")


def test_md_list_merges_wrapped_continuation_lines():
    md = "- first line\n  wrapped onto the next line\n- second item\n"
    out = B._md_to_html(md)
    assert "<li>first line wrapped onto the next line</li>" in out
    assert out.count("<li>") == 2 and "<p>" not in out             # not split into a stray paragraph


def test_fundamental_section_renders_with_elo_links_and_caveats():
    import worldcup_fundamental as WF
    import worldcup_live as WL
    ladder = dict(LADDER)
    ladder["win"] = {WL._norm("France"): 0.166, WL._norm("Spain"): 0.155,
                     WL._norm("Brazil"): 0.08, WL._norm("Panama"): 0.004}
    fund = WF.fundamental_ladder(n_sims=1500, seed=0)
    h = B.build_html(ladder=ladder, bankroll=1000.0, fundamental=fund)
    assert "id=fundamental" in h                              # the independent-model section
    assert "eloratings.net" in h and "World_Football_Elo" in h   # Elo source + "what is Elo?" links
    assert "less sharp" in h and "scorecard adjudicates" in h     # the honesty caveat
    assert ("MODEL LOWER" in h or "MODEL HIGHER" in h)       # at least one disagreement card
    # the Elo model is promoted: a board model toggle + its OWN two book tabs (Buy & Hold / Active).
    assert "function setModel(" in h and 'id=mb-elo' in h and "data-elo" in h
    assert "tab('eloc')" in h and "id=pane-eloc" in h          # Elo · Buy & Hold
    assert "tab('elol')" in h and "id=pane-elol" in h          # Elo · Active
    # the reset/clear filter control + its JS.
    assert "function clearFind()" in h and "id=clr" in h
    # without a fundamental ladder, the section + toggle + Elo tabs are absent (data-free callers stay fast).
    h0 = B.build_html(ladder=ladder, bankroll=1000.0)
    assert "id=fundamental" not in h0 and "id=pane-eloc" not in h0 and "id=mb-elo" not in h0


def test_outcome_map_renders_groups_and_knockout_pyramid():
    import worldcup_fundamental as WF
    import worldcup_live as WL
    ladder = dict(LADDER)
    ladder["win"] = {WL._norm("Spain"): 0.18, WL._norm("France"): 0.10}
    fund = WF.fundamental_ladder(n_sims=1500, seed=0)
    pos = WF.group_positions(n_sims=1500, seed=0)
    paths = WF.fundamental_paths(n_sims=1500, seed=0)
    h = B.build_html(ladder=ladder, fundamental=fund, positions=pos, paths=paths)
    assert "id=outcome" in h and "Projected group stage" in h    # the map section
    assert "Group A" in h and "Group L" in h                     # all 12 groups
    # the knockout BRACKET (converging tree of flags/codes to a centre champion), framed as one path
    assert "most-likely bracket" in h and 'class=bracket' in h
    assert 'class=bn' in h and 'class=bchamp' in h and "🏆" in h
    assert 'class=blabels' in h                                  # the R16/QF/SF/Final round labels
    # the distribution-first views from the 20k sim: champion bars + each team's exit-round bar
    assert "Title race" in h and 'class=trace' in h and 'class=tfill' in h
    assert "How far each team goes" in h and 'class=surv' in h and 'class="sv s6"' in h
    assert "Most-likely final" in h                              # the finalist fact callout
    # the bracket still renders (degrades gracefully) when the richer paths aren't supplied.
    assert "most-likely bracket" in B.build_html(ladder=ladder, fundamental=fund, positions=pos)
    # without positions the map is absent (data-free callers stay fast).
    assert "id=outcome" not in B.build_html(ladder=ladder, fundamental=fund)


def test_econ_is_a_bounded_binary_payoff():
    # a binary YES position can never lose more than its stake; max upside is the other leg.
    long_ = B._econ(shares=10.0, entry=0.30)
    assert long_["stake"] == 3.0 and long_["max_down"] == -3.0 and long_["max_up"] == 7.0
    short_ = B._econ(shares=-10.0, entry=0.30)
    assert short_["stake"] == 7.0 and short_["max_down"] == -7.0 and short_["max_up"] == 3.0


def test_faq_page_renders_and_is_linked():
    """The FAQ page renders from markdown, carries the disclaimers, and is cross-linked; the board's
    top nav links to it."""
    h = B.build_faq_html(board_href="index.html")
    assert "<!doctype html>" in h and "FAQ" in h and "data-theme" in h
    assert 'href="index.html"' in h and 'href="methodology.html"' in h and 'href="glossary.html"' in h
    assert "Is this gambling?" in h and "not gambling" in h and "Singapore" in h   # plain-language + caveats
    assert "**" not in h and h.count("<table") == h.count("</table>")              # clean render
    # the substantive how-it-works entries are present.
    assert "How is the simulation done?" in h and "How do you calculate the Elo ratings?" in h
    assert "How do I read the board?" in h and "Which is better" in h
    # the board links to the FAQ in its top nav AND from the About block.
    board = B.build_html(ladder=LADDER, bankroll=1000.0)
    assert 'href="faq.html"' in board and "Common questions (FAQ)" in board
