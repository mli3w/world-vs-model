"""Tests for the nested-ladder structural signals (src/worldcup_markets.py) — data-free."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
WM = pytest.importorskip("worldcup_markets")
WL = pytest.importorskip("worldcup_live")


def test_every_field_team_has_a_continent():
    missing = [t for t in WL.FIELD if WL._norm(t) not in WM.TEAM_CONTINENT]
    assert missing == [], f"teams missing a continent: {missing}"
    assert len(WM.TEAM_CONTINENT) == 48


def test_level_sums_overround():
    ladder = {"win": {"a": 0.6, "b": 0.5}, "reach_F": {}, "reach_SF": {},
              "reach_QF": {}, "advance": {}}
    L = WM.level_sums(ladder)["win"]
    assert L["slots"] == 1 and abs(L["sum"] - 1.1) < 1e-9
    assert abs(L["overround_pct"] - 10.0) < 1e-6


def test_nested_scan_flags_impossible_ordering():
    # team 'a' priced to WIN (0.35) more than to REACH THE FINAL (0.30): impossible
    ladder = {"advance": {"a": 0.9}, "reach_QF": {"a": 0.5}, "reach_SF": {"a": 0.4},
              "reach_F": {"a": 0.30}, "win": {"a": 0.35}}
    v = WM.nested_scan(ladder, tol=0.005)
    assert any(t == "a" and sh == "reach_F" and dp == "win" for t, sh, dp, *_ in v)
    ok = {"advance": {"a": 0.9}, "reach_QF": {"a": 0.5}, "reach_SF": {"a": 0.4},
          "reach_F": {"a": 0.30}, "win": {"a": 0.20}}
    assert WM.nested_scan(ok, tol=0.005) == []


def test_team_info_and_flag_images_cover_the_field():
    # every field team has reference info (iso, rank, titles) and a flag image.
    for t in WL.FIELD:
        iso, rank, titles = WM.info(t)
        assert iso and isinstance(rank, int) and isinstance(titles, int)
    # flag_img returns a real <img> at a valid flagcdn size, with the emoji as alt.
    img = WM.flag_img("Brazil")
    assert "flagcdn.com/20x15/br.png" in img and "srcset=" in img and 'alt="🇧🇷"' in img
    assert WM.info("Brazil")[2] == 5 and WM.info("Germany")[2] == 4   # World Cup titles


def test_book_spans_levels_and_signs_edges():
    ladder = {"win": {"fav": 0.40, "dog": 0.02}, "reach_F": {}, "reach_SF": {},
              "reach_QF": {}, "advance": {}}
    rows = WM.book(ladder, power=1.3)
    assert {r["team"] for r in rows} == {"fav", "dog"}
    by = {r["team"]: r["edge"] for r in rows}
    assert by["fav"] > 0 > by["dog"]                      # power inflates favorite, deflates longshot


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeSession:
    """Returns one canned Gamma /events payload, ignoring url/params."""
    def __init__(self, payload):
        self._payload = payload

    def get(self, *a, **k):
        return _FakeResp(self._payload)


def test_fetch_event_prices_keeps_resolved_zero_outcomes():
    # A resolved event: one team eliminated (YES 0), one clinched (YES 1), one live (~0.5),
    # and one never-traded market with no quote at all. The eliminated 0 must be KEPT (so a
    # short marks to max profit instead of vanishing); only the no-data market is dropped.
    payload = [{"markets": [
        {"groupItemTitle": "Tunisia", "outcomePrices": "[\"0\", \"1\"]"},      # eliminated -> 0
        {"groupItemTitle": "Argentina", "outcomePrices": "[\"1\", \"0\"]"},    # clinched -> 1
        {"groupItemTitle": "Spain", "outcomePrices": "[\"0.52\", \"0.48\"]"},  # live
        {"groupItemTitle": "Nowhere", "lastTradePrice": None},                 # no quote -> drop
    ]}]
    out = WM.fetch_event_prices("any-slug", session=_FakeSession(payload))
    assert out[WL._norm("Tunisia")] == 0.0          # the bug: this used to be dropped
    assert out[WL._norm("Argentina")] == 1.0
    assert abs(out[WL._norm("Spain")] - 0.52) < 1e-9
    assert WL._norm("Nowhere") not in out           # genuine no-data is still dropped


def test_downsample_keeps_endpoints_and_caps_length():
    s = [i / 100 for i in range(100)]                     # 0.00 .. 0.99
    out = WM._downsample(s, 24)
    assert len(out) == 24 and out[0] == s[0] and out[-1] == round(s[-1], 4)
    assert WM._downsample([0.1, 0.2, 0.3], 24) == [0.1, 0.2, 0.3]   # shorter-than-k passes through
