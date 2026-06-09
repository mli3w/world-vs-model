"""
make_groups.py — "projected group stage" cards (assets/wvm_groups.png)
======================================================================
The 12 groups (A–L) as cards: each team ranked by the model's expected finish, with its advance %.
Top-2 are green (qualify), the 3rd is gold (a best-third contender), the 4th is greyed (likely out).

    python src/make_groups.py

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

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "wvm_groups.png")
NAVY, INK, INK2, INK3 = MC.NAVY, MC.INK, MC.INK2, MC.INK3
CARD, LINE = (24, 34, 56), (44, 60, 90)
GREEN, GOLD, GREY = (52, 199, 120), (240, 191, 73), (120, 134, 162)


def _disp(t):
    nz = WM.WL._norm
    return next((x for x in WM.WL.FIELD if nz(x) == t), t)


def _pct(a):
    if a >= 0.9995:
        return "100%"
    if a >= 0.999:
        return ">99.9%"
    return f"{a*100:.0f}%"


def _rows(n_sims=20000):
    nz = WM.WL._norm
    f = WF.fundamental_ladder(n_sims=n_sims, seed=0)
    pos = WF.group_positions(n_sims=n_sims, seed=0)
    adv = f.get("advance", {})
    groups = WM.WL.GROUPS_2026
    out = {}
    for g, teams in groups.items():
        ranked = sorted(teams, key=lambda t: sum(i * p for i, p in enumerate(pos.get(nz(t), [0, 0, 0, 1]))))
        out[g] = [(t, adv.get(nz(t), 0.0)) for t in ranked]
    return out


def _flag(t, sess):
    try:
        b = sess.get(f"https://flagcdn.com/80x60/{WM.info(t)[0]}.png", timeout=15).content
        return Image.open(io.BytesIO(b)).convert("RGBA").resize((36, 27), Image.LANCZOS)
    except Exception:
        return None


def build(out=OUT, n_sims=20000):
    data = _rows(n_sims)
    sess = requests.Session()
    sess.headers.update({"User-Agent": "world-vs-model research"})
    flags = {t: _flag(t, sess) for g in data for t, _ in data[g]}

    W, H = 2000, 1230
    im = Image.new("RGBA", (W, H), NAVY + (255,))
    d = ImageDraw.Draw(im)
    lerp = lambda a, b, t: tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    for x in range(W):
        d.line([(x, 0), (x, 8)], fill=lerp(MC.TEAL, MC.VIOL, x / W))
    d.text((48, 40), "Projected group stage", font=MC._font("segoeuib.ttf", 50), fill=INK)
    d.text((48, 106), "each team by the model's expected finish, with its chance to advance",
           font=MC._font("seguisb.ttf", 26), fill=INK2)
    # legend
    d.ellipse([48, 162, 66, 180], fill=GREEN); d.text((74, 158), "top-2 qualify", font=MC._font("seguisb.ttf", 21), fill=INK2)
    d.ellipse([260, 162, 278, 180], fill=GOLD); d.text((286, 158), "3rd — best-third contender", font=MC._font("seguisb.ttf", 21), fill=INK2)
    d.ellipse([620, 162, 638, 180], fill=GREY); d.text((646, 158), "likely out", font=MC._font("seguisb.ttf", 21), fill=INK2)

    cols, top, mgn, gap = 4, 214, 48, 22
    cw = (W - 2 * mgn - (cols - 1) * gap) / cols
    ch, rowh = 312, 60
    GROUPS = list(data.keys())
    for idx, g in enumerate(GROUPS):
        r, c = divmod(idx, cols)
        x = mgn + c * (cw + gap)
        y = top + r * (ch + 18)
        d.rounded_rectangle([x, y, x + cw, y + ch], 14, fill=CARD, outline=LINE, width=1)
        d.text((x + 22, y + 16), f"GROUP {g}", font=MC._font("segoeuib.ttf", 22), fill=INK2)
        for i, (t, a) in enumerate(data[g]):
            ry = y + 64 + i * rowh
            col = GREEN if i < 2 else (GOLD if i == 2 else GREY)
            faded = INK if i < 3 else INK3
            d.text((x + 24, ry + rowh / 2), str(i + 1), font=MC._font("segoeuib.ttf", 22), fill=col, anchor="lm")
            fg = flags.get(t)
            if fg:
                im.alpha_composite(fg, (int(x + 50), int(ry + rowh / 2 - 13)))
            d.text((x + 98, ry + rowh / 2), _disp(t), font=MC._font("seguisb.ttf", 22), fill=faded, anchor="lm")
            d.text((x + cw - 22, ry + rowh / 2), _pct(a), font=MC._font("segoeuib.ttf", 22),
                   fill=col if i < 3 else INK3, anchor="rm")

    fy = H - 56
    try:
        emb = Image.open(os.path.join(os.path.dirname(out), "wvm_mark.png")).convert("RGBA").resize((40, 40), Image.LANCZOS)
        im.alpha_composite(emb, (48, fy - 8))
    except OSError:
        pass
    d.text((98, fy - 6), "World vs Model", font=MC._font("segoeuib.ttf", 24), fill=INK)
    d.text((98, fy + 22), "mli3w.github.io/world-vs-model · informed (Elo) model · research only, not gambling",
           font=MC._font("segoeui.ttf", 18), fill=INK3)
    im.convert("RGB").save(out, "PNG")
    print(f"[groups] wrote {out}")


if __name__ == "__main__":
    build()
