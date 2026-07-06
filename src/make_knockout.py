"""
make_knockout.py — the shareable "disagreement bracket" (assets/wvm_knockout.png)
=================================================================================
Concept A: one knockout funnel (QF → SF → Final → Champion) showing, per round, where the
**model** and the **market** disagree about who goes deep. Teams both sides back are neutral; a
team only the model backs gets a violet ring, a team only the market backs gets a teal ring. The
honest story is that they mostly agree — and the few contested calls are falsifiable by July.

    python src/make_knockout.py

Reuses make_chart's palette/fonts/flag fetch; degrades to no-flags if offline.
Research/education only — not financial advice, not gambling.
"""
import os
import io
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests                                  # noqa: E402
from PIL import Image, ImageDraw                 # noqa: E402
import make_chart as MC                          # noqa: E402  (palette, fonts, stars)
import worldcup_markets as WM                    # noqa: E402
import worldcup_fundamental as WF                # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "wvm_knockout.png")
NAVY, TEAL, VIOL, GOLD = MC.NAVY, MC.TEAL, MC.VIOL, MC.GOLD
INK, INK2, INK3 = MC.INK, MC.INK2, MC.INK3
PANEL, LINE = (20, 30, 50), (36, 50, 76)
ROUNDS = [("reach_QF", "QUARTER-FINALS", 8), ("reach_SF", "SEMI-FINALS", 4),
          ("reach_F", "THE FINAL", 2), ("win", "CHAMPION", 1)]


def _topk(probs, k):
    return [t for t, _ in sorted(probs.items(), key=lambda kv: -kv[1])[:k]]


def _disp(t):
    """Full display name for a normalized team key (Spain, not 'spain')."""
    nz = WM.WL._norm
    return next((x for x in WM.WL.FIELD if nz(x) == t), t)


def _rows(n_sims=20000, results=None):
    """For each knockout round: the model's and the market's top-k teams (by reach probability)."""
    if results is None:
        results = WF.load_results()
    fund = WF.fundamental_ladder(n_sims=n_sims, seed=0, results=results)
    mkt = WM.fetch_ladder()
    out = []
    for lvl, label, k in ROUNDS:
        model = _topk(fund.get(lvl, {}), k)
        market = _topk(mkt.get(lvl, {}), k)
        union = list(dict.fromkeys(model + market))           # agreed first-ish, stable
        out.append(dict(lvl=lvl, label=label, k=k, model=set(model), market=set(market), union=union))
    return out


def _flags(teams, sess, size=(64, 47)):
    imgs = {}
    for t in teams:
        try:
            iso = WM.info(t)[0]
            b = sess.get(f"https://flagcdn.com/80x60/{iso}.png", timeout=15).content
            imgs[t] = Image.open(io.BytesIO(b)).convert("RGBA").resize(size, Image.LANCZOS)
        except Exception:
            imgs[t] = None
    return imgs


def build(rows=None, out=OUT, results=None):
    rows = rows or _rows(results=results)
    sess = requests.Session()
    sess.headers.update({"User-Agent": "world-vs-model research"})
    allteams = {t for r in rows for t in r["union"]}
    flags = _flags(allteams, sess)
    champ = next((t for t in rows[-1]["union"]), None)
    champ_flag = _flags([champ], sess, size=(130, 97)).get(champ) if champ else None

    W, H = 1500, 1560
    im = Image.new("RGBA", (W, H), NAVY + (255,))
    d = ImageDraw.Draw(im)
    lerp = lambda a, b, t: tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    for x in range(W):
        t = x / W
        d.line([(x, 0), (x, 8)], fill=lerp(TEAL, VIOL, t))
    d.text((48, 44), "Who goes deep at the 2026 World Cup?", font=MC._font("segoeuib.ttf", 50), fill=INK)
    d.text((48, 112), "My model vs the betting market — the knockout calls where they disagree",
           font=MC._font("seguisb.ttf", 27), fill=INK2)
    # legend
    ly = 168
    d.ellipse([48, ly, 66, ly + 18], outline=VIOL, width=3)
    d.text((74, ly - 3), "model backs", font=MC._font("seguisb.ttf", 22), fill=INK2)
    d.ellipse([250, ly, 268, ly + 18], outline=TEAL, width=3)
    d.text((276, ly - 3), "market backs", font=MC._font("seguisb.ttf", 22), fill=INK2)
    d.text((470, ly - 3), "both agree = no ring", font=MC._font("seguisb.ttf", 22), fill=INK3)

    top, bottom = 220, H - 96
    bandh = (bottom - top) / len(rows)
    for i, r in enumerate(rows):
        by = top + i * bandh
        cy = by + bandh / 2
        d.line([(48, int(by)), (W - 48, int(by))], fill=LINE, width=1)
        d.text((48, int(by) + 14), r["label"], font=MC._font("segoeuib.ttf", 24), fill=INK3)
        d.text((48, int(by) + 46), f"last {r['k']}" if r["k"] > 1 else "the winner",
               font=MC._font("segoeui.ttf", 18), fill=INK3)
        if r["lvl"] == "win" and champ:                       # champion: one big crowned flag
            cx = W // 2
            if champ_flag:
                im.alpha_composite(champ_flag, (cx - 65, int(cy) - 64))
            d.text((cx, int(cy) + 44), _disp(champ),
                   font=MC._font("segoeuib.ttf", 36), fill=INK, anchor="mm")
            MC._star(d, cx, int(cy) - 88, 15, GOLD)
            note = ("model & market agree" if r["model"] == r["market"]
                    else "model & market disagree")
            d.text((cx, int(cy) + 84), note, font=MC._font("seguisb.ttf", 22), fill=INK3, anchor="mm")
            continue
        teams = r["union"]
        n = len(teams)
        cell = min(190, (W - 240) / max(n, 1))
        x0 = (W - cell * n) / 2 + 40
        fw, fh = 64, 47
        for j, t in enumerate(teams):
            x = x0 + j * cell + cell / 2
            ring = VIOL if (t in r["model"] and t not in r["market"]) else (
                TEAL if (t in r["market"] and t not in r["model"]) else None)
            fg = flags.get(t)
            if fg:
                im.alpha_composite(fg, (int(x - fw / 2), int(cy - fh / 2 - 8)))
            if ring:
                d.rounded_rectangle([x - fw / 2 - 6, cy - fh / 2 - 14, x + fw / 2 + 6, cy + fh / 2 - 2],
                                    7, outline=ring, width=4)
            d.text((x, int(cy) + 38), WM.code(t), font=MC._font("segoeuib.ttf", 23), fill=INK, anchor="mm")

    fy = H - 64
    try:
        emb = Image.open(os.path.join(os.path.dirname(out), "wvm_mark.png")).convert("RGBA").resize((42, 42), Image.LANCZOS)
        im.alpha_composite(emb, (48, fy - 6))
    except OSError:
        pass
    d.text((100, fy - 4), "World vs Model", font=MC._font("segoeuib.ttf", 25), fill=INK)
    d.text((100, fy + 23), "mli3w.github.io/world-vs-model · research & education only, not gambling",
           font=MC._font("segoeui.ttf", 19), fill=INK3)
    im.convert("RGB").save(out, "PNG")
    print(f"[knockout] wrote {out}")


if __name__ == "__main__":
    build()
