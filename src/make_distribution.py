"""
make_distribution.py — "how far each team goes" (assets/wvm_distribution.png)
=============================================================================
A stacked horizontal bar per team showing the model's *full* distribution over where it bows out:
out in the groups, Round of 32, Round of 16, Quarter-final, Semi-final, Runner-up, Champion. Sorted
by title odds; the champion % is called out at the right. From the informed (Elo) Monte-Carlo ladder.

    python src/make_distribution.py

Reuses make_chart's palette/fonts/flag fetch; degrades to no-flags if offline.
Research/education only — a model projection, not gambling.
"""
import os
import io
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests                                  # noqa: E402
from PIL import Image, ImageDraw                 # noqa: E402
import make_chart as MC                          # noqa: E402
import worldcup_markets as WM                    # noqa: E402
import worldcup_fundamental as WF                # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "wvm_distribution.png")
NAVY, INK, INK2, INK3 = MC.NAVY, MC.INK, MC.INK2, MC.INK3
# the 7 stages, left → right, with their colours (a blue ramp into violet, then grey, then gold)
STAGES = [
    ("out", "Out in groups", (150, 166, 196)),
    ("r32", "Round of 32", (38, 56, 110)),
    ("r16", "Round of 16", (54, 94, 196)),
    ("qf", "Quarter-final", (74, 158, 226)),
    ("sf", "Semi-final", (139, 109, 255)),
    ("ru", "Runner-up", (176, 186, 208)),
    ("champ", "Champion", (240, 191, 73)),
]
N_TEAMS = 28


def _rows(n_sims=20000):
    """Per-team stage distribution (clamped ≥0, sums to 1), sorted by title odds."""
    f = WF.fundamental_ladder(n_sims=n_sims, seed=0)
    adv, r16, qf, sf, rf, win = (f.get(k, {}) for k in
                                 ("advance", "reach_R16", "reach_QF", "reach_SF", "reach_F", "win"))
    out = []
    for t in {x for d in (adv, win) for x in d}:
        a, b, c, d2, e, w = (adv.get(t, 0), r16.get(t, 0), qf.get(t, 0),
                             sf.get(t, 0), rf.get(t, 0), win.get(t, 0))
        seg = dict(out=max(0, 1 - a), r32=max(0, a - b), r16=max(0, b - c), qf=max(0, c - d2),
                   sf=max(0, d2 - e), ru=max(0, e - w), champ=max(0, w))
        s = sum(seg.values()) or 1.0
        seg = {k: v / s for k, v in seg.items()}
        out.append(dict(team=t, win=w, seg=seg))
    out.sort(key=lambda r: -r["win"])
    return out[:N_TEAMS]


def _flag(t, sess):
    try:
        b = sess.get(f"https://flagcdn.com/80x60/{WM.info(t)[0]}.png", timeout=15).content
        return Image.open(io.BytesIO(b)).convert("RGBA").resize((34, 25), Image.LANCZOS)
    except Exception:
        return None


def build(out=OUT, n_sims=20000):
    rows = _rows(n_sims)
    sess = requests.Session()
    sess.headers.update({"User-Agent": "world-vs-model research"})
    flags = {r["team"]: _flag(r["team"], sess) for r in rows}

    W = 2000
    top, rowh = 230, 46
    H = top + len(rows) * rowh + 86
    im = Image.new("RGBA", (W, H), NAVY + (255,))
    d = ImageDraw.Draw(im)
    lerp = lambda a, b, t: tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    for x in range(W):
        d.line([(x, 0), (x, 8)], fill=lerp(MC.TEAL, MC.VIOL, x / W))
    d.text((48, 42), "How far each team goes", font=MC._font("segoeuib.ttf", 50), fill=INK)
    d.text((48, 108), "the model's full distribution over where each team bows out — sorted by title odds",
           font=MC._font("seguisb.ttf", 26), fill=INK2)
    lx = 48
    for _k, lab, col in STAGES:
        d.rounded_rectangle([lx, 168, lx + 22, 186], 3, fill=col)
        d.text((lx + 30, 166), lab, font=MC._font("seguisb.ttf", 21), fill=INK2)
        lx += 34 + d.textlength(lab, font=MC._font("seguisb.ttf", 21)) + 26

    x0, xmax = 150, W - 150
    bw = xmax - x0
    for i, r in enumerate(rows):
        cy = top + i * rowh + rowh / 2
        fg = flags.get(r["team"])
        if fg:
            im.alpha_composite(fg, (44, int(cy - 12)))
        d.text((90, cy), WM.code(r["team"]), font=MC._font("segoeuib.ttf", 21), fill=INK, anchor="lm")
        x = x0
        for k, _lab, col in STAGES:
            w = r["seg"][k] * bw
            if w > 0.5:
                d.rectangle([x, cy - 15, x + w, cy + 15], fill=col)
            x += w
        d.text((W - 130, cy), f'{r["win"]*100:.0f}%', font=MC._font("segoeuib.ttf", 23),
               fill=STAGES[-1][2], anchor="lm")

    fy = H - 60
    try:
        emb = Image.open(os.path.join(os.path.dirname(out), "wvm_mark.png")).convert("RGBA").resize((40, 40), Image.LANCZOS)
        im.alpha_composite(emb, (48, fy - 8))
    except OSError:
        pass
    d.text((98, fy - 6), "World vs Model", font=MC._font("segoeuib.ttf", 24), fill=INK)
    d.text((98, fy + 22), "mli3w.github.io/world-vs-model · informed (Elo) model · research only, not gambling",
           font=MC._font("segoeui.ttf", 18), fill=INK3)
    im.convert("RGB").save(out, "PNG")
    print(f"[distribution] wrote {out}  ({len(rows)} teams)")


if __name__ == "__main__":
    build()
