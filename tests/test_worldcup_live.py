"""Tests for the World Cup glue (src/worldcup_live.py) — data-free (no network/cache)."""
import os
import sys

import pytest

np = pytest.importorskip("numpy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
L = pytest.importorskip("worldcup_live")


def test_groups_are_12x4_unique_48():
    assert len(L.GROUPS_2026) == 12
    assert all(len(v) == 4 for v in L.GROUPS_2026.values())
    assert len(L.FIELD) == 48 and len(set(L.FIELD)) == 48


def test_norm_aliases_match_market_spellings():
    assert L._norm("Türkiye") == L._norm("Turkiye")
    assert L._norm("DR Congo") == L._norm("Congo DR")
    assert L._norm("Bosnia-Herzegovina") == L._norm("Bosnia Herzegovina")
    assert L._norm("Curaçao") == L._norm("Curacao")


def test_ratings_from_probs_monotone():
    import worldcup_sim as W
    r = W.ratings_from_probs({"strong": 0.30, "mid": 0.05, "weak": 0.005})
    assert r["strong"] > r["mid"] > r["weak"]


def test_model_substitution_is_negative_and_favorites_first():
    probs = {t: p for t, p in zip(L.FIELD, np.linspace(0.2, 0.001, len(L.FIELD)))}
    s = L.model_substitution(probs, top=5)
    assert all(r < 0 for _, _, r in s)                 # substitution is negative
    top_pair = set(s[0][:2])
    assert top_pair == {L.FIELD[0], L.FIELD[1]}         # two biggest favorites compete most
