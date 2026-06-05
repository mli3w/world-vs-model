# World vs Model · World Cup 2026

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

The full methodology, with the formulas, lives in
[`docs/methodology-worldcup.md`](docs/methodology-worldcup.md) (rendered on the site's *Methodology*
page). In short: de-vig → favorite–longshot correction (zero-knowledge) and Elo + Poisson +
Monte-Carlo over the bracket (informed), then a conviction-weighted, dollar-neutral *paper* book —
net of a half-spread — purely to put a number on the disagreements.

## Run it locally

```bash
pip install -r requirements.txt
python src/worldcup_board.py --out outputs/index.html   # writes index.html + methodology.html
```

Open `outputs/index.html` in a browser. The board fetches live prices from Polymarket's public Gamma
and CLOB APIs; if they're unreachable it degrades gracefully (no sparklines/liquidity).

```bash
python -m pytest -q     # the model + board test suite
```

## Live updates

The site is a static board redeployed by a scheduled GitHub Action
([`.github/workflows/refresh-board.yml`](.github/workflows/refresh-board.yml)) that rebuilds from live
data and publishes to GitHub Pages. Once the tournament starts, played results are folded in by
committing them to `ledger/wc_results.json` (a list of `{a, b, ga, gb, stage}`); the Elo forecast then
re-forecasts automatically.

## Data source

A single source: **Polymarket** (public Gamma + CLOB APIs). Not affiliated with Polymarket or FIFA.
