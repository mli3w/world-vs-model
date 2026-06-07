# World Cup 2026 — methodology ("World vs Model")

> ⚠️ **A research & education experiment — NOT gambling and NOT an encouragement to gamble.**
> We hold no positions and invest no real capital. Every figure is a *paper* simulation of market
> *structure*, not investment returns, advice, or a solicitation. Prediction-market platforms like
> Polymarket are restricted or banned in some jurisdictions (e.g. Singapore) — know your local laws.

---

## 1. What we are trying to do

**Beat the market at the World Cup using *zero* football knowledge.**

We never forecast a match, a player, or a team. We take the market's *own prices* and ask a
narrower, more honest question: **are those prices internally consistent and unbiased — and if
not, can we harvest the inconsistency?** The entire edge, if any, comes from the *structure* of
the prices, not from knowing anything about football.

Then we **keep score in public**. Because these markets *resolve*, every call is timestamped and
graded out-of-sample against what actually happened. The point isn't to look clever — it's to find
out, on the record, whether a purely structural strategy can beat a liquid crowd.

## 2. Why *bounded* (prediction) markets are interesting for this

A "bounded" market is one that settles to a known value — here, **0 or 1** (a team advances, or it
doesn't). That boundedness is exactly what makes zero-knowledge strategies viable, in four ways an
ordinary stock doesn't offer:

1. **Ground truth arrives.** A stock never tells you its "true value." A prediction market
   *resolves* — so a forecast is **falsifiable** and skill is *measurable*, not just assertable.
   This is what lets us run an honest scorecard instead of a vibe.
2. **Hard mathematical constraints exist for free.** Prices are probabilities. Sub-events nest
   (winning ⊆ reaching the final ⊆ reaching the semi …). Mutually-exclusive outcomes must sum to
   the number of slots. These create **no-arbitrage relationships that need no domain model** —
   pure logic flags a mispricing.
3. **There are well-documented behavioral biases.** The **favorite–longshot bias** (longshots
   systematically overpriced, favorites underpriced) is one of the oldest and most-replicated
   anomalies in betting markets — horse racing, sports, elections, for decades. It's a *shape* in
   the price distribution we can correct without any view on a specific team.
4. **Breadth.** One tournament is *hundreds* of correlated markets (advance / QF / SF / final /
   win, per team). That breadth lets us build a **market-neutral long/short book** instead of a
   single winner pick — and breadth is the cleanest lever there is (Grinold's law: information
   ratio ≈ skill × √breadth).

## 3. The market surface: a nested ladder

**Our single market data source is [Polymarket](https://polymarket.com/sports/world-cup).** We read
its live, real-money World Cup prices through the public Gamma API — no private feeds, no broker. Those
prices are the "world" / market side of every comparison on the board; the crowd's money *is* our
benchmark, and we link straight out to the underlying Polymarket market on every team. (We are not
affiliated with Polymarket, and — see the banner — it is restricted in some jurisdictions; the links
are reference-only.) Because everything keys off one transparent, reproducible price source, there is
no separate "data source" tab to maintain: it is Polymarket, end to end.

Polymarket lists the World Cup as several separately-traded events. Per team they form a **nested
ladder** of "how far do you go," each level with a known number of slots:

| Round | Slots (prices must sum to) |
|---|---|
| Advance to knockouts | 32 |
| Reach quarter-final | 8 |
| Reach semi-final | 4 |
| Reach final | 2 |
| Win the Cup | 1 |

≈240 markets vs 48 winner-only — 5× the breadth, and where the cleanest structural tells live.

## 4. Why we think there's an edge — and why it could work

Three independent structural sources, none of which require football knowledge:

- **Favorite–longshot shape correction (the main edge).** We de-vig each level to its slot count,
  then apply a power-law shape correction `p → pᵖᵒʷᵉʳ` (renormalized). On a planted-bias test this
  beats the de-vigged market by ~0.7% Brier. It's small — but it's *robust* and *directional*: it
  buys favorites and fades longshots, the historically profitable side of the bias. **Why it could
  work:** the bias is behavioral (longshot lottery-love + margin structure) and has persisted for
  decades; we exploit the *distribution shape*, which is far more stable than any single price.
- **No-arbitrage logic (riskless when present).** If a team is priced *higher* to reach the final
  than to reach the semi-final, that's impossible — buy the cheap leg, sell the dear one. The
  nested ladder and the slot-sum constraint give us these checks for free.
- **Breadth + market-neutrality.** We go long the most under-priced and short the most over-priced
  across *all* 240 markets, dollar-neutral. **Why it could work even if we whiff on the champion:**
  the book doesn't need the winner right — it needs the *cross-section* to be mispriced on average.
  A long/short book monetizes relative mispricing, so gross-of-cost alpha can survive being wrong
  on any single market.

We measure all of this **against the market's own price as the baseline** — skill-vs-market, the
only comparison that matters. Beating a coin flip is meaningless; beating the de-vigged crowd is
the whole game.

## 5. Sizing & the four books (2 models × 2 styles)

A fixed **$1,000 paper bankroll** per book, **conviction-weighted** (stake ∝ |edge|, capped per
trade), **dollar-neutral**, net of the half-spread. Each ticket holds *signed* YES-shares:
`unrealized = shares × (price − entry)`, `realized = shares × (outcome − entry)`. Every book is
**frozen at day 0** into the ledger (`ledger/wc_*.jsonl`) and **marked to live**, so each shows real
running Entry → Now → PnL — not a re-sized proposal.

Two **trading styles**, run identically for *both* models so the comparison is symmetric:

- **Buy & Hold** *(`wc-core`)* — entered **once** at day 0, every ticket held to its market's
  resolution. The clean test of *"was the pre-tournament view right?"* PnL settles in waves
  (advance → QF → SF → final → win).
- **Active Trading** *(`wc-live`)* — **re-evaluated daily**, not just on matchdays (the board refreshes
  ~every 3 hours). It trades only on an explicit, cost-gated rule set (`src/wc_active.py`), so the only
  difference from Buy & Hold is *disciplined* action — never churn. With `aligned = (fair − price)·sign`
  the position's still-favourable edge and `buffer` the half-spread:
  - **Hold** while `aligned > buffer` — the gap that justified the trade is still open.
  - **Cut** (stop-loss) when `aligned < −buffer` — the model now thinks the leg loses, so exit early
    rather than realise a bigger loss at settlement. The ±buffer band is **hysteresis**: a leg that
    merely wobbles around fair is *not* cut, so we don't whipsaw the spread.
  - **Take-profit is taken at resolution, not by a paid early exit.** A converged leg (`|aligned| ≤
    buffer`) has ~no edge left; closing it just pays a spread to sit in cash, so we **ride it to its
    free settlement** — and only close it early to **rotate** into a clearly better edge.
  - **Rotate** a held leg for a candidate only when `edge_cand − aligned > 2·cost + buffer` (the swap
    must beat its round trip). Freed capital is redeployed **same-side** (a long replaces a long, a
    short a short), so the book stays dollar-neutral by construction.
  - **Resolution** forces realisation at the {0,1} outcome.

  A **riskless inconsistency** is the cleanest any-day trigger. The test: *"does acting on the model's
  updates beat just holding, net of churn?"* Its changelog is the rebalance timeline.

Crossed with the two **models** that produce the edges — the **zero-knowledge** structural model and
the **informed** Elo model (§5b) — that is four books, each its own tab with its own PnL: *Buy & Hold*,
*Active*, *Elo · Buy & Hold*, *Elo · Active*. Comparing across the grid is itself the finding: if
Active doesn't beat Buy & Hold net of churn the daily updates are noise; if the Elo books don't beat
the zero-knowledge ones, football knowledge didn't help — and we'd report either honestly.

## 5b. The fundamental model (Elo) — an independent second opinion

The structural book above is *derived from* the market, so by construction it can only disagree
with the crowd a little. To get a genuinely **independent** view we run the engine's own
simulation — Elo + Poisson goals over the **verified 2026 bracket** — on **real per-team
[World Football Elo ratings](https://www.eloratings.net/2026_World_Cup)** (eloratings.net, dated,
reproducible), **not** seeded from Polymarket.

Four disclosed choices make it honest (all priors from football, **not** tuned to the market):
- **Real ratings**, swappable and dated — so anyone can reproduce or update them.
- **A host bonus (+60 Elo)** for the three 2026 co-hosts (USA, Canada, Mexico) — home advantage is
  worth roughly this much in recent international football, and without it the model absurdly faded
  the USA to advance *at home*.
- **A knockout-only shrink (×0.6)**: raw match-Elo over-concentrates the favorite when compounded
  through the *knockout* (the top team's title prob balloons to ~30%). A single-elimination bracket
  is far higher-variance than the match-Elo implies, so we flatten the spread *for the knockout
  only*; the group round-robin keeps (near-)raw Elo.
- **Rating uncertainty (±70 Elo per simulation)**: an Elo number is a point estimate of an uncertain
  true strength, so every run jitters each rating. This integrates over that uncertainty, so the
  model stops printing false-precision 0%/100% for minnows and giants. The favorite lands at a
  **plausible ~16%**. (We checked: a group-stage shrink does *not* explain the model's advance-level
  disagreements — those are real.)

**What it finds (live):** a clean *results-vs-reputation* split — the Elo model rates **Spain,
Argentina and the in-form South-Americans (Colombia, Ecuador, Uruguay)** higher than the market,
and fades the **reputation teams (France, England, Portugal, Germany)** whose results have lagged
their squad value. That's a real, defensible disagreement.

**How the Elo model sizes and places its bets.** The Elo book is sized *exactly like* the
structural book — **conviction-weighted and dollar-neutral**: long the markets the model thinks
are under-priced, short the over-priced, each side getting half a fixed **$1,000 paper bankroll**,
stake **∝ |edge|** and **capped per trade** so no single bet dominates. The crucial difference is
where the edge comes from:

- **Edge = Elo-model probability − de-vigged market probability** — both are proper probabilities
  (each round sums to its slots), so the bookmaker's margin doesn't contaminate the edge.
- **Price you'd pay = the raw market price** (with vig), used as the entry/cost and for max ↑/↓.
- It is a **separate paper book** (its own colour — violet — on the board, so you can tell at a
  glance which model the column/tab is showing), scored by the **same out-of-sample scorecard**.

Which of its bets to trust: the **win-level** disagreements (results-vs-reputation) are the
defensible part; the **advance-level** bets are larger but **less reliable** — the market usually
knows a team's specific group context better than a single backward-looking Elo number.

**The honest caveat, stated on the board itself:** a model built on *public* ratings is usually
**less sharp** than a liquid, heavily-traded market — so a big gap is *more likely* the model
being cruder than the crowd being wrong. **Big disagreement ≠ edge.** Both books are scored by the
same live scorecard; that's what adjudicates. (`src/worldcup_fundamental.py`.)

**The most-likely outcome map.** The same 20k simulations also drive a projection on the board: the
**projected group stage** (each team's most-likely finishing rank + advance %, from the group
finishing-position distribution) and a **knockout pyramid** (the most-likely Quarter-finalists →
Semi-finalists → Finalists → Champion, read off the reach-round probabilities). These are the
*model's* probabilities, shown in its violet colour — a picture of what the informed model expects,
not a market consensus.

**Scoring the bracket.** That projection is also kept honest. We register, pre-tournament, every
side's forecast at *each* knockout rung (advance / reach-QF / SF / final / win) and score it two
ways as results land. (1) A round-weighted **points race** — each side fills the bracket with its
top-k teams per rung and a correctly placed team scores that rung's weight (×1 / ×4 / ×8 / ×16 / ×32).
This race is **Informed (Elo) vs Market**: the zero-knowledge model only re-shapes the market's own
prices with a *monotonic* favorite-longshot power, so its *ranking* — and therefore its whole bracket —
is identical to the market's by construction; it cannot disagree about *who* goes how far, so showing
it as a third bracket would just mirror the market. (2) The rigorous companion: **Brier** at every rung
(the same proper score as the books) — and this is where the zero-knowledge model *does* score
separately, because Brier grades probability *magnitudes*, which its power correction changes even when
the ranking doesn't move. One bracket is a single high-variance draw while the Brier averages over all
of them. Both come from the one pre-registered, timestamped ledger
(`src/worldcup_register.py::bracket_scorecard`), so a skeptic can recompute either.

## 6. What's missing, and how we'd improve it (read this part)

We are deliberately loud about the limitations — the credibility is in the caveats.

**What's missing / weak today**
- **Costs & capacity.** Polymarket spreads are wide and depth is thin; the break-even capacity is
  near **\$0** — the spread alone can exceed the gross daily edge. We
  now **net a flat ~1¢ half-spread off every book edge** (sub-spread gaps are sized to zero), so the
  paper books are no longer purely gross. This is still a *flat* approximation — real per-market
  spreads vary and a full slippage/impact model isn't wired in — but it removes the worst of the
  gross-edge illusion.
- **The model's loud "edges" can be its blind spots.** A big model-vs-market gap is frequently the
  *model* missing something the crowd prices, not alpha. We've closed two of the worst: the 2026
  **co-hosts now get a +60 Elo home bump** (the model no longer fades the USA to advance at home),
  and **rating uncertainty (±70 Elo per sim)** stops the false-precision 0%/100% extremes for
  minnows and giants. Advance-level bets are still excluded from the books for the same reason.
- **One tournament = tiny sample.** Single-event variance is enormous; one World Cup *cannot*
  validate a strategy. Confidence is **LOW**; the value is the scorecard accruing over many events.
- **The favorite–longshot knob is illustrative.** The power exponent is a single global constant,
  not fit from data. It *should* be learned from **resolved outcomes** (recalibration) and may
  differ by round and by time-to-resolution.
- **No independent information.** By design we use only the market's own prices. A durable edge vs
  a sharp market may require *some* orthogonal signal; we keep our fundamental Elo/Poisson model
  strictly separate to preserve the zero-knowledge purity, which caps the ceiling.
- **Risk model is crude.** "Dollar-neutral" is not risk-neutral — the nested markets are highly
  correlated, so the book's true risk and the "max ↑/↓" envelope are loose bounds.
- **Breadth is largely an illusion.** The Elo book's edges almost all express *one* view — Elo's
  results-based rating vs the market's reputation pricing (fade France/England/Portugal/Germany, back
  Spain/Colombia/Ecuador/Uruguay). They are highly correlated, so the effective number of independent
  bets is close to **one**, and Grinold's `IR ≈ IC·√K` (which assumes `K` *independent* signals) would
  badly overstate the information ratio. We present the rows as one correlated position, not as breadth.
- **Data completeness & timing.** Partial fetches distort the de-vig; "reach-QF"-type markets
  resolve progressively while we treat them statically; some levels (reach-final) carry huge vig
  (live overrounds run advance ≈ 0%, reach-SF ≈ +17%, reach-final ≈ +30%), so any "edge" on the
  thin middle rungs is the least real. (The Elo forecast itself now **re-forecasts live** — see below.)
- **The displayed bracket is the official 2026 slot table; the probability engine still seeds a
  balanced bracket.** The *Most-likely-outcome* projection pours the model's group standings into
  FIFA's published Round-of-32 slots (`src/wc_bracket.py`: the 16 fixed R32 fixtures + the full
  495-row best-third contingency table), so the matchups you see are the real fixtures, not a guess.
  The Monte-Carlo *probabilities* (win %, reach %) are still computed over a **balanced seeded**
  bracket that avoids same-group R32 rematches — so a team's precise path difficulty in the numbers
  remains an approximation, even though the rendered path is now exact.
- **The goals model has no team-specific attack/defence.** It is a Dixon–Coles-corrected Poisson
  (a realistic ~27% draw rate), but scoring rates come only from the Elo gap — not from a team's
  actual goals-for/against, so a heavy-scoring or defensive side isn't individually captured.
- **The Elo model's advance-level edges are real but unreliable.** They are *not* a shrink
  artifact (we verified a group shrink barely moves them) — raw Elo genuinely rates some teams
  high *within their group* (e.g. Panama's Elo is 2nd in Group L), while the market strongly
  disagrees. Those are legitimate model disagreements, but the market is usually the sharper one
  there, so the **win-level** disagreements (results-vs-reputation) are the more defensible story.
- **The Active book's rotation rule is a deliberately simple baseline.** It has hysteresis (no
  whipsaw), a stop-loss, ride-to-resolution take-profit, and dollar-neutral redeploy — but it (a)
  trusts the model's *own* fair value to decide convergence (circular if the model is
  mis-calibrated), (b) ignores **time-to-resolution** (an edge is more trustworthy as τ→0, and a
  small far-dated edge is mostly cost-drag), (c) has **no correlation guard** (rotating
  "Spain-to-win" into "Spain-to-final" isn't diversification), and (d) assumes you can exit at the
  marked price (thin depth says otherwise). We keep it simple on purpose: given the spreads, the
  honest expectation is that a disciplined Active book trades *rarely* and may **lose** to Buy &
  Hold net of costs — publishing that cleanly is the point, not winning, so we resist false
  precision. τ-weighting, a calibration-discounted edge, and a correlation gate are the natural
  next steps if the realized ledger says churn is paying.

**How we'd improve it**
- **Fit the bias from settled outcomes** per round (recalibrate the de-vig power from the realized
  ledger as markets resolve), and
  **weight by time-to-resolution** (IC rises as τ→0).
- **Per-market, dynamic costs** — we now net a *flat* half-spread; next is real per-market spread +
  depth/impact and capacity gating, so sizing respects each market's true liquidity.
- **Live re-forecasting is wired** — played results Elo-update the ratings and completed group
  games are held fixed, so the Elo forecast moves with the tournament (it reads
  `ledger/wc_results.json`; pre-tournament, with no results, it is the day-0 forecast). The
  **Dixon–Coles** goals correction is also in. The **displayed** projection now uses the **exact
  official slot table** (incl. best-third contingencies, `src/wc_bracket.py`); the remaining gap is
  to drive the Monte-Carlo *probabilities* through those same official slots (today they run over a
  balanced seeded bracket).
- **Stack more decorrelated zero-knowledge signals** (calibration, no-arb, round-clustering) to
  lift breadth (IR ≈ IC·√K).
- **Covariance-aware risk** (RMT-denoised or hierarchical risk parity) instead of naive dollar-
  neutral, so sizing respects the nested correlations.
- **The independent fundamental model is now built** (`src/worldcup_fundamental.py`, §5b) — shown
  as a separate, clearly-labelled section so readers see structure-only vs Elo side by side. The
  shrink is now **knockout-only** (the group stage trusts raw Elo). Next for it: real form/injury
  adjustments to the ratings (so its advance-level disagreements are better-founded).

## 7. Honesty guardrails

- **Confidence is LOW for any single tournament.** Small, unproven edges; huge single-event
  variance; ~zero realistic capacity. The deliverable is a falsifiable record, not a return.
- **Skill is scored vs the market**, with the market price captured as the baseline.
- **No domain knowledge is injected anywhere.** A team-specific judgement would be a bug.

## The math — formulas & techniques

A compact, reproducible reference. Prices are probabilities \(p \in (0,1)\); each round has \(S\)
slots (advance 32, QF 8, SF 4, final 2, win 1). Everything is plain arithmetic over a handful of
**disclosed priors** — none fit to the market: the favorite–longshot \(\alpha\), the Elo shrinks
\(\kappa\), the host bonus, the rating-uncertainty \(\sigma\), the Dixon–Coles \(\rho\), and the cost
half-spread \(c\).

**De-vig & overround.** Raw prices sum to more than the slots (the bookmaker's margin); we rescale
each level proportionally to its slot count:

$$q_i = \frac{p_i}{\sum_j p_j}\,S, \qquad \text{overround} = \frac{\sum_j p_j}{S} - 1 .$$

**Zero-knowledge model — favorite–longshot correction.** A power transform of the shape,
renormalised back to the slots, with \(\alpha = 1.15\):

$$\text{model}_i = \frac{p_i^{\alpha}}{\sum_j p_j^{\alpha}}\,S, \qquad
  \text{edge}_i = \text{model}_i - q_i .$$

\(\alpha > 1\) lifts favorites and trims longshots — the historically profitable direction of the bias.

**No-arbitrage (nested).** For each team the deeper rounds can't exceed the shallower ones:

$$P(\text{win}) \le P(\text{final}) \le P(\text{SF}) \le P(\text{QF}) \le P(\text{advance}) .$$

Any \(P(\text{deeper}) > P(\text{shallower}) + \text{tol}\) is a riskless mispricing.

**Cost (half-spread) netting.** Every edge shown in a *book* is net of a flat half-spread
\(c = 0.01\) (≈ 1 cent, a typical Polymarket tick):

$$\text{edge}_{\text{net}} = \operatorname{sign}(\text{edge})\cdot\max\!\big(|\text{edge}| - c,\ 0\big).$$

A gap that doesn't clear the cost to trade it is sized to zero — we only act on edges that survive the
spread. (The model-vs-market *comparison* table still shows the gross disagreement; netting applies
where money is at stake.)

**Sizing — the paper book.** Conviction-weighted and dollar-neutral, on the **net** edge. Each side
(long/short) gets half a bankroll \(B\), allocated by \(|\text{edge}|\) and capped per trade:

$$\text{stake}_i = \min\!\left(\frac{B}{2}\cdot\frac{|\text{edge}_i|}{\sum_j|\text{edge}_j|},\ \ \text{cap}\right),
  \quad \text{cap} = \tfrac{B}{2}\cdot 0.15 ,$$

$$\text{shares}_i = \pm\,\frac{\text{stake}_i}{\max(\kappa_i,\ \varepsilon)},
  \quad \kappa_i = p_i\ (\text{long})\ \text{ or }\ 1-p_i\ (\text{short}).$$

Mark-to-market \(\text{PnL} = \text{shares}\cdot(\text{price}_{\text{now}} - \text{entry})\); realised uses
the settled outcome \(o \in \{0,1\}\). A binary bet can't lose more than its stake:
\(\max\!\downarrow = -\,\text{stake}\), \(\max\!\uparrow = |\text{shares}| - \text{stake}\).

**The informed (Elo) model.** Match win probability (Elo expected score), with a home bonus \(h\),
and the rating update from a result (\(S \in \{1,\tfrac12,0\}\), \(K = 24\)):

$$E = \frac{1}{1 + 10^{-(R_A - R_B + h)/400}}, \qquad
  R \leftarrow R + K\,\ln\!\big(|\Delta\text{goals}| + 1\big)\,(S - E).$$

Group-stage scoreline — a **Dixon–Coles**-corrected double Poisson (the \(\rho\) term lifts the
low-score draws that independent Poisson under-produces, giving a realistic \(\sim 27\%\) draw rate):

$$g_A \sim \text{Poisson}(\lambda_A),\quad
  \lambda_A = \mu\,e^{+b(R_A - R_B + h)},\quad
  \lambda_B = \mu\,e^{-b(R_A - R_B + h)},$$

with \(\mu = 1.35\), \(b = 0.0028\), \(\rho = -0.05\); the DC factor \(\tau_\rho\) reweights the
\((0\text{-}0,\ 1\text{-}0,\ 0\text{-}1,\ 1\text{-}1)\) cells.

Disclosed priors on the ratings: a **host bonus** of \(+60\) Elo for the three 2026 co-hosts (added
before the shrink), and a **knockout-only shrink** toward the field mean \(\bar{R}\):

$$R' = \bar{R} + \kappa\,(R - \bar{R}), \qquad \kappa_{\text{group}} = 1.0,\quad \kappa_{\text{KO}} = 0.6.$$

**Rating uncertainty.** Each of the \(N\) simulations perturbs every team's rating by
\(\varepsilon \sim \mathcal{N}(0,\sigma^2)\), \(\sigma = 70\) Elo (the same \(\varepsilon\) for a team's
group and knockout ratings), integrating over our uncertainty about true strength — so a favorite
reads \(\sim 99\%\), not a false 100%, to advance.

**Bracket.** The *Monte-Carlo* qualifiers are seeded into a balanced bracket (winners take the protected
top seeds, then runners-up, then best-thirds, by rating within each tier), so winners are kept apart and
same-group teams don't meet in the Round of 32 — a structural approximation for the *probabilities*. The
*Most-likely-outcome* projection shown on the board is separate and **exact**: it pours the model's group
standings into FIFA's official Round-of-32 slot table and the full 495-row best-third contingency
(`src/wc_bracket.py`), so the rendered fixtures are the real ones.

**Monte-Carlo reach probabilities.** Over \(N = 20{,}000\) sims, \(P(\text{level}) = \text{count}/N\). The
**Monte-Carlo** error — how precisely the sim estimates its *own* answer — is

$$\mathrm{SE} \approx \sqrt{\frac{p(1-p)}{N}} \approx 0.2\text{–}0.3\%.$$

That is **not** the forecast's error bar: the real uncertainty is dominated by the *inputs* (the Elo
ratings, the host bonus, the bracket path, and everything the model can't see — form, injuries,
motivation), which is far larger. So a big model-vs-market gap is **not** "signal because it clears the
MC noise"; treat it as a disagreement the scorecard adjudicates, not a proven edge. The
rating-uncertainty band is a first, partial attempt to reflect this.

**Scoring (the public scorecard).** Out-of-sample, always vs the market — lower Brier is better,
positive skill means the model beat the crowd:

$$\text{Brier} = \frac{1}{n}\sum_i (p_i - o_i)^2, \qquad
  \text{skill} = \text{Brier}_{\text{market}} - \text{Brier}_{\text{model}} .$$

## Where this lives in code

| Piece | Module |
|---|---|
| De-vig / favorite–longshot / no-arb detectors | `src/consistency.py` |
| Full nested ladder + per-level overround + arb scan | `src/worldcup_markets.py` |
| Informed Elo model (Elo + Poisson + Dixon–Coles Monte Carlo) | `src/worldcup_fundamental.py`, `src/worldcup_sim.py` |
| Official FIFA 2026 knockout slot table + projected bracket | `src/wc_bracket.py` |
| Paper positions, mark-to-live, resolve PnL | `src/worldcup_positions.py` |
| Active book rotation rules (sell / take-profit / cut / switch, cost-gated) | `src/wc_active.py` |
| Conviction-weighted sizing + the four books + the HTML board | `src/worldcup_board.py` |
| Pre-registered predictions, frozen books, scorecard + the **bracket scorecard** | `src/worldcup_register.py`, `ledger/` |
| Record a played result → live re-forecast | `src/feed_result.py` |
