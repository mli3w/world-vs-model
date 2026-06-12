"""
make_reliability.py — calibration / reliability plot (assets/wvm_reliability.png)
==================================================================================
The forecasting evaluation chart that quants actually look for: a reliability diagram showing,
for each predicted-probability bin, the realized frequency of the event happening — with the
diagonal as the "perfect calibration" reference. Two (or three) lines: market vs zero-knowledge
(vs informed Elo, if available). Brier scores in the legend make it directly readable.

Reads `ledger/predictions.jsonl`, filters to resolved forecasts at a given `level` (default
"advance"), and produces a single share asset. Pre-tournament (no resolved data) it emits a
graceful "lights up after the first round" placeholder, so it's safe to wire into the cron.

    python src/make_reliability.py [--level advance] [--bins 5]

References:
- Murphy, A. H. (1973). "A new vector partition of the probability score." J. Appl. Meteorology.
- Bröcker, J. (2009). "Reliability, sufficiency, and the decomposition of proper scores."
- Brier, G. W. (1950). "Verification of forecasts expressed in terms of probability."

Research/education only — paper scoring, not betting advice.
"""
import os
import sys
import json
import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREDICTIONS_DEFAULT = os.path.join(ROOT, "ledger", "predictions.jsonl")
OUT = os.path.join(ROOT, "assets", "wvm_reliability.png")

# On-brand palette
NAVY = (12 / 255, 20 / 255, 36 / 255)
INK = (233 / 255, 237 / 255, 248 / 255)
INK2 = (170 / 255, 182 / 255, 212 / 255)
INK3 = (124 / 255, 144 / 255, 179 / 255)
TEAL = (63 / 255, 217 / 255, 163 / 255)
BLUE = (79 / 255, 124 / 255, 232 / 255)
VIOL = (139 / 255, 109 / 255, 255 / 255)
LINE = (44 / 255, 60 / 255, 90 / 255)

LEVEL_LABEL = {"advance": "Last 32 (advance from groups)", "reach_QF": "Quarter-finals",
               "reach_SF": "Semi-finals", "reach_F": "Final", "win": "Champion"}


def _apply_theme():
    plt.rcParams.update({
        "figure.facecolor": NAVY, "savefig.facecolor": NAVY,
        "axes.facecolor": NAVY, "axes.edgecolor": INK3,
        "axes.labelcolor": INK, "axes.titlecolor": INK,
        "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
        "grid.color": LINE, "axes.grid": True,
        "grid.linestyle": "-", "grid.linewidth": 0.5, "grid.alpha": 0.6,
        "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "Inter", "DejaVu Sans"],
        "mathtext.fontset": "stix", "mathtext.default": "regular",
    })


def _load_resolved(path, level):
    """Load resolved forecasts at `level` (newest per (model, team)). Each row: model, prob,
    market (the de-vigged baseline), outcome ∈ {0, 1}."""
    if not os.path.exists(path):
        return []
    by_key = {}                                                # (model, team) -> newest row
    for ln in open(path, encoding="utf-8"):
        if not ln.strip():
            continue
        r = json.loads(ln)
        if r.get("level") != level or r.get("outcome") is None:
            continue
        k = (r["model"], r["team"])
        if k not in by_key or r["date"] >= by_key[k]["date"]:
            by_key[k] = r
    return list(by_key.values())


def _bin(rows, prob_key, n_bins):
    """Equal-width binning of predicted probability. Returns list of (mean_p, freq, n, se)."""
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    out = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        in_bin = [r for r in rows if lo <= r[prob_key] < hi
                  or (i == n_bins - 1 and r[prob_key] == 1.0)]
        if not in_bin:
            continue
        ps = np.array([r[prob_key] for r in in_bin])
        ys = np.array([float(r["outcome"]) for r in in_bin])
        mean_p, freq, n = float(ps.mean()), float(ys.mean()), len(in_bin)
        se = float(np.sqrt(freq * (1 - freq) / n)) if n > 1 else 0.0
        out.append((mean_p, freq, n, se))
    return out


def _brier(rows, prob_key):
    return float(np.mean([(r[prob_key] - r["outcome"]) ** 2 for r in rows])) if rows else None


def _placeholder(out, level):
    """Pre-tournament — show an inviting empty state instead of a broken plot."""
    _apply_theme()
    fig, ax = plt.subplots(figsize=(11, 11))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.plot([0, 1], [0, 1], "--", color=INK3, lw=2.0, alpha=0.7)
    ax.text(0.5, 0.5, "Lights up after the first round resolves",
            ha="center", va="center", fontsize=22, color=INK2, transform=ax.transAxes)
    ax.text(0.5, 0.42,
            f"Calibration of pre-tournament forecasts at the {LEVEL_LABEL.get(level, level)} level",
            ha="center", va="center", fontsize=14, color=INK3, transform=ax.transAxes,
            style="italic")
    ax.set_xlabel("predicted probability", fontsize=16, labelpad=10)
    ax.set_ylabel("realized frequency", fontsize=16, labelpad=10)
    ax.set_title("Reliability plot · forecast calibration", fontsize=20, pad=14)
    fig.text(0.5, 0.018,
             "World vs Model · mli3w.github.io/world-vs-model · research only, not betting",
             ha="center", fontsize=11, color=INK3)
    fig.savefig(out, dpi=180, facecolor=NAVY, bbox_inches="tight", pad_inches=0.35)
    plt.close(fig)
    print(f"[reliability] wrote placeholder (no resolved forecasts at level={level}) -> {out}")


def build(path=PREDICTIONS_DEFAULT, level="advance", n_bins=5, out=OUT):
    rows = _load_resolved(path, level)
    if not rows:
        return _placeholder(out, level)
    _apply_theme()

    zk = [r for r in rows if r["model"] == "zero_knowledge"]
    elo = [r for r in rows if r["model"] == "elo"]

    series = []
    # Market is the same per (level, team), so just use ZK's set if it exists, else Elo's.
    base = zk or elo
    if base:
        b = _brier(base, "market")
        series.append(("Market (de-vigged)", _bin(base, "market", n_bins), TEAL, "o", b))
    if zk:
        series.append((r"Zero-knowledge ($\alpha=1.15$)", _bin(zk, "prob", n_bins), BLUE, "o",
                       _brier(zk, "prob")))
    if elo:
        series.append(("Informed · Elo", _bin(elo, "prob", n_bins), VIOL, "s", _brier(elo, "prob")))

    fig, ax = plt.subplots(figsize=(11, 11))
    ax.plot([0, 1], [0, 1], "--", color=INK3, lw=2.0, alpha=0.7, label="perfect calibration")

    for label, calib, color, marker, b in series:
        if not calib:
            continue
        xs = [c[0] for c in calib]
        ys = [c[1] for c in calib]
        es = [c[3] for c in calib]
        ns = [c[2] for c in calib]
        lbl = f"{label}  ·  Brier {b:.3f}" if b is not None else label
        ax.errorbar(xs, ys, yerr=es, color=color, lw=3, marker=marker, markersize=11,
                    capsize=5, capthick=1.5, label=lbl, alpha=0.95)
        for x, y, n in zip(xs, ys, ns):
            ax.annotate(f"n={n}", (x, y), textcoords="offset points", xytext=(7, 7),
                        fontsize=9, color=color, alpha=0.85)

    n_zk = len(zk); n_elo = len(elo)
    n_total = max(n_zk, n_elo)
    ax.set_xlim(-0.03, 1.03); ax.set_ylim(-0.03, 1.03)
    ax.set_xticks(np.arange(0, 1.01, 0.1)); ax.set_yticks(np.arange(0, 1.01, 0.1))
    ax.tick_params(labelsize=11)
    ax.set_xlabel("predicted probability", fontsize=16, labelpad=10)
    ax.set_ylabel("realized frequency", fontsize=16, labelpad=10)
    ax.legend(loc="upper left", fontsize=12, frameon=False, labelcolor="linecolor")
    ax.set_title(f"Reliability plot · {LEVEL_LABEL.get(level, level)} · {n_total} forecasts scored",
                 fontsize=18, pad=14)

    # methodological footnote: error bars are ±1σ binomial
    fig.text(0.10, 0.045, r"error bars: $\pm 1\sigma$ binomial $= \sqrt{p(1-p)/n}$    ·    "
                          r"Brier = $\frac{1}{n}\sum (p_i - o_i)^2$  (lower is better)",
             fontsize=11, color=INK3, ha="left")
    fig.text(0.5, 0.018,
             "World vs Model · mli3w.github.io/world-vs-model · research only, not betting",
             ha="center", fontsize=11, color=INK3)

    fig.savefig(out, dpi=180, facecolor=NAVY)
    plt.close(fig)
    print(f"[reliability] wrote {out}  (level={level}, n={n_total})")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Reliability / calibration plot for the wvm scorecard")
    ap.add_argument("--predictions", default=PREDICTIONS_DEFAULT, help="path to predictions.jsonl")
    ap.add_argument("--level", default="advance", help="market rung to score (advance/reach_QF/SF/F/win)")
    ap.add_argument("--bins", type=int, default=5, help="number of probability bins (default 5)")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    build(path=a.predictions, level=a.level, n_bins=a.bins, out=a.out)


if __name__ == "__main__":
    main()
