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

### How do I read the Outcome map?

It is a **distribution, not a prediction**. *Title race* shows each team's chance to win the cup; *how
far each team goes* shows where the simulation has each team bow out; *the field narrows* tracks who
fills each round; and the bracket is just the single most-likely path. Even the favourite usually wins
only about one time in six.

### Why doesn't the fan poll work for me?

The poll talks to a tiny external service. If that request is blocked — most often on a corporate
network or by an ad / tracking blocker — the bubble can't load or record a vote. It generally works on
a normal home or mobile connection.

### How often does it update?

The board is a static page, rebuilt from live data several times a day by a scheduled job, and again
whenever played results are added. The timestamp at the top shows the last build.
