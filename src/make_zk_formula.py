"""
make_zk_formula.py — the favourite-longshot correction (assets/wvm_alpha_curve.png)
====================================================================================
An educational, on-brand share card explaining the zero-knowledge model in one image. Top: the
formula in mathtext. Bottom: the binary-case transformation curve `p' = p^α / (p^α + (1-p)^α)`
for α=1.15 (our default) and α=1.30 (sharper), with the diagonal as the "no correction" baseline
and the regions where favourites are raised / longshots faded shaded for intuition.

The multi-outcome version used in production is `p_i^α / Σ_j p_j^α` — same shape, more dramatic
when there are many outcomes (48 winner markets). The binary version is the cleanest illustration.

    python src/make_zk_formula.py

Research/education only — not a recommendation, not betting.
"""
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "wvm_alpha_curve.png")

# On-brand palette (RGB 0-1 for matplotlib)
NAVY = (12 / 255, 20 / 255, 36 / 255)
INK = (233 / 255, 237 / 255, 248 / 255)
INK2 = (170 / 255, 182 / 255, 212 / 255)
INK3 = (124 / 255, 144 / 255, 179 / 255)
TEAL = (63 / 255, 217 / 255, 163 / 255)
BLUE = (79 / 255, 124 / 255, 232 / 255)
VIOL = (139 / 255, 109 / 255, 255 / 255)
GOLD = (240 / 255, 191 / 255, 73 / 255)
LINE = (44 / 255, 60 / 255, 90 / 255)


def alpha_correct(p, alpha):
    """The binary-case re-shaping: p' = p^α / (p^α + (1-p)^α). Used for the illustration curve."""
    pa, qa = p ** alpha, (1 - p) ** alpha
    return pa / (pa + qa)


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


def build(out=OUT):
    _apply_theme()
    fig, (ax_top, ax) = plt.subplots(
        2, 1, figsize=(12, 13),
        gridspec_kw={"height_ratios": [1, 2.4], "hspace": 0.22, "left": 0.10,
                     "right": 0.94, "top": 0.94, "bottom": 0.07},
    )

    # ---- Top: formula card (text on a borderless axis with normalised coords) ----
    ax_top.set_xlim(0, 1); ax_top.set_ylim(0, 1); ax_top.axis("off")
    ax_top.text(0.5, 0.96, "The favourite–longshot correction",
                ha="center", va="top", fontsize=32, fontweight="bold", color=INK,
                transform=ax_top.transAxes)
    ax_top.text(0.5, 0.78, "Zero-knowledge model · re-shape the market's own prices with one parameter",
                ha="center", va="top", fontsize=16, color=INK2, transform=ax_top.transAxes)
    ax_top.text(0.5, 0.36,
                r"$p'_{i} \; = \; \dfrac{p_{i}^{\,\alpha}}{\sum_{j} p_{j}^{\,\alpha}}\,, \qquad \alpha > 1$",
                ha="center", va="center", fontsize=40, color=INK, transform=ax_top.transAxes)
    ax_top.text(0.5, 0.02, "Raise α to fade longshots and raise favourites · our default α = 1.15",
                ha="center", va="bottom", fontsize=15, color=INK3, style="italic",
                transform=ax_top.transAxes)

    # ---- Bottom: transformation curve ----
    p = np.linspace(0.001, 0.999, 600)
    p_115 = alpha_correct(p, 1.15)
    p_130 = alpha_correct(p, 1.30)

    lo, hi = p < 0.5, p > 0.5
    ax.fill_between(p[lo], p[lo], p_115[lo], color=BLUE, alpha=0.12)
    ax.fill_between(p[hi], p[hi], p_115[hi], color=GOLD, alpha=0.12)

    ax.plot([0, 1], [0, 1], "--", color=INK3, lw=2.0, alpha=0.7, label=r"no correction  ($\alpha = 1$)")
    ax.plot(p, p_115, color=BLUE, lw=4.5, label=r"$\alpha = 1.15$  (our default)")
    ax.plot(p, p_130, color=VIOL, lw=3.0, alpha=0.80, label=r"$\alpha = 1.30$  (sharper)")

    ax.scatter([0.5], [0.5], s=70, color=INK, zorder=10, edgecolor=NAVY)
    ax.annotate("fixed at $p = 0.5$", (0.5, 0.5), xytext=(15, -22),
                textcoords="offset points", fontsize=12, color=INK2,
                arrowprops=dict(arrowstyle="-", color=INK3, lw=1))

    ax.text(0.20, 0.075, "longshots faded\n" r"$p\,' < p$  when  $p < 0.5$",
            fontsize=13, color=BLUE, fontweight="bold", va="bottom")
    ax.text(0.62, 0.90, "favourites raised\n" r"$p\,' > p$  when  $p > 0.5$",
            fontsize=13, color=GOLD, fontweight="bold", va="top")

    ax.set_xlabel(r"market's de-vigged probability  $p$", fontsize=16, labelpad=10)
    ax.set_ylabel(r"corrected probability  $p\,'$", fontsize=16, labelpad=10)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_xticks(np.arange(0, 1.01, 0.1))
    ax.set_yticks(np.arange(0, 1.01, 0.1))
    ax.tick_params(labelsize=11)
    leg = ax.legend(loc="upper left", fontsize=12, frameon=False, labelcolor="linecolor")
    ax.set_title(r"Binary illustration  ·  $p\,' = p^{\alpha}\,/\,(p^{\alpha} + (1-p)^{\alpha})$",
                 fontsize=14, color=INK2, pad=12)

    # brand footer at the very bottom of the figure
    fig.text(0.5, 0.018,
             "World vs Model  ·  mli3w.github.io/world-vs-model  ·  research & education only, not betting",
             ha="center", fontsize=11, color=INK3)

    fig.savefig(out, dpi=180, facecolor=NAVY)        # no bbox=tight — would re-inflate the canvas
    plt.close(fig)
    print(f"[zk_formula] wrote {out}")


if __name__ == "__main__":
    build()
