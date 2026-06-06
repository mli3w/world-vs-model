# World vs Model · World Cup 2026

### 🔴 Live: **[mli3w.github.io/world-vs-model](https://mli3w.github.io/world-vs-model/)**

**Can a model beat the betting market?** This is a public, research-and-education experiment that
pits two transparent models against the crowd across all ~240 Polymarket World Cup 2026 markets, and
keeps a falsifiable, out-of-sample scorecard.

- **Market (the "world")** — live [Polymarket](https://polymarket.com/sports/world-cup) prices,
  de-vigged so each round sums to its real number of slots (32 advance, 8 QF, 4 SF, 2 final, 1 win).
- **Zero-knowledge model** — knows *no* football: it only re-shapes the market's own prices with a
  favorite–longshot correction. The honest baseline.
- **Informed model (Elo)** — an independent simulation of the verified bracket on real
  [World Football Elo](https://www.eloratings.net/2026_World_Cup) ratings (plus a host bonus, a
  knockout shrink, rating uncertainty and a Dixon–Coles goals model) — **not** derived from the market.

Every disagreement is timestamped and scored **against the market** as results come in. The whole point
is the receipts, not a tip.

> ⚠️ **Research & education only — not financial advice, not a solicitation, and not gambling.** No
> capital is invested and no positions are held; every figure is a paper simulation of market
> *structure*. Prediction-market platforms such as Polymarket are restricted or banned in several
> jurisdictions (e.g. Singapore) — know and follow your local laws. The Polymarket links are
> reference-only.

## How it works

The full methodology with the formulas lives in
[`docs/methodology-worldcup.md`](docs/methodology-worldcup.md) (rendered on the site's *Methodology*
page); a plain-English [*Glossary & references*](docs/glossary-worldcup.md) explains the jargon and
links the source papers. In short: de-vig → favorite–longshot correction (zero-knowledge) and Elo +
Poisson + Monte-Carlo over the bracket (informed).

To put a number on the disagreements there are **four paper books** = 2 models × 2 styles —
**Buy & Hold** (entered once, held) and **Active Trading** (re-evaluated daily; rebalances when a
market settles or a fresh edge clears the cost buffer — any day, not only matchdays) — each
conviction-weighted, dollar-neutral, net of a half-spread, and frozen at day 0 into the ledger so it
shows real running Entry → Now → PnL (no real money; a simulation of structure).

And there is a third voice: a **fan poll** ("Who wins the World Cup 2026?") in the bottom-left bubble
lets visitors add the **crowd** to the picture, plotted on the same *P(wins the cup)* axis as the
model and the market. It is non-binding and not betting; votes are tallied by a tiny, cookieless
[Cloudflare Worker](poll-worker/) (opt-in — the bubble only appears when its endpoint is configured).

## Run it locally

```bash
pip install -r requirements.txt
python src/worldcup_board.py --out outputs/index.html   # writes index.html + methodology.html + glossary.html
```

Open `outputs/index.html` in a browser. The board fetches live prices from Polymarket's public Gamma
and CLOB APIs; if they're unreachable it degrades gracefully (no sparklines/liquidity).

```bash
python -m pytest -q     # the model + board test suite
```

### The track record (pre-registration)

`python src/worldcup_register.py snapshot` stamps **both models' forecasts + the captured market
baseline** for every team into `ledger/predictions.jsonl` (timestamped, falsifiable, scored
out-of-sample by Brier + skill-vs-market) and freezes the four day-0 books. It is **append-only and
immutable** — a stamp is never edited. The board reads the resulting `ledger/scorecard.json` for its
public track-record strip. The daily rebuild marks the frozen stamp to live; it does **not**
re-register.

## Live updates

The site is a static board redeployed by a scheduled GitHub Action
([`.github/workflows/refresh-board.yml`](.github/workflows/refresh-board.yml)) that rebuilds from live
data and publishes to GitHub Pages. Once the tournament starts, played results are folded in by
committing them to `ledger/wc_results.json` (a list of `{a, b, ga, gb, stage}`); the Elo forecast then
re-forecasts automatically.

## Data source

A single source: **Polymarket** (public Gamma + CLOB APIs). Not affiliated with Polymarket or FIFA.
