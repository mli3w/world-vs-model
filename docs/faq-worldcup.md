# FAQ

Plain-English answers to the questions people actually ask about this project. For the maths, see the
[Methodology](methodology.html); for jargon, see the [Glossary](glossary.html). Everything here is
**research & education** — not financial advice, not a tipping service, and not gambling.

## Is this legit?

### Is this gambling?

No. No real money is staked and no positions are ever held. Every figure on the site is a *paper*
simulation of market **structure** — a way to keep score of a forecast, not a wager. There is nothing
to win and nothing to lose.

### Is this financial or betting advice?

No. Nothing here is advice, a solicitation, or a tip. The whole point is a public, falsifiable
scorecard — testing whether transparent models can out-forecast a liquid market — not telling anyone
what to back.

### Is it legal where I am?

The site itself is just public research, so reading it is fine. But prediction-market platforms such
as Polymarket are **restricted or banned in several jurisdictions** (for example, Singapore). The
Polymarket links here are reference-only; know and follow your local laws.

### Are you affiliated with Polymarket or FIFA?

No. This is an independent, solo research experiment. Market data comes from Polymarket's public APIs,
but the project is not affiliated with, or endorsed by, Polymarket or FIFA.

## The contest

### What is the actual question?

Can a transparent, rules-based model beat the betting market? Two models take on the crowd across all
~240 Polymarket World Cup 2026 markets, and every disagreement is scored against the market as results
come in.

### What is the difference between the two models?

The **zero-knowledge** model knows no football — it only re-shapes the market's own prices with a
favorite–longshot correction. It is the honest baseline. The **informed** model is an independent Elo
simulation of the bracket, **not** derived from the market, so it can genuinely disagree with the
crowd. The board lets you switch between them.

### Where do the "market" prices come from?

A single source: Polymarket's public Gamma and CLOB APIs. Each round's prices are **de-vigged**
(rescaled to sum to the real number of slots) so they are comparable, apples-to-apples, with a model.

### Which is better — the zero-knowledge or the informed model?

Nobody knows yet — deciding that *is* the experiment, and they are built to be judged rather than
assumed. There is an important subtlety, though. The zero-knowledge model only re-shapes the market's
own prices, so it can never disagree with the market about *who* goes how far — its bracket is the
market's bracket by construction. It earns its keep purely on **calibration**: are the probabilities
the right *size*? The informed model is the only one that can genuinely disagree on the *ordering*,
because it is built from Elo, independent of the market. So the two are scored on different strengths —
out of sample, by Brier score and skill versus the market — and the live scorecard, not us, decides
which (if either) beats the crowd.

## How it works

### How is the simulation done?

The informed model plays the **entire tournament 20,000 times**. Each run:

1. Plays the group stage as real **scorelines** — expected goals come from the two teams' Elo gap,
   with a Dixon–Coles correction so draws and low scores look like real football, not coin flips.
2. Ranks each group and pours the **top two (plus the eight best third-placed teams)** into the
   **official FIFA 2026 bracket** — the real Round-of-32 slots, not an invented draw.
3. Plays the knockouts **one match at a time** until a champion is crowned.

Across all 20,000 runs we then tally how often each team reaches each round, wins the cup, and meets
each opponent in the final — that is where the Outcome map's distributions come from. Two honest
touches: the knockout rounds use a **flatter** set of ratings (a single match is far more of a
coin-flip than a three-game group), and each run **nudges every team's rating by a random amount** to
reflect that we don't know any team's true strength exactly — so the output is a genuine *spread* of
outcomes, not false precision. The full formulas live on the [Methodology](methodology.html) page.

### How do you calculate the Elo ratings?

We don't invent them. The base numbers are real **World Football Elo ratings**
([eloratings.net](https://www.eloratings.net/2026_World_Cup)), captured at a fixed date, plus a modest
**home-advantage bonus** for the three co-hosts. From a rating gap, the chance team A beats team B is
the standard Elo logistic — a **400-point edge means about 10-to-1 odds**. Once matches are played,
each result updates *both* teams' ratings with a standard, **margin-of-victory-aware** Elo step (a
bigger win, or an upset, moves the numbers more), so the forecast re-forecasts itself as the
tournament unfolds. For the knockout phase we deliberately flatten the ratings toward the field
average, because one-off matches are more random than a round-robin.

### What does the model not account for?

Plenty — and we would rather say so. The informed model is built from team-strength **ratings**, so it
cannot see what the ratings don't already capture: **injuries, suspensions, who actually starts,
motivation, fatigue and travel, the weather**, or a team peaking at just the right moment. It uses the
official bracket, but the *best-third* assignments and the "no same-group rematch in the Round of 32"
rule are handled as a close **approximation**, not the exact draw logic. And because the ratings are
**public**, a model built on them is usually playing catch-up to a sharp market that already prices
most of this in — beating it is *meant* to be hard. The zero-knowledge model is more limited still, by
design: it adds no football knowledge at all, only a correction to the market's own prices. None of
this is hidden — the [Methodology](methodology.html) page has a full "what's missing" section.

### Does the forecast change as games are played?

Yes. As results come in, the model **re-forecasts**: each played match updates both teams' Elo ratings
(so later rounds reflect current form), completed group games are **held fixed** rather than
re-simulated, and only the matches still to come are rolled forward. Crucially, the **pre-tournament
forecast stays frozen** in an append-only ledger — that locked-in prediction is what gets scored, so
the model can't quietly rewrite history to look good. The live board shows the updated view, and the
*as-it-unfolds* strip near the top wakes up once the first games are played, highlighting what moved
and which upsets landed.

## Can I trust the numbers?

### How do you keep score without cherry-picking?

Every forecast is timestamped and **frozen before the tournament** into an append-only ledger — a
stamp is never edited. As results land, each call is scored **out of sample** by its Brier score and
its skill versus the market. The receipts are the point, not any single pick.

### Can the model actually beat the market?

Nobody knows yet — that is the experiment. Liquid markets are very hard to beat, and the honest answer
is settled only by the live scorecard as matches resolve. The project is built to be **falsifiable**:
if the models do not beat the market, the scorecard will say so.

### What are the "paper books"?

A secondary, what-if view that puts a dollar number on the disagreements: a $1,000 *paper* bankroll,
conviction-weighted and dollar-neutral, shown net of trading costs. No real money is involved — it is
a way to *size* the edges, not a portfolio.

## Using the site

### Where do I find the bracket / scorecard / book?

Use the top nav. From left to right: **Scoreboard** (the three contestants), **Disagreements** (where
the zero-knowledge model fades the market most), **🔮 Outcome map** (the model's full distribution
over how far each team goes, with the single most-likely bracket at the bottom), **🏆 Bracket score**
(the round-weighted points race + per-round Brier), **Board** (the dense market-vs-model table),
**Books** (the paper PnL), and **Model** (the informed-model summary). The Outcome map and Bracket
score are top-level sections — no tabs to click through.

### How do I read the board?

Each **row is a team**. The left block is the market's de-vigged price to clear each round — advance
(last 32), reach the quarters, the semis, the final, and win it. The right block is the **win-the-cup**
number three ways: the **market**, your chosen **model**, and the **edge** between them (model minus
market). A **green edge** means the model rates the team *higher* than the market; **red** means lower.
Use the toggle to switch the model column between **zero-knowledge** and **informed**, click any row to
see the reasoning behind it, and click a column header to sort.

### How do I read the Outcome map?

It is a **distribution, not a prediction**. *Title race* shows each team's chance to win the cup; *how
far each team goes* shows where the simulation has each team bow out; *the field narrows* tracks who
fills each round; and the bracket at the bottom is just the single most-likely path. Even the favourite
usually wins only about one time in six. The **Bracket score** section immediately below it is the
*scoring* layer — each side fills the bracket with its own probabilities, and as rounds resolve we
tally a round-weighted points race (Informed model vs Market) alongside a per-round Brier.

### Why doesn't the fan poll work for me?

The poll talks to a tiny external service. If that request is blocked — most often on a corporate
network or by an ad / tracking blocker — the bubble can't load or record a vote. It generally works on
a normal home or mobile connection.

### How often does it update?

The board is a static page, rebuilt from live data several times a day by a scheduled job, and again
whenever played results are added. The timestamp at the top shows the last build.
