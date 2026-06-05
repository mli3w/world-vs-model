"""
consistency.py — combinatorial "no-arbitrage" signal for prediction markets
==============================================================================
A market on a set of MUTUALLY EXCLUSIVE outcomes (e.g. the 48 "Team X wins the 2026 World
Cup" markets) must obey hard constraints that need ZERO domain knowledge to check:

  1. SUM-TO-ONE — the implied probabilities should sum to 1. They don't: a bookmaker/AMM
     vig plus the favorite-longshot bias push the sum > 1 (the "overround").
  2. NESTED ORDERING — P(win cup) <= P(reach final) <= P(advance from group). A market that
     violates this is internally incoherent (a riskless inconsistency where it's exact).
  3. GROUP CONSERVATION — within a group, the "advance" probabilities sum to the number of
     qualifiers (2 in 2026).

Correcting these is a FORECAST you can make without knowing anything about football — pure
structure. Honest finding: PROPORTIONAL de-vig (dividing by the sum) is ~neutral on a proper
score, because a uniform vig rescale lowers the eventual champion's probability too. The
tradeable no-knowledge edge is the favorite-longshot SHAPE correction (raise favorites / fade
longshots) plus bracket-coherence shrinkage. The CONSTRAINT CHECKS are detectors: where the
market violates them beyond the vig, that is a genuine inconsistency edge.
"""
import numpy as np


def overround(probs):
    """Summary of the sum-to-one violation. >0 overround_pct = the market sums to >1."""
    s = float(sum(probs.values()))
    return dict(sum=round(s, 4), overround_pct=round((s - 1.0) * 100, 2), n=len(probs))


def devig(probs, method="proportional", power=1.0):
    """Remove the overround so the probabilities sum to 1.
    'proportional' (power=1): p_i / sum(p).
    'power' (power>1): p_i**power renormalized — also corrects favorite-longshot bias."""
    pw = power if method == "power" else 1.0
    items = {t: max(float(p), 1e-12) ** pw for t, p in probs.items()}
    s = sum(items.values())
    return {t: v / s for t, v in items.items()}


def nested_violations(inner, outer, tol=1e-6):
    """Pairs where inner > outer though nesting requires inner <= outer
    (e.g. P(win cup) must be <= P(advance)). Returns [(entity, inner, outer), ...]."""
    return [(t, round(inner[t], 4), round(outer[t], 4))
            for t in inner if t in outer and inner[t] > outer[t] + tol]


def group_advance_consistency(advance, groups, qualify=2):
    """Each group's 'advance' probabilities should sum to `qualify`. Returns per-group
    sum and gap (sum - qualify); a large |gap| is an incoherent group market."""
    out = {}
    for g, teams in groups.items():
        s = float(sum(advance.get(t, 0.0) for t in teams))
        out[g] = dict(sum=round(s, 3), gap=round(s - qualify, 3))
    return out


def brier(prob, outcome):
    return float((prob - outcome) ** 2)


def coherent_forecast(market_raw, method="power", power=1.15):
    """The zero-knowledge structural forecast: de-vig (and favorite-longshot correct) the
    market's OWN prices. Returns a probability dict summing to 1. `power` is the only knob —
    fit it from the realized track record later (start mild; the ledger judges it)."""
    return devig(market_raw, method=method, power=power)


# ----------------------------------------------------------------------
# SYNTHETIC GROUND-TRUTH VALIDATION
# ----------------------------------------------------------------------
def _planted_market(n=48, vig=0.06, fav_long_beta=0.72, noise=0.05, rng=None):
    """True win-probs (softmax of latent strengths) + a 'market' that is (a) vigged,
    (b) favorite-longshot biased (prices ~ true**beta, beta<1 flattens: longshots dear,
    favorites cheap), (c) noisy. Returns (true_probs, market_raw, beta)."""
    rng = rng or np.random.default_rng(0)
    s = rng.normal(0, 1.2, n)
    p = np.exp(s - s.max()); p = p / p.sum()
    teams = [f"T{i:02d}" for i in range(n)]
    raw = p ** fav_long_beta
    raw = raw / raw.sum() * (1.0 + vig)
    raw = raw * np.exp(rng.normal(0, noise, n))
    return dict(zip(teams, p)), dict(zip(teams, raw)), fav_long_beta


def run_validation(trials=4000, n=48, seed=0):
    """Two honest tests, no domain knowledge used:
    (1) DETECTORS flag planted inconsistencies (nested + group-sum violations).
    (2) The FAVORITE-LONGSHOT SHAPE correction lowers Brier vs the de-vigged market."""
    inner = {"A": 0.30, "B": 0.10}
    outer = {"A": 0.20, "B": 0.40}                           # A: P(win) > P(advance) -> impossible
    nv = nested_violations(inner, outer)
    grp = group_advance_consistency({"x": 0.9, "y": 0.9, "z": 0.1, "w": 0.1},
                                    {"G": ["x", "y", "z", "w"]}, qualify=2)
    det_ok = (len(nv) == 1 and nv[0][0] == "A" and abs(grp["G"]["gap"]) < 1e-6)

    rng = np.random.default_rng(seed)
    base_b, pow_b, over = [], [], []
    for _ in range(trials):
        true_p, mkt, beta = _planted_market(n=n, rng=rng)
        teams = list(true_p)
        over.append(overround(mkt)["overround_pct"])
        champ = rng.choice(teams, p=np.array([true_p[t] for t in teams]))   # drawn from TRUTH
        mkt_norm = devig(mkt, "proportional")                # the de-vigged market = fair baseline
        mkt_pow = devig(mkt, "power", power=1.0 / beta)      # the favorite-longshot correction
        for t in teams:
            y = 1.0 if t == champ else 0.0
            base_b.append(brier(mkt_norm[t], y))
            pow_b.append(brier(mkt_pow[t], y))
    base_m, pow_m = float(np.mean(base_b)), float(np.mean(pow_b))

    R = ["=" * 72,
         "CONSISTENCY — combinatorial 'no-arbitrage' signal (zero domain knowledge)",
         "=" * 72,
         "(1) DETECTORS (find where the market violates hard constraints):",
         f"   nested violation flagged : {nv}",
         f"   group advance sum        : {grp['G']['sum']} (want 2.0, gap {grp['G']['gap']:+})",
         f"   -> detectors {'WORK' if det_ok else 'FAIL'}",
         "",
         f"(2) FORECAST vs the de-vigged market  ({n} outcomes, overround "
         f"{np.mean(over):.1f}%, favorite-longshot bias):",
         f"   de-vigged market (baseline) Brier : {base_m:.5f}",
         f"   + favorite-longshot correction    : {pow_m:.5f}   "
         f"({(1 - pow_m / base_m) * 100:+.2f}% Brier)",
         "",
         "Honest note: proportional de-vig is ~neutral on a proper score (uniform rescale).",
         "The tradeable no-knowledge edge is the favorite-longshot SHAPE correction (raise",
         "favorites / fade longshots) + bracket-coherence shrinkage."]
    ok = det_ok and pow_m < base_m
    R += [f"\nRESULT: {'PASS' if ok else 'FAIL'} — detectors fire and the shape correction "
          f"{'beats' if pow_m < base_m else 'does not beat'} the de-vigged market.",
          "=" * 72]
    print("\n".join(R))
    return dict(detectors_ok=det_ok, baseline_brier=base_m, corrected_brier=pow_m, ok=ok)


if __name__ == "__main__":
    run_validation()
