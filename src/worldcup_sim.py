"""
worldcup_sim — a 538-style tournament Monte Carlo
==============================================================================
The FUNDAMENTAL counterpart to the market-structure engine. Team ratings (Elo) +
a Poisson goals match model + the group/knockout bracket, simulated many times to
produce MODEL-implied probabilities (title, advancement) and a realistic substitution
structure (title outcomes are anti-correlated because only one team can win).

Two uses, kept strictly modular (never let the model leak into a market estimator):
  1) Ground truth — we KNOW the structure a simulation produces, so it validates the
     market relationship detector against a realistic bracket (richer than the
     softmax-simplex synthetic in relationships.py).
  2) Dislocation — compare model-implied title probs to the MARKET (Polymarket
     world-cup-winner). Where they disagree is a candidate mispricing.

Rigor (Prime Directive 1): the bracket logic is separated from the goals model so each
has clean ground truth. Knockout win prob = the Elo expected score, so a k-round
single-elimination gives an ANALYTIC title prob = p**k that the Monte Carlo must recover.
The goals model is validated for realism (avg goals, draw rate, rating->points monotonicity).
"""
import numpy as np

# ----------------------------------------------------------------------
# 1. ELO  (rating -> match probability, and result -> rating update)
# ----------------------------------------------------------------------
def expected_score(ra, rb, home=0.0):
    """Elo expected score of A vs B (1=certain win). `home` is a rating bonus for A."""
    return 1.0 / (1.0 + 10.0 ** (-(ra - rb + home) / 400.0))


def elo_update(ra, rb, ga, gb, k=24.0):
    """538-style zero-sum Elo update from a match score (ga:gb). Margin of victory
    inflates the swing (ln of goal diff); the update is conserved (A gains what B loses).
    Returns (new_ra, new_rb)."""
    sa = 1.0 if ga > gb else (0.5 if ga == gb else 0.0)
    ea = expected_score(ra, rb)
    mov = np.log(abs(ga - gb) + 1.0)                    # 1 for a 1-goal/draw, grows with margin
    delta = k * mov * (sa - ea)
    return ra + delta, rb - delta


# ----------------------------------------------------------------------
# 2. GOALS MODEL  (group stage: realistic scorelines + standings)
# ----------------------------------------------------------------------
DC_RHO = -0.05   # Dixon-Coles low-score dependence: real football scores aren't independent Poisson
                 # (too few draws). rho<0 lifts 0-0 and 1-1 and trims 1-0/0-1 -> a realistic draw rate.


def _dc_tau(ga, gb, la, lb, rho):
    """Dixon-Coles correction factor for the four low-score cells (1 elsewhere)."""
    if ga == 0 and gb == 0:
        return 1.0 - la * lb * rho
    if ga == 0 and gb == 1:
        return 1.0 + la * rho
    if ga == 1 and gb == 0:
        return 1.0 + lb * rho
    if ga == 1 and gb == 1:
        return 1.0 - rho
    return 1.0


def match_goals(ra, rb, rng, home=0.0, mu=1.35, b=0.0028, rho=DC_RHO):
    """Dixon-Coles-corrected Poisson scoreline. Expected goals are split by rating diff so the
    stronger side scores more; `mu` sets the even-match per-side mean (~1.35 => ~2.7 total). The
    `rho` low-score dependence corrects independent Poisson's draw deficit. Returns integer (ga, gb).
    Sampled by accept-reject on the joint Poisson * tau (a few % of draws are re-rolled)."""
    d = (ra - rb + home)
    la = mu * np.exp(b * d)
    lb = mu * np.exp(-b * d)
    if not rho:
        return int(rng.poisson(la)), int(rng.poisson(lb))
    tmax = max(1.0 - la * lb * rho, 1.0 - rho, 1.0 + la * rho, 1.0 + lb * rho, 1.0)
    while True:                                          # accept-reject: exact DC joint distribution
        ga, gb = int(rng.poisson(la)), int(rng.poisson(lb))
        if rng.random() < _dc_tau(ga, gb, la, lb, rho) / tmax:
            return ga, gb


# ----------------------------------------------------------------------
# 3. GROUP STAGE
# ----------------------------------------------------------------------
def round_robin(teams):
    """All unordered pairs (each team plays each other once)."""
    return [(a, b) for i, a in enumerate(teams) for b in teams[i + 1:]]


def group_standings(teams, ratings, rng, home_for=None, home=80.0, known=None):
    """Simulate a round-robin and return a rank table sorted by (points, GD, GF).

    Returns list of dict rows in finishing order. `home_for` set = host bonus for that team.
    `known` = {frozenset({a,b}): {a: ga, b: gb}} uses ACTUAL played scores instead of
    simulating those matches — this is what makes the forecast update as results come in.
    """
    rec = {t: dict(team=t, P=0, W=0, D=0, L=0, GF=0, GA=0, Pts=0) for t in teams}
    for a, b in round_robin(teams):
        key = frozenset((a, b))
        if known and key in known:
            ga, gb = known[key][a], known[key][b]
        else:
            ha = home if home_for == a else 0.0
            hb = home if home_for == b else 0.0
            ga, gb = match_goals(ratings[a], ratings[b], rng, home=ha - hb)
        for t, gf, ga_ in ((a, ga, gb), (b, gb, ga)):
            r = rec[t]; r["P"] += 1; r["GF"] += gf; r["GA"] += ga_
        if ga > gb:
            rec[a]["W"] += 1; rec[a]["Pts"] += 3; rec[b]["L"] += 1
        elif ga < gb:
            rec[b]["W"] += 1; rec[b]["Pts"] += 3; rec[a]["L"] += 1
        else:
            rec[a]["D"] += 1; rec[b]["D"] += 1; rec[a]["Pts"] += 1; rec[b]["Pts"] += 1
    rows = list(rec.values())
    for r in rows:
        r["GD"] = r["GF"] - r["GA"]
    # tiebreak: points, goal difference, goals for, then a coin flip (random key)
    rng.shuffle(rows)
    rows.sort(key=lambda r: (r["Pts"], r["GD"], r["GF"]), reverse=True)
    return rows


# ----------------------------------------------------------------------
# 4. KNOCKOUT  (win prob = Elo expected score -> analytic title = p**rounds)
# ----------------------------------------------------------------------
def knockout_run(seeds, ratings, rng, home_for=None, home=80.0):
    """Single-elimination over a power-of-two seed list. Returns (champion, wins) where
    wins[team] = number of knockout matches that team won — i.e. how deep it went. A tie is
    impossible (penalty shootouts fold into the Elo win probability)."""
    alive = list(seeds)
    wins = {t: 0 for t in seeds}
    while len(alive) > 1:
        nxt = []
        for i in range(0, len(alive), 2):
            a, b = alive[i], alive[i + 1]
            ha = (home if home_for == a else 0.0) - (home if home_for == b else 0.0)
            w = a if rng.random() < expected_score(ratings[a], ratings[b], home=ha) else b
            wins[w] += 1
            nxt.append(w)
        alive = nxt
    return alive[0], wins


def knockout_champion(seeds, ratings, rng, home_for=None, home=80.0):
    """The champion of a single-elimination bracket (thin wrapper over knockout_run)."""
    return knockout_run(seeds, ratings, rng, home_for=home_for, home=home)[0]


# ----------------------------------------------------------------------
# 5. FULL TOURNAMENT + MONTE CARLO
# ----------------------------------------------------------------------
def _seed_order(n):
    """Standard bracket seeding for a power-of-two `n`: returns 1-based seed numbers in
    first-round seat order, so seeds 1 and 2 can meet only in the final, 1 plays the lowest
    seed, and stronger seeds are spread across the halves (e.g. n=8 -> [1,8,4,5,2,7,3,6])."""
    order = [1]
    while len(order) < n:
        m = len(order) * 2
        order = [x for p in order for x in (p, m + 1 - p)]
    return order


def _avoid_group_rematch(seeds, groups):
    """Light single-pass nudge: if a first-round pair is two teams from the SAME group (a group
    winner drawn against its own runner-up), swap one with an adjacent pair's partner when that
    clears the clash. An approximation of the real draw's 'no same-group rematch in R32' rule."""
    gof = {t: g for g, ts in groups.items() for t in ts}
    s = list(seeds)
    for i in range(0, len(s), 2):
        if gof.get(s[i]) == gof.get(s[i + 1]):
            j = (i + 2) % len(s)
            if gof.get(s[i]) != gof.get(s[j + 1]) and gof.get(s[j]) != gof.get(s[i + 1]):
                s[i + 1], s[j + 1] = s[j + 1], s[i + 1]
    return s


def _group_seeds(groups, ratings, rng, qualify=2, n_best_third=0, home_for=None, known=None):
    """Run the group stage and return (seeds, qualifiers) in first-round bracket order. Qualifiers
    are seeded into a BALANCED bracket: group winners take the top (protected) seeds, then runners-
    up, then best-thirds, ranked by rating within each tier — so winners get the easier early path
    and are kept apart until late (no winner-vs-winner in the Round of 32). A same-group R32 rematch
    is nudged apart. This approximates the real draw's structure; it is NOT the exact official slot
    table (the best-third placement contingencies are not modelled). Field must be a power of two."""
    winners, runners, third_rows = [], [], []
    for g, teams in groups.items():
        table = group_standings(teams, ratings, rng, home_for=home_for, known=known)
        winners.append(table[0]["team"])
        if qualify >= 2:
            runners.append(table[1]["team"])
        if len(table) > 2:
            third_rows.append(table[2])
    third_rows.sort(key=lambda r: (r["Pts"], r["GD"], r["GF"]), reverse=True)
    thirds = [r["team"] for r in third_rows[:n_best_third]]
    quals = set(winners) | set(runners) | set(thirds)
    if len(quals) & (len(quals) - 1) != 0:
        raise ValueError(f"knockout needs a power-of-two field, got {len(quals)} "
                         f"(adjust qualify / n_best_third)")
    tier = {t: 0 for t in winners}
    tier.update({t: 1 for t in runners})
    tier.update({t: 2 for t in thirds})
    ranked = sorted(quals, key=lambda t: (tier[t], -ratings[t]))    # seed 1 = strongest winner
    seats = _seed_order(len(ranked))                               # seat -> seed number (1-based)
    seeds = _avoid_group_rematch([ranked[s - 1] for s in seats], groups)
    return seeds, quals


def simulate_tournament(groups, ratings, rng, qualify=2, n_best_third=0,
                        home_for=None, known=None):
    """One full run: group stage -> seeded knockout -> champion. `groups` is an
    ordered dict {group_name: [teams]}. Top `qualify` per group advance, plus the
    `n_best_third` best third-placed teams across groups (the real 2026 format is
    qualify=2, n_best_third=8 -> a 32-team Round of 32). `known` passes actual group
    scores through so only UNPLAYED matches are randomized.
    Returns (champion, qualifiers set)."""
    seeds, quals = _group_seeds(groups, ratings, rng, qualify, n_best_third, home_for, known)
    return knockout_champion(seeds, ratings, rng, home_for=home_for), quals


def monte_carlo_ladder(groups, ratings, n_sims=20000, seed=0, qualify=2, n_best_third=0,
                       home_for=None, known=None, ko_ratings=None, rating_sd=0.0):
    """Per-team probability of reaching EACH ladder level (advance / reach_QF / reach_SF /
    reach_F / win), by tallying how deep each team gets across n_sims runs. Returns
    {level: {team: prob}}. The reach thresholds are derived from the bracket size, so the
    nested ordering advance >= reach_QF >= reach_SF >= reach_F >= win holds by construction.

    `ko_ratings` (default = `ratings`) lets the KNOCKOUT phase use different ratings from the
    group stage — e.g. a flatter (more-shrunk) set, since single-elimination is higher-variance
    than the Elo match probability implies, while a 3-game round-robin is closer to true strength.

    `rating_sd` > 0 adds PARAMETER (rating) uncertainty: each simulation perturbs every team's
    rating by N(0, rating_sd) — the SAME draw applied to its group and knockout ratings so the
    perturbation is consistent within a run. This integrates over our uncertainty about each
    team's true strength, so the output reflects FORECAST uncertainty, not just the bracket coin-
    flips (without it the favorite reads ~100% to advance and minnows ~0%, falsely precise)."""
    rng = np.random.default_rng(seed)
    ko = ko_ratings if ko_ratings is not None else ratings
    teams = [t for ts in groups.values() for t in ts]
    levels = ("advance", "reach_R16", "reach_QF", "reach_SF", "reach_F", "win")
    cnt = {lv: {t: 0 for t in teams} for lv in levels}
    for _ in range(n_sims):
        if rating_sd:
            eps = {t: rng.normal(0.0, rating_sd) for t in teams}
            r_g = {t: ratings[t] + eps[t] for t in teams}
            r_k = {t: ko[t] + eps[t] for t in teams}
        else:
            r_g, r_k = ratings, ko
        seeds, quals = _group_seeds(groups, r_g, rng, qualify, n_best_third, home_for, known)
        champ, wins = knockout_run(seeds, r_k, rng, home_for=home_for)
        rounds = len(seeds).bit_length() - 1                 # 5 for a 32-team bracket
        for t in quals:
            cnt["advance"][t] += 1
        for t, w in wins.items():
            if w >= rounds - 4: cnt["reach_R16"][t] += 1      # last 16
            if w >= rounds - 3: cnt["reach_QF"][t] += 1       # last 8
            if w >= rounds - 2: cnt["reach_SF"][t] += 1       # last 4
            if w >= rounds - 1: cnt["reach_F"][t] += 1        # last 2
        cnt["win"][champ] += 1
    return {lv: {t: cnt[lv][t] / n_sims for t in teams} for lv in levels}


def monte_carlo_paths(groups, ratings, n_sims=20000, seed=0, qualify=2, n_best_third=0,
                      home_for=None, known=None, ko_ratings=None, rating_sd=0.0, top_finals=8):
    """Richer Monte-Carlo that keeps the JOINT outcomes the marginal ladder throws away. Same
    ratings / uncertainty knobs as monte_carlo_ladder. Returns a dict:
      depth     : {team: [p_group, p_R32, p_R16, p_QF, p_SF, p_runnerup, p_champ]} — the team's
                  EXIT-round distribution (where it bows out), summing to 1. The natural input for
                  a 'how far does each team go' survival bar.
      champions : {team: P(win the cup)} (the champion distribution).
      finals    : [(a, b, prob), ...] the `top_finals` most-likely FINAL pairings (names sorted),
                  i.e. how often each specific final actually occurs across the runs.
    Buckets are sized from the bracket: group + one per knockout round + champion."""
    import collections
    rng = np.random.default_rng(seed)
    ko = ko_ratings if ko_ratings is not None else ratings
    teams = [t for ts in groups.values() for t in ts]
    n_qual = qualify * len(groups) + n_best_third            # 2026: 2*12 + 8 = 32
    rounds = max(n_qual, 1).bit_length() - 1                 # 5 knockout rounds for a 32-team draw
    nb = rounds + 2                                          # group + R32..champ
    depth = {t: [0] * nb for t in teams}
    champ_cnt = {t: 0 for t in teams}
    finals_cnt = collections.Counter()
    for _ in range(n_sims):
        if rating_sd:
            eps = {t: rng.normal(0.0, rating_sd) for t in teams}
            r_g = {t: ratings[t] + eps[t] for t in teams}
            r_k = {t: ko[t] + eps[t] for t in teams}
        else:
            r_g, r_k = ratings, ko
        seeds, quals = _group_seeds(groups, r_g, rng, qualify, n_best_third, home_for, known)
        champ, wins = knockout_run(seeds, r_k, rng, home_for=home_for)
        qset = set(quals)
        for t in teams:
            depth[t][0 if t not in qset else min(wins.get(t, 0), rounds) + 1] += 1
        champ_cnt[champ] += 1
        runner = next((t for t, w in wins.items() if w == rounds - 1), None)   # the losing finalist
        if runner is not None:
            finals_cnt[tuple(sorted((champ, runner)))] += 1
    return dict(
        depth={t: [c / n_sims for c in depth[t]] for t in teams},
        champions={t: champ_cnt[t] / n_sims for t in teams},
        finals=[(a, b, c / n_sims) for (a, b), c in finals_cnt.most_common(top_finals)],
    )


def monte_carlo_positions(groups, ratings, n_sims=20000, seed=0, home_for=None, known=None,
                          rating_sd=0.0):
    """Per-team probability of FINISHING 1st / 2nd / 3rd / 4th in its group, by tallying the
    group-stage finishing index across n_sims runs. Returns {team: [p1, p2, p3, p4]} (the list
    length is the group size). Group-stage only — far cheaper than a full tournament run.
    `rating_sd` > 0 adds per-sim rating uncertainty (see monte_carlo_ladder)."""
    rng = np.random.default_rng(seed)
    gsize = {t: len(ts) for ts in groups.values() for t in ts}
    pos = {t: [0] * gsize[t] for t in gsize}
    for _ in range(n_sims):
        rr = ({t: ratings[t] + rng.normal(0.0, rating_sd) for t in ratings}
              if rating_sd else ratings)
        for g, teams in groups.items():
            table = group_standings(teams, rr, rng, home_for=home_for, known=known)
            for i, row in enumerate(table):
                pos[row["team"]][i] += 1
    return {t: [c / n_sims for c in pos[t]] for t in pos}


def monte_carlo(groups, ratings, n_sims=20000, seed=0, **kw):
    """Run the tournament n_sims times -> per-team title prob + advancement prob,
    each with a Monte-Carlo standard error. Returns dict keyed by team."""
    rng = np.random.default_rng(seed)
    teams = [t for ts in groups.values() for t in ts]
    title = {t: 0 for t in teams}
    adv = {t: 0 for t in teams}
    for _ in range(n_sims):
        champ, quals = simulate_tournament(groups, ratings, rng, **kw)
        title[champ] += 1
        for t in quals:
            adv[t] += 1
    out = {}
    for t in teams:
        p = title[t] / n_sims
        out[t] = dict(title=p, title_se=np.sqrt(max(p * (1 - p), 1e-12) / n_sims),
                      advance=adv[t] / n_sims)
    return out


# ----------------------------------------------------------------------
# 6. LIVE STATE — ingest scores, update ratings, rank tables, re-forecast
# ----------------------------------------------------------------------
def _tally(teams, played):
    """Build a rank table from a list of played (a, b, ga, gb) results only."""
    rec = {t: dict(team=t, P=0, W=0, D=0, L=0, GF=0, GA=0, Pts=0) for t in teams}
    for a, b, ga, gb in played:
        for t, gf, ag in ((a, ga, gb), (b, gb, ga)):
            r = rec[t]; r["P"] += 1; r["GF"] += gf; r["GA"] += ag
        if ga > gb:
            rec[a]["W"] += 1; rec[a]["Pts"] += 3; rec[b]["L"] += 1
        elif ga < gb:
            rec[b]["W"] += 1; rec[b]["Pts"] += 3; rec[a]["L"] += 1
        else:
            rec[a]["D"] += 1; rec[b]["D"] += 1; rec[a]["Pts"] += 1; rec[b]["Pts"] += 1
    rows = list(rec.values())
    for r in rows:
        r["GD"] = r["GF"] - r["GA"]
    rows.sort(key=lambda r: (r["Pts"], r["GD"], r["GF"], r["team"]), reverse=True)
    return rows


class Tournament:
    """Live tournament state. Feed match scores as they happen; ratings update (Elo),
    rank tables reflect played matches, and forecast() re-simulates only the UNPLAYED
    matches — so model-implied probabilities update as the tournament progresses."""

    def __init__(self, groups, ratings, home_for=None, k_elo=24.0):
        self.groups = {g: list(ts) for g, ts in groups.items()}
        self.ratings = dict(ratings)                    # live ratings (updated by results)
        self.home_for = home_for
        self.k = k_elo
        self.known = {}                                 # frozenset({a,b}) -> {a:ga, b:gb}
        self.group_of = {t: g for g, ts in self.groups.items() for t in ts}

    def play(self, a, b, ga, gb):
        """Record a played group match: store the score and update both Elo ratings."""
        self.known[frozenset((a, b))] = {a: ga, b: gb}
        self.ratings[a], self.ratings[b] = elo_update(
            self.ratings[a], self.ratings[b], ga, gb, self.k)

    def rank_table(self, group):
        """Current standings of one group from PLAYED matches only."""
        teams = self.groups[group]
        played = [(a, b, self.known[frozenset((a, b))][a], self.known[frozenset((a, b))][b])
                  for a, b in round_robin(teams) if frozenset((a, b)) in self.known]
        return _tally(teams, played)

    def forecast(self, n_sims=20000, seed=0, qualify=2, n_best_third=0):
        """Model-implied title/advancement probabilities given results so far."""
        return monte_carlo(self.groups, self.ratings, n_sims, seed=seed,
                           known=self.known, home_for=self.home_for,
                           qualify=qualify, n_best_third=n_best_third)


# ----------------------------------------------------------------------
# 7. RATINGS <-> MARKET PROBABILITIES
# ----------------------------------------------------------------------
def ratings_from_probs(prob_by_team, scale=400.0, base=1500.0):
    """Seed Elo ratings from (market-implied) title probabilities: stronger teams get
    higher ratings, monotone in log-odds. Anchors the model to the real field. The
    bracket path then makes model != market -> that gap is the dislocation signal."""
    eps = 1e-4
    items = {t: np.log(max(p, eps)) for t, p in prob_by_team.items()}
    mean = np.mean(list(items.values()))
    return {t: base + scale / np.log(10) * (v - mean) for t, v in items.items()}


# ----------------------------------------------------------------------
# 8. VALIDATION ON GROUND TRUTH
# ----------------------------------------------------------------------
def run_validation():
    rng = np.random.default_rng(7)
    R = ["=" * 72,
         "WORLDCUP_SIM — validation on analytic / synthetic ground truth",
         "=" * 72]

    # --- (a) Elo update: conservation, direction, upset sensitivity ---
    ra, rb = 1600.0, 1500.0
    na, nb = elo_update(ra, rb, 2, 1)
    cons = abs((na - ra) + (nb - rb))
    up_fav = elo_update(1500, 1500, 1, 0)[0] - 1500          # beat an equal team
    up_dog = elo_update(1300, 1700, 1, 0)[0] - 1300          # upset a stronger team
    R += ["",
          "(a) Elo update",
          f"   zero-sum conservation |dA+dB|      : {cons:.2e}  (want ~0)",
          f"   winner gains rating                : {na - ra:+.2f}",
          f"   upset (beat +400) vs expected win  : {up_dog:.2f} > {up_fav:.2f}  "
          f"=> {'OK' if up_dog > up_fav else 'FAIL'}"]

    # --- (b) Knockout ANALYTIC ground truth: title prob = p**rounds ---
    # one super team with win prob p vs an otherwise-equal field of 8 (3 rounds)
    p = 0.75
    r_field = 1500.0
    r_super = r_field - 400.0 * np.log10(1.0 / p - 1.0)      # expected_score(super,field)=p
    field = [f"T{i}" for i in range(8)]
    ratings = {t: r_field for t in field}
    ratings["SUPER"] = r_super
    seeds = ["SUPER"] + field[:7]                            # 8-team bracket, 3 rounds
    n = 40000
    wins = sum(knockout_champion(seeds, ratings, rng) == "SUPER" for _ in range(n))
    emp = wins / n; analytic = p ** 3
    se = np.sqrt(emp * (1 - emp) / n)
    R += ["",
          "(b) Knockout — title prob of a super-team (win prob p=0.75 each round, 3 rounds)",
          f"   analytic  p**3                     : {analytic:.3f}",
          f"   simulated                          : {emp:.3f} ± {2*se:.3f} (95% MC)",
          f"   => {'OK' if abs(emp - analytic) < 3*se + 0.01 else 'FAIL'}"]

    # --- (c) Goals model realism: avg goals, draw rate, rating->points monotonic ---
    tot, draws, m = 0.0, 0, 6000
    for _ in range(m):
        ga, gb = match_goals(1500, 1500, rng)
        tot += ga + gb; draws += (ga == gb)
    teams16 = [f"G{i}" for i in range(4)]
    rat = {t: 1500 + 120 * i for i, t in enumerate(teams16)}  # strictly increasing strength
    pts = {t: 0 for t in teams16}
    for _ in range(4000):
        for row in group_standings(teams16, rat, rng):
            pts[row["team"]] += row["Pts"]
    order = [pts[t] for t in teams16]
    monotone = all(order[i] < order[i + 1] for i in range(len(order) - 1))
    R += ["",
          "(c) Goals model realism",
          f"   avg total goals / match            : {tot/m:.2f}  (want ~2.7)",
          f"   draw rate                          : {draws/m:.0%}  (want ~25-30%)",
          f"   stronger teams earn more points     : {'OK (monotone)' if monotone else 'FAIL'}"]

    # --- (d) Monte Carlo convergence: SE shrinks ~1/sqrt(n) ---
    groups = {chr(65 + i): [f"{chr(65+i)}{j}" for j in range(4)] for i in range(8)}
    rr = {t: rng.normal(1500, 120) for ts in groups.values() for t in ts}
    se_small = max(v["title_se"] for v in monte_carlo(groups, rr, 2000, seed=1).values())
    se_big = max(v["title_se"] for v in monte_carlo(groups, rr, 8000, seed=1).values())
    ratio = se_small / max(se_big, 1e-12)
    R += ["",
          "(d) Monte Carlo convergence (max title-prob SE)",
          f"   n=2000 -> {se_small:.4f} ;  n=8000 -> {se_big:.4f}",
          f"   ratio {ratio:.2f} (want ~2.0 for 4x sims)  => {'OK' if 1.6 < ratio < 2.5 else 'CHECK'}"]

    # --- (e) FULL-LADDER depth: super-team reach-round probs = p**k; nested monotonicity ---
    p = 0.75                                                  # super-team per-match win prob
    r_field, r_super = 1500.0, 1500.0 - 400.0 * np.log10(1.0 / p - 1.0)
    field8 = [f"K{i}" for i in range(7)]
    rat = {t: r_field for t in field8}; rat["SUPER"] = r_super
    seeds = ["SUPER"] + field8                                # 8-team bracket, 3 rounds
    n = 40000
    d = {1: 0, 2: 0, 3: 0}
    for _ in range(n):
        _c, wins = knockout_run(seeds, rat, rng)
        for k in d:
            if wins["SUPER"] >= k:
                d[k] += 1
    sf, fin, win = d[1] / n, d[2] / n, d[3] / n              # reach SF / final / win = p^1 / p^2 / p^3
    ok_depth = all(abs(e - p ** k) < 0.012 for k, e in ((1, sf), (2, fin), (3, win)))
    # nested monotonicity on a real-ish random field
    gl = monte_carlo_ladder(groups, rr, n_sims=3000, seed=2, qualify=2, n_best_third=0)
    teams_all = list(gl["win"])
    mono = all(gl["advance"][t] >= gl["reach_QF"][t] >= gl["reach_SF"][t]
               >= gl["reach_F"][t] >= gl["win"][t] - 1e-9 for t in teams_all)
    R += ["",
          "(e) Full ladder — knockout depth analytic + nested monotonicity",
          f"   super-team reach SF/final/win        : {sf:.3f}/{fin:.3f}/{win:.3f}  "
          f"vs p^k {p:.3f}/{p**2:.3f}/{p**3:.3f}  => {'OK' if ok_depth else 'FAIL'}",
          f"   advance>=QF>=SF>=F>=win for all teams: {'OK' if mono else 'FAIL'}",
          "=" * 72]
    report = "\n".join(R)
    print(report)
    return report


if __name__ == "__main__":
    run_validation()
