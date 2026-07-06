"""Tests for the official 2026 knockout slot table (src/wc_bracket.py)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import wc_bracket as B  # noqa: E402


def test_third_table_is_the_full_495():
    assert len(B.THIRD_ASSIGN) == 495
    for key, val in B.THIRD_ASSIGN.items():
        assert len(key) == 8 and len(val) == 8
        assert key == "".join(sorted(key))          # canonical, deduped key
        assert len(set(key)) == 8 and len(set(val)) == 8
        assert set(val) <= set(key)                  # every assigned third actually qualified


def test_each_third_respects_its_slot_candidate_set():
    for key, val in B.THIRD_ASSIGN.items():
        for col, grp in zip(B.COLS, val):
            assert grp in B.CAND[col]                # slot can only draw its eligible groups


def test_r32_is_sixteen_matches_over_distinct_slots():
    assert len(B.R32) == 16
    winners = sorted(w for _, a, b in B.R32 for (k, w) in (a, b) if k == "W")
    runners = sorted(w for _, a, b in B.R32 for (k, w) in (a, b) if k == "R")
    thirds = sorted(w for _, a, b in B.R32 for (k, w) in (a, b) if k == "3")
    assert winners == list("ABCDEFGHIJKL")           # all 12 group winners appear once
    assert runners == list("ABCDEFGHIJKL")           # all 12 runners-up appear once
    assert thirds == sorted(B.COLS)                  # the 8 winner-vs-third slots


def test_resolve_pours_distinct_teams_and_crowns_a_champion():
    groups = {g: [f"{g}1", f"{g}2", f"{g}3", f"{g}4"] for g in "ABCDEFGHIJKL"}
    # strength: group winners strongest, then runners-up, then thirds; later letters stronger
    strength = lambda t: ord(t[0]) * 10 + (4 - int(t[1]))
    br = B.resolve(groups, strength)
    assert [len(r) for r in br["rounds"]] == [32, 16, 8, 4, 2, 1]
    r32_teams = [t for _, a, b in br["r32"] for t in (a, b)]
    assert len(set(r32_teams)) == 32                 # nobody is slotted twice
    assert br["champ"] is not None

    key = B.qualifying_thirds(groups, strength)
    assign = B.THIRD_ASSIGN[key]
    slot = {m: (a, b) for m, a, b in B.R32}
    for m, ta, tb in br["r32"]:
        for s, team in zip(slot[m], (ta, tb)):
            if s[0] == "3":
                grp = assign[B.COLS.index(s[1])]
                assert team == f"{grp}3"             # the right group's third filled the slot


def test_resolve_honours_a_played_result_over_model_strength():
    groups = {g: [f"{g}1", f"{g}2", f"{g}3", f"{g}4"] for g in "ABCDEFGHIJKL"}
    strength = lambda t: ord(t[0]) * 10 + (4 - int(t[1]))
    base = B.resolve(groups, strength)
    m0, ta, tb = base["r32"][0]                      # the top Round-of-32 match
    fav = ta if strength(ta) >= strength(tb) else tb
    dog = tb if fav == ta else ta
    # Record the UNDERDOG as the actual winner of that tie; it must now advance to the R16 slot.
    br = B.resolve(groups, strength, played={frozenset((ta, tb)): dog})
    assert base["rounds"][1][0] == fav               # projection alone crowns the favourite
    assert br["rounds"][1][0] == dog                 # a recorded result overrides the projection
    # A stray winner not actually in the tie is ignored (falls back to strength).
    stray = B.resolve(groups, strength, played={frozenset((ta, tb)): "Z9"})
    assert stray["rounds"][1][0] == fav


def test_resolve_accepts_explicit_qualifying_thirds():
    groups = {g: [f"{g}1", f"{g}2", f"{g}3", f"{g}4"] for g in "ABCDEFGHIJKL"}
    strength = lambda t: ord(t[0]) * 10 + (4 - int(t[1]))
    thirds = set("ABDEGIKL")                          # a valid 8-group key present in THIRD_ASSIGN
    br = B.resolve(groups, strength, third_groups=thirds)
    assign = B.THIRD_ASSIGN["".join(sorted(thirds))]
    slot = {m: (a, b) for m, a, b in B.R32}
    for m, ta, tb in br["r32"]:
        for s, team in zip(slot[m], (ta, tb)):
            if s[0] == "3":
                assert team == f"{assign[B.COLS.index(s[1])]}3"


def test_group_table_and_helpers_from_results():
    groups = {"A": ["Alpha", "Bravo", "Charlie", "Delta"]}
    results = [
        {"a": "Alpha", "b": "Bravo", "ga": 3, "gb": 0, "stage": "group"},
        {"a": "Charlie", "b": "Delta", "ga": 1, "gb": 1, "stage": "group"},
        {"a": "Alpha", "b": "Charlie", "ga": 2, "gb": 0, "stage": "group"},
        {"a": "Bravo", "b": "Delta", "ga": 1, "gb": 0, "stage": "group"},
        {"a": "Alpha", "b": "Delta", "ga": 0, "gb": 0, "stage": "group"},
        {"a": "Bravo", "b": "Charlie", "ga": 2, "gb": 1, "stage": "group"},
    ]
    ranked, table = B.group_table(groups, results)
    assert ranked["A"][0] == "Alpha"                 # 7 pts, tops the group
    assert table["Alpha"]["Pts"] == 7 and table["Alpha"]["P"] == 3
    assert B.groups_complete(groups, results)        # all C(4,2)=6 matches present
    assert not B.groups_complete(groups, results[:5])
    assert B.best_third_groups(ranked, table, n=1) == {"A"}
    ko = [{"a": "Alpha", "b": "Bravo", "ga": 0, "gb": 1, "stage": "ko"},
          {"a": "Charlie", "b": "Delta", "ga": 1, "gb": 1, "stage": "ko"}]  # draw -> omitted
    assert B.ko_winners(ko) == {frozenset(("Alpha", "Bravo")): "Bravo"}
