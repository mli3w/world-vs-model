"""
make_chart.py — the shareable "model vs market" chart (assets/wvm_chart.png)
============================================================================
A clean, on-brand bar chart for socials: each contender's chance to win the World Cup per the
model (Elo) vs the market (Polymarket), with the country flag and gold stars for past World Cup
titles. Re-run before posting so the numbers match the live board:

    python src/make_chart.py

Fetches flags from flagcdn + live prices from Polymarket; degrades to no-flags if offline.
Research/education only — not financial advice, not gambling.
"""
import os
import io
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests                          # noqa: E402
from PIL import Image, ImageDraw, ImageFont   # noqa: E402
import worldcup_markets as WM            # noqa: E402
import worldcup_fundamental as WF        # noqa: E402
from worldcup_live import _norm          # noqa: E402

TEAMS = ["Spain", "France", "Argentina", "England", "Brazil", "Portugal", "Germany"]
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "wvm_chart.png")
_FONTS = r"C:/Windows/Fonts"
NAVY, TEAL, BLUE, VIOL = (12, 20, 36), (63, 217, 163), (79, 124, 232), (139, 109, 255)
GOLD, INK, INK2, INK3 = (240, 191, 73), (233, 237, 248), (170, 182, 212), (124, 144, 179)


def _font(name, size):
    try:
        return ImageFont.truetype(os.path.join(_FONTS, name), size)
    except OSError:
        return ImageFont.load_default()


def _rows(results=None):
    if results is None:
        results = WF.load_results()
    fl = WF.fundamental_ladder(n_sims=20000, seed=0, results=results)
    mkt = WM.fetch_ladder()
    s = sum(mkt["win"].values()) or 1.0
    dv = {t: p / s for t, p in mkt["win"].items()}
    sess = requests.Session()
    sess.headers.update({"User-Agent": "world-vs-model research"})
    out = []
    for t in TEAMS:
        n = _norm(t)
        iso, _rank, titles = WM.info(t)
        flag = None
        try:
            b = sess.get(f"https://flagcdn.com/80x60/{iso}.png", timeout=15).content
            flag = Image.open(io.BytesIO(b)).convert("RGBA")
        except Exception:
            pass
        out.append(dict(team=t, titles=titles, flag=flag,
                        market=round(dv.get(n, 0) * 100, 1), model=round(fl["win"].get(n, 0) * 100, 1)))
    return out


def _star(d, cx, cy, r, fill):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    d.polygon(pts, fill=fill)


def build(rows=None, out=OUT, results=None):
    rows = rows or _rows(results)
    W, H = 1200, 1280
    im = Image.new("RGBA", (W, H), NAVY + (255,))
    d = ImageDraw.Draw(im)
    lerp = lambda a, b, t: tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    for x in range(W):                                       # teal->blue->violet accent bar
        t = x / W
        d.line([(x, 0), (x, 8)], fill=lerp(TEAL, BLUE, t / 0.5) if t < 0.5 else lerp(BLUE, VIOL, (t - 0.5) / 0.5))
    d.text((48, 46), "Who wins the 2026 World Cup?", font=_font("segoeuib.ttf", 56), fill=INK)
    d.text((48, 120), "Chance to lift the trophy — the model vs the market", font=_font("seguisb.ttf", 30), fill=INK2)
    ly = 180
    d.rounded_rectangle([48, ly, 70, ly + 22], 4, fill=TEAL)
    d.text((80, ly - 2), "Market (Polymarket)", font=_font("seguisb.ttf", 25), fill=INK2)
    d.rounded_rectangle([400, ly, 422, ly + 22], 4, fill=VIOL)
    d.text((432, ly - 2), "Model (Elo)", font=_font("seguisb.ttf", 25), fill=INK2)
    _star(d, 712, ly + 10, 9, GOLD)
    d.text((726, ly - 2), "= past World Cup titles", font=_font("seguisb.ttf", 23), fill=INK3)

    top, x0, xmax, maxv = 234, 472, W - 132, 18.0
    scale = (xmax - x0) / maxv
    rowh = (H - top - 92) / len(rows)
    for i, r in enumerate(rows):
        ty = top + i * rowh
        cy = ty + rowh / 2
        if r["flag"]:
            im.alpha_composite(r["flag"].resize((52, 39), Image.LANCZOS), (48, int(cy - 42)))
        d.text((112, int(cy - 44)), r["team"], font=_font("segoeuib.ttf", 30), fill=INK)
        sy = int(cy + 14)
        if r["titles"] > 0:
            for k in range(r["titles"]):
                _star(d, 124 + k * 30, sy, 11, GOLD)
        else:
            d.text((112, sy - 14), "no title yet", font=_font("segoeui.ttf", 20), fill=INK3)
        bw = r["market"] * scale
        d.rounded_rectangle([x0, cy - 32, x0 + bw, cy - 4], 6, fill=TEAL)
        d.text((x0 + bw + 12, cy - 34), f"{r['market']:.1f}%", font=_font("seguisb.ttf", 24), fill=TEAL)
        bw2 = r["model"] * scale
        d.rounded_rectangle([x0, cy + 4, x0 + bw2, cy + 32], 6, fill=VIOL)
        d.text((x0 + bw2 + 12, cy + 2), f"{r['model']:.1f}%", font=_font("seguisb.ttf", 24), fill=VIOL)
        d.line([(48, int(ty + rowh - 4)), (xmax, int(ty + rowh - 4))], fill=(28, 41, 65), width=1)

    fy = H - 66
    try:
        emb = Image.open(os.path.join(os.path.dirname(out), "wvm_mark.png")).convert("RGBA").resize((44, 44), Image.LANCZOS)
        im.alpha_composite(emb, (48, fy - 6))
    except OSError:
        pass
    d.text((104, fy - 4), "World vs Model", font=_font("segoeuib.ttf", 26), fill=INK)
    d.text((104, fy + 24), "mli3w.github.io/world-vs-model · research & education only, not gambling",
           font=_font("segoeui.ttf", 20), fill=INK3)
    im.convert("RGB").save(out, "PNG")
    print(f"[chart] wrote {out}  ({len(rows)} teams)")


if __name__ == "__main__":
    build()
