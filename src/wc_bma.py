"""
wc_bma.py — Bayesian Model Averaging (ensemble forecasts via Brier-weighted weights)
====================================================================================
A principled third forecast voice alongside the zero-knowledge and informed Elo models. For each
knockout rung we track each model's Brier track record so far and weight that model's forecasts
accordingly; the *ensemble* forecast is the weighted average.

The intuition (and the talking point): I don't have to commit to one model upfront — I let the
data decide, **per rung**, which model to trust more, with a self-correcting weighted average.

Weights (per level) are softmax(-eta · Brier_mean), so a model with consistently lower Brier at
that level gets a bigger weight. Pre-data: equal weights. As rounds resolve, the weights drift
toward whichever model is better-calibrated *at that rung*.

We use Brier (not strict log-likelihood) because:
  * we already track it,
  * it's bounded in [0, 1] (no -inf catastrophe when a forecast hits p=0 on outcome=1), and
  * it's the same proper scoring rule the public scorecard uses.

The name remains "BMA" because the spirit (data-weighted model averaging) is identical; the
choice of scoring rule is the practical difference. Strict BMA is recovered with log-loss.

Research/education only.
"""
import math


def _bsum(resolved):
    """Aggregate Brier sums and counts per (model, level) from resolved forecasts."""
    bs, bc = {}, {}
    for r in resolved:
        o = r.get("outcome")
        if o is None:
            continue
        k = (r["model"], r["level"])
        bs[k] = bs.get(k, 0.0) + (float(r["prob"]) - float(o)) ** 2
        bc[k] = bc.get(k, 0) + 1
    return bs, bc


def weights_per_level(resolved, models, levels, eta=10.0, prior_strength=4):
    """For each level, return {model: weight} from per-level Brier track records.

    `eta`            : how aggressively a Brier gap shifts the weights. eta=10 → a 0.05 Brier gap
                       moves the weight ratio by ~e^0.5 ≈ 1.65 (~62/38). Tunable but conservative.
    `prior_strength` : the equivalent "imaginary count" of 0.25-Brier (coin-flip) prior forecasts
                       blended into each model at each level. This shrinks the weights toward 50/50
                       when we only have a few resolved data points, so we don't whipsaw on noise.
    """
    bs, bc = _bsum(resolved)
    out = {}
    for level in levels:
        scores = {}
        for m in models:
            n = bc.get((m, level), 0)
            b = bs.get((m, level), 0.0)
            # shrink the empirical Brier toward 0.25 (a coin-flip) with a fake count of prior_strength
            b_shrunk = (b + 0.25 * prior_strength) / (n + prior_strength)
            scores[m] = -eta * b_shrunk
        # softmax for numerical stability
        m0 = max(scores.values()) if scores else 0.0
        exps = {m: math.exp(s - m0) for m, s in scores.items()}
        Z = sum(exps.values()) or 1.0
        out[level] = {m: round(e / Z, 4) for m, e in exps.items()}
    return out


def ensemble_forecasts(forecasts, weights):
    """Combine per-model forecasts into one ensemble per (level, team).

    `forecasts` : {(model, level, team): probability}
    `weights`   : {level: {model: weight}}  (weights sum to 1 per level)
    Returns       {(level, team): ensemble_probability}  for every (level, team) seen.
    """
    by_level_team = {}                                       # (level, team) -> {model: prob}
    for (m, level, team), p in forecasts.items():
        by_level_team.setdefault((level, team), {})[m] = p
    out = {}
    for (level, team), per_model in by_level_team.items():
        w = weights.get(level, {})
        p = 0.0
        z = 0.0                                              # renormalise over the models that DO forecast this
        for m, prob in per_model.items():
            wm = w.get(m, 0.0)
            p += wm * prob
            z += wm
        out[(level, team)] = round(p / z, 4) if z > 0 else 0.0
    return out


def bma(forecasts, resolved, models=None, levels=None, eta=10.0):
    """One-stop: compute (weights_per_level, ensemble_forecasts) from `forecasts` and `resolved`.

    `forecasts` : {(model, level, team): probability}    (the latest registered forecasts)
    `resolved`  : list of {model, level, team, prob, outcome} (forecasts whose outcomes are in)
    Returns dict(weights={level: {model: w}}, ensemble={(level, team): p}, n_resolved=int).
    """
    models = models or sorted({m for (m, _l, _t) in forecasts.keys()})
    levels = levels or sorted({l for (_m, l, _t) in forecasts.keys()})
    w = weights_per_level(resolved, models, levels, eta=eta)
    e = ensemble_forecasts(forecasts, w)
    n = sum(1 for r in resolved if r.get("outcome") is not None)
    return dict(weights=w, ensemble=e, n_resolved=n, models=models, levels=levels)
