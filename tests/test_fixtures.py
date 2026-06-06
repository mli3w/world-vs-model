"""Group draw positions and the matchday template must match FIFA's official 2026 schedule.

Ground truth: the per-group standings tables ("2026 FIFA World Cup Group A".."L") and FIFA's
"Schedule by group" (MD1 1v2 & 3v4, MD2 1v3 & 4v2, MD3 4v1 & 2v3). Anchored by the known opener,
Mexico (A1) v South Africa (A2) on June 11.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import worldcup_markets as WM          # noqa: E402
import worldcup_board as B             # noqa: E402

# Official within-group slot order (FIFA 3-letter codes), position 1/2/3/4.
OFFICIAL = {
    "A": ["MEX", "RSA", "KOR", "CZE"], "B": ["CAN", "BIH", "QAT", "SUI"],
    "C": ["BRA", "MAR", "HAI", "SCO"], "D": ["USA", "PAR", "AUS", "TUR"],
    "E": ["GER", "CUW", "CIV", "ECU"], "F": ["NED", "JPN", "SWE", "TUN"],
    "G": ["BEL", "EGY", "IRN", "NZL"], "H": ["ESP", "CPV", "KSA", "URU"],
    "I": ["FRA", "SEN", "IRQ", "NOR"], "J": ["ARG", "ALG", "AUT", "JOR"],
    "K": ["POR", "COD", "UZB", "COL"], "L": ["ENG", "CRO", "GHA", "PAN"],
}


def test_group_slot_order_matches_official_draw():
    for g, teams in WM.WL.GROUPS_2026.items():
        assert [WM.code(t).upper() for t in teams] == OFFICIAL[g], g


def test_matchday_template_is_fifas():
    # MD1: 1v2, 3v4 | MD2: 1v3, 4v2 | MD3: 4v1, 2v3  (0-indexed)
    assert B._RR_MATCHDAYS == [[(0, 1), (2, 3)], [(0, 2), (3, 1)], [(3, 0), (1, 2)]]


def test_opening_match_is_mexico_v_south_africa():
    a = WM.WL.GROUPS_2026["A"]
    (i, j), _ = B._RR_MATCHDAYS[0]          # MD1, first pairing
    assert {a[i], a[j]} == {"Mexico", "South Africa"}
