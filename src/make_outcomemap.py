"""
make_outcomemap.py — the full projected bracket (assets/wvm_outcomemap.png)
===========================================================================
A clean, classic tournament bracket of the informed (Elo) model's most-likely path: Round of 32
all the way to the champion, with the real FIFA slot structure (src/wc_bracket.py) filled by the
model's projected group standings. Two halves converge on the champion in the middle.

    python src/make_outcomemap.py

Reuses make_chart's palette/fonts/flag fetch; degrades to no-flags if offline.
Research/education only — a model projection, not a prediction of certainty; not gambling.
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
import wc_bracket as WB                          # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "wvm_outcomemap.png")
NAVY, TEAL, VIOL, GOLD = MC.NAVY, MC.TEAL, MC.VIOL, MC.GOLD
INK, INK2, INK3 = MC.INK, MC.INK2, MC.INK3
PANEL, LINE = (22, 32, 52), (44, 60, 90)
NW, NH = 150, 48                                 # node width/height (bigger = more legible flags/codes)


def _bracket(n_sims=20000, results=None):
    """The model's most-likely bracket. Once the group stage is decided we pour the REAL final
    standings into the official slots and honour actual knockout results (eliminated teams drop
    off the path); before that it is the pure pre-tournament projection. Either way the remaining,
    unplayed ties are filled by the live-re-forecast Elo model."""
    nz = WM.WL._norm
    groups = WM.WL.GROUPS_2026
    fund = WF.fundamental_ladder(n_sims=n_sims, seed=0, results=results)
    if results and WB.groups_complete(groups, results):
        rbg, table = WB.group_table(groups, results)           # real final standings
        third_groups = WB.best_third_groups(rbg, table)        # real best-eight thirds
    else:
        pos = WF.group_positions(n_sims=n_sims, seed=0, results=results)
        rbg = {g: sorted(t, key=lambda x: sum(i * p for i, p in enumerate(pos.get(nz(x), [0, 0, 0, 1]))))
               for g, t in groups.items()}
        third_groups = None
    win, adv, r16 = fund["win"], fund["advance"], fund["reach_R16"]
    strength = lambda t: (win.get(nz(t), 0), adv.get(nz(t), 0), r16.get(nz(t), 0))
    played = WB.ko_winners(results)                            # actual knockout winners so far
    return WB.resolve(rbg, strength, played=played, third_groups=third_groups), fund


def _disp(t):
    nz = WM.WL._norm
    return next((x for x in WM.WL.FIELD if nz(x) == t), t)


def _flag(t, sess, size=(38, 28)):
    try:
        iso = WM.info(t)[0]
        b = sess.get(f"https://flagcdn.com/80x60/{iso}.png", timeout=15).content
        return Image.open(io.BytesIO(b)).convert("RGBA").resize(size, Image.LANCZOS)
    except Exception:
        return None


def build(out=OUT, n_sims=20000, results=None):
    if results is None:
        results = WF.load_results()
    live = bool(results and WB.groups_complete(WM.WL.GROUPS_2026, results))
    br, fund = _bracket(n_sims, results)
    rounds = br["rounds"]                          # [32, 16, 8, 4, 2, 1] in bracket order
    champ = br["champ"]
    nz = WM.WL._norm
    win = fund["win"]
    sess = requests.Session()
    sess.headers.update({"User-Agent": "world-vs-model research"})
    flags = {t: _flag(t, sess) for t in rounds[0]}
    champ_flag = _flag(champ, sess, size=(72, 54)) if champ else None

    W, H = 2000, 1760
    im = Image.new("RGBA", (W, H), NAVY + (255,))
    d = ImageDraw.Draw(im)
    lerp = lambda a, b, t: tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    for x in range(W):
        d.line([(x, 0), (x, 9)], fill=lerp(TEAL, VIOL, x / W))
    d.text((50, 42), "The most-likely 2026 World Cup bracket", font=MC._font("segoeuib.ttf", 56), fill=INK)
    subtitle = ("Results so far + my informed (Elo) model for the rest — real FIFA slots, Round of 32 to the champion"
                if live else
                "My informed (Elo) model's projection — real FIFA slots, Round of 32 to the champion")
    d.text((50, 116), subtitle, font=MC._font("seguisb.ttf", 29), fill=INK2)

    margin, top_y, bot_y = 60, 268, H - 120
    step = (W - 2 * margin - NW) / 10.0
    col_cx = [margin + NW / 2 + k * step for k in range(11)]   # 11 column centres
    # vertical slots: 16 on the outer columns, parents centred on their two children
    slot = (bot_y - top_y) / 16.0
    yL = [[top_y + slot * (i + 0.5) for i in range(16)]]       # level 0 = R32 (16 ys)
    for _ in range(4):                                          # R16, QF, SF, F
        prev = yL[-1]
        yL.append([(prev[2 * i] + prev[2 * i + 1]) / 2 for i in range(len(prev) // 2)])
    champ_y = (yL[4][0] + yL[4][0])                            # placeholder, set below to true centre
    champ_y = (top_y + bot_y) / 2

    L = [rounds[0][:16], rounds[1][:8], rounds[2][:4], rounds[3][:2], rounds[4][:1]]
    R = [rounds[0][16:], rounds[1][8:], rounds[2][4:], rounds[3][2:], rounds[4][1:]]
    labels = ["R32", "R16", "QF", "SF", "FINAL", "CHAMPION", "FINAL", "SF", "QF", "R16", "R32"]
    for k, lab in enumerate(labels):
        d.text((col_cx[k], 232), lab, font=MC._font("segoeuib.ttf", 20), fill=INK3, anchor="mm")

    def _node(cx, cy, team, champ=False):
        if champ:
            bw, bh = 210, 96
            d.rounded_rectangle([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], 14,
                                fill=(30, 26, 54), outline=VIOL, width=4)
            if champ_flag:
                im.alpha_composite(champ_flag, (int(cx - 36), int(cy - 42)))
            d.text((cx, cy + 26), _disp(team), font=MC._font("segoeuib.ttf", 28), fill=INK, anchor="mm")
            MC._star(d, cx, int(cy - 46), 14, GOLD)
            return
        d.rounded_rectangle([cx - NW / 2, cy - NH / 2, cx + NW / 2, cy + NH / 2], 8,
                            fill=PANEL, outline=LINE, width=1)
        fg = flags.get(team)
        if fg:
            im.alpha_composite(fg, (int(cx - NW / 2 + 12), int(cy - 14)))
        d.text((cx - NW / 2 + 60, cy), WM.code(team), font=MC._font("segoeuib.ttf", 24), fill=INK, anchor="lm")

    def _connect(kc, kp, yc, yp, left=True):
        """Bracket connectors between child column kc and parent column kp."""
        for i, py in enumerate(yp):
            y1, y2 = yc[2 * i], yc[2 * i + 1]
            if left:
                cxr = col_cx[kc] + NW / 2
                pxl = col_cx[kp] - NW / 2
            else:
                cxr = col_cx[kc] - NW / 2
                pxl = col_cx[kp] + NW / 2
            spine = (cxr + pxl) / 2
            d.line([(cxr, y1), (spine, y1)], fill=LINE, width=1)
            d.line([(cxr, y2), (spine, y2)], fill=LINE, width=1)
            d.line([(spine, y1), (spine, y2)], fill=LINE, width=1)
            d.line([(spine, py), (pxl, py)], fill=LINE, width=1)

    # connectors (draw first, under the nodes)
    for k in range(4):                                         # L: R32->R16->QF->SF->F
        _connect(k, k + 1, yL[k], yL[k + 1], left=True)
    for k in range(4):                                         # R: mirror (cols 10..7 -> 6)
        _connect(10 - k, 9 - k, yL[k], yL[k + 1], left=False)
    d.line([(col_cx[4] + NW / 2, yL[4][0]), (col_cx[5] - 105, champ_y)], fill=LINE, width=1)
    d.line([(col_cx[6] - NW / 2, yL[4][0]), (col_cx[5] + 105, champ_y)], fill=LINE, width=1)

    # nodes
    cols_L = list(zip(range(5), L, yL))
    for k, teams, ys in cols_L:
        for t, y in zip(teams, ys):
            _node(col_cx[k], y, t)
    cols_R = list(zip(range(10, 5, -1), R, yL))
    for k, teams, ys in cols_R:
        for t, y in zip(teams, ys):
            _node(col_cx[k], y, t)
    if champ:
        _node(col_cx[5], champ_y, champ, champ=True)
        d.text((col_cx[5], champ_y + 66), f"🏆 {win.get(nz(champ), 0)*100:.0f}% to lift it",
               font=MC._font("seguisb.ttf", 21), fill=INK3, anchor="mm")

    fy = H - 72
    try:
        emb = Image.open(os.path.join(os.path.dirname(out), "wvm_mark.png")).convert("RGBA").resize((42, 42), Image.LANCZOS)
        im.alpha_composite(emb, (46, fy - 6))
    except OSError:
        pass
    d.text((98, fy - 4), "World vs Model", font=MC._font("segoeuib.ttf", 25), fill=INK)
    d.text((98, fy + 23), "mli3w.github.io/world-vs-model · a model projection, not certainty · research only, not gambling",
           font=MC._font("segoeui.ttf", 18), fill=INK3)
    im.convert("RGB").save(out, "PNG")
    print(f"[outcomemap] wrote {out}")


if __name__ == "__main__":
    build()
