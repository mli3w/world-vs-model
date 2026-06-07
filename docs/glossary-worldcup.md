# Glossary & references

Plain-English definitions of the jargon on this site, and the source papers each method comes from.
Everything here is **research & education** — not financial advice, not a tipping service.

## The market

| Term | In plain English |
|---|---|
| **Implied probability** | A price between 0 and 1, read as a chance. A team priced at 0.16 means the market gives it ~16% to win. |
| **Overround / vig** | Add up every team's price in a round and it sums to *more* than the real number of slots — the excess is the bookmaker's built-in margin. |
| **De-vig** | Stripping that margin back out by rescaling a round's prices to sum to its true slot count, so they're comparable to a model. |
| **Favorite–longshot bias** | The long-documented tendency for longshots to be over-priced and favorites under-priced versus their true odds. |
| **Liquidity / depth** | How much money is resting in a market. A thin market can't be traded at size without moving the price. |
| **Half-spread** | Half the gap between the buy and sell price — a rough per-trade cost. We net it off every edge, so a gap that doesn't clear it isn't taken. |
| **Nested ladder** | The five linked markets per team: advance → reach QF → SF → final → win. |
| **No-arbitrage** | If a team's price to reach a *deeper* round exceeds its price to reach a *shallower* one, one of those prices is provably wrong — a riskless inconsistency. |

## The models

| Term | In plain English |
|---|---|
| **Edge** | Model probability minus the de-vigged market probability. Positive = the model thinks it's under-priced. |
| **Zero-knowledge model** | Knows no football — it only re-shapes the market's own prices with a favorite–longshot correction. The honest baseline. |
| **Informed model** | An independent Elo simulation of the bracket, **not** derived from the market — so it can genuinely disagree. |
| **Elo rating** | One number for team strength; the gap between two ratings sets the win probability. From chess, now standard in football. |
| **Expected score** | The win probability the Elo gap implies for a single match. |
| **Poisson goals model** | Treats each team's goals as a random count whose average is set by the rating gap — the standard way to simulate scorelines. |
| **Dixon–Coles correction** | A tweak to the Poisson model that fixes its tendency to under-produce low-score draws (0-0, 1-1). |
| **Shrinkage** | Pulling estimates toward the field average to avoid over-confidence — we flatten ratings for the high-variance knockout. |
| **Rating uncertainty** | We don't know any team's true strength exactly, so each simulation jitters the ratings — which stops the model printing false 0% / 100%. |
| **Host advantage** | The well-documented home-team bump; the three 2026 co-hosts get a disclosed +60 Elo. |
| **Monte Carlo** | Simulating the whole tournament tens of thousands of times and counting how often each outcome happens, to read off a probability. |

## The paper book

| Term | In plain English |
|---|---|
| **Paper book** | A pretend portfolio — no real money — purely to put a number on the model-vs-market disagreements. |
| **Conviction-weighted** | Bigger disagreements get bigger (capped) stakes. |
| **Dollar-neutral** | Equal money long and short, so it's a bet on *relative* mispricing, not on the market rising or falling. |
| **Mark-to-market (MTM)** | Re-pricing open positions at the current market to show running profit/loss. |
| **Capital at risk · max ↑ · max ↓** | The money deployed, and the loose best/worst-case envelope of that book. |
| **Buy & Hold vs Active Trading** | Enter once and hold to the end, versus re-evaluated daily — rebalancing whenever a market settles or a fresh edge clears the cost buffer (any day, not only matchdays). |
| **Cost buffer** | The half-spread gate: a gap that doesn't clear it isn't traded. A *round trip* (close + reopen) costs ~2× it, so a switch must beat that. |
| **Take-profit / Cut / Rotate** | The Active book's exit rules. **Cut** = stop-loss when the model flips against a leg. **Take-profit** = realised for free at settlement (we don't pay a spread to sit in cash). **Rotate** = leave a leg early only for a clearly bigger edge. |
| **Hysteresis** | A dead-band around fair value so a leg that merely wobbles isn't cut-and-reopened repeatedly — it stops the book churning the spread on noise. |
| **Bracket scorecard** | Scores the knockout *projection*: a round-weighted points race (market vs each model) plus a per-round Brier, frozen pre-tournament and tallied as rounds resolve. |

## Scoring & honesty

| Term | In plain English |
|---|---|
| **Out-of-sample** | Scored only on data that arrived *after* the prediction was timestamped. The only honest test. |
| **Brier score** | The average squared error of probability forecasts — lower is better. |
| **Skill (vs market)** | Our Brier minus the market's Brier. Positive means we beat the crowd — the only comparison that matters. |
| **Breadth / information ratio** | More *independent* bets sharpen a strategy (IR ≈ IC·√breadth). Our Elo edges are highly correlated, so the real breadth is small — and we say so. |

## References — where the methods come from

The techniques here are standard; these are the sources.

- **Elo, A. (1978).** *The Rating of Chessplayers, Past and Present.* Arco Publishing. — the rating system.
- **Maher, M. J. (1982).** ["Modelling association football scores."](https://doi.org/10.1111/j.1467-9574.1982.tb00782.x) *Statistica Neerlandica* 36(3): 109–118. — the Poisson goals model for football.
- **Dixon, M. J. & Coles, S. G. (1997).** ["Modelling Association Football Scores and Inefficiencies in the Football Betting Market."](https://doi.org/10.1111/1467-9876.00065) *Journal of the Royal Statistical Society: Series C (Applied Statistics)* 46(2): 265–280. — the low-score (draw) correction we apply.
- **Brier, G. W. (1950).** "Verification of forecasts expressed in terms of probability." *Monthly Weather Review* 78(1): 1–3. — the proper scoring rule we grade ourselves with.
- **Snowberg, E. & Wolfers, J. (2010).** ["Explaining the Favorite–Longshot Bias: Is it Risk-Love or Misperceptions?"](https://www.journals.uchicago.edu/doi/abs/10.1086/655844) *Journal of Political Economy* 118(4): 723–746. — the bias the zero-knowledge model exploits.
- **Ottaviani, M. & Sørensen, P. N. (2008).** "The Favorite-Longshot Bias: An Overview of the Main Explanations." In *Handbook of Sports and Lottery Markets.* — a survey of that bias.
- **Grinold, R. C. (1989).** "The Fundamental Law of Active Management." *Journal of Portfolio Management* 15(3): 30–37. — IR ≈ IC·√breadth, the breadth caveat we flag.
- **[World Football Elo Ratings](https://www.eloratings.net/2026_World_Cup)** (eloratings.net) — the live team ratings the informed model runs on.

The full maths, parameters and code pointers are on the [methodology page](methodology.html).
