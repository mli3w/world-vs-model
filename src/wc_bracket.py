"""
wc_bracket.py - the REAL 2026 FIFA World Cup knockout bracket (official slot table)
==================================================================================
The 2026 finals have 48 teams in 12 groups (A-L). The top two of each group plus the eight
best third-placed teams advance to a 32-team knockout: Round of 32 -> R16 -> QF -> SF -> Final.

This module encodes FIFA's OFFICIAL slot table verbatim, as published in the tournament
regulations (Annex C) and mirrored by Wikipedia's "2026 FIFA World Cup knockout stage":

  * R32  : the 16 fixed Round-of-32 matches (#73-#88), each a pair of group slots, listed in
           bracket (top-to-bottom) order so adjacent pairs converge through R16 (#89-#96),
           QF (#97-#100), SF (#101-#102) to the Final (#104) as a clean binary tree.
  * THIRD_ASSIGN : the full 495-row contingency table that maps *which* eight groups' third-placed
           teams qualify -> which group fills each of the eight "winner-vs-third" slots. (495 = the
           number of ways to pick 8 qualifying thirds out of 12 groups.)

Nothing here is invented: the matchups are the published fixtures, not a model guess. What the
model supplies is only the *projected standings* poured into these fixed slots.

Research/education only.
"""

# The eight Round-of-32 matches in which a group WINNER plays a qualifying third, keyed by the
# winner's slot. THIRD_ASSIGN rows give the assigned third-group letter in exactly this column order.
COLS = ["1A", "1B", "1D", "1E", "1G", "1I", "1K", "1L"]

# Candidate third-place groups each winner can draw (for labels/tooltips) -- straight from the bracket.
CAND = {
    "1A": "CEFHI", "1B": "EFGIJ", "1D": "BEFIJ", "1E": "ABCDF",
    "1G": "AEHIJ", "1I": "CDFGH", "1K": "DEIJL", "1L": "EHIJK",
}

# Round of 32 in BRACKET ORDER (top half first, then bottom half). Each entry:
#   (match_no, slotA, slotB) where a slot is:
#     ("W", g)   -> winner of group g
#     ("R", g)   -> runner-up of group g
#     ("3", col) -> the qualifying third assigned to winner-slot `col` (resolved via THIRD_ASSIGN)
R32 = [
    (74, ("W", "E"), ("3", "1E")),   # top half (feeds Semifinal 1 / Match 101)
    (77, ("W", "I"), ("3", "1I")),
    (73, ("R", "A"), ("R", "B")),
    (75, ("W", "F"), ("R", "C")),
    (83, ("R", "K"), ("R", "L")),
    (84, ("W", "H"), ("R", "J")),
    (81, ("W", "D"), ("3", "1D")),
    (82, ("W", "G"), ("3", "1G")),
    (76, ("W", "C"), ("R", "F")),   # bottom half (feeds Semifinal 2 / Match 102)
    (78, ("R", "E"), ("R", "I")),
    (79, ("W", "A"), ("3", "1A")),
    (80, ("W", "L"), ("3", "1L")),
    (86, ("W", "J"), ("R", "H")),
    (88, ("R", "D"), ("R", "G")),
    (85, ("W", "B"), ("3", "1B")),
    (87, ("W", "K"), ("3", "1K")),
]

_THIRD_RAW = """\nABCDEFGH HGBCAFDE
ABCDEFGI CGBDAFEI
ABCDEFGJ CGBDAFEJ
ABCDEFGK CGBDAFEK
ABCDEFGL CGBDAFLE
ABCDEFHI HEBCAFDI
ABCDEFHJ HJBCAFDE
ABCDEFHK HEBCAFDK
ABCDEFHL HFBCADLE
ABCDEFIJ CJBDAFEI
ABCDEFIK CEBDAFIK
ABCDEFIL CEBDAFLI
ABCDEFJK CJBDAFEK
ABCDEFJL CJBDAFLE
ABCDEFKL CEBDAFLK
ABCDEGHI HGBCADEI
ABCDEGHJ HGBCADEJ
ABCDEGHK HGBCADEK
ABCDEGHL HGBCADLE
ABCDEGIJ EGBCADIJ
ABCDEGIK EGBCADIK
ABCDEGIL EGBCADLI
ABCDEGJK EGBCADJK
ABCDEGJL EGBCADLJ
ABCDEGKL EGBCADLK
ABCDEHIJ HJBCADEI
ABCDEHIK HEBCADIK
ABCDEHIL HEBCADLI
ABCDEHJK HJBCADEK
ABCDEHJL HJBCADLE
ABCDEHKL HEBCADLK
ABCDEIJK EJBCADIK
ABCDEIJL EJBCADLI
ABCDEIKL EIBCADLK
ABCDEJKL EJBCADLK
ABCDFGHI HGBCAFDI
ABCDFGHJ HGBCAFDJ
ABCDFGHK HGBCAFDK
ABCDFGHL CGBDAFLH
ABCDFGIJ CGBDAFIJ
ABCDFGIK CGBDAFIK
ABCDFGIL CGBDAFLI
ABCDFGJK CGBDAFJK
ABCDFGJL CGBDAFLJ
ABCDFGKL CGBDAFLK
ABCDFHIJ HJBCAFDI
ABCDFHIK HFBCADIK
ABCDFHIL HFBCADLI
ABCDFHJK HJBCAFDK
ABCDFHJL CJBDAFLH
ABCDFHKL HFBCADLK
ABCDFIJK CJBDAFIK
ABCDFIJL CJBDAFLI
ABCDFIKL CIBDAFLK
ABCDFJKL CJBDAFLK
ABCDGHIJ HGBCADIJ
ABCDGHIK HGBCADIK
ABCDGHIL HGBCADLI
ABCDGHJK HGBCADJK
ABCDGHJL HGBCADLJ
ABCDGHKL HGBCADLK
ABCDGIJK CJBDAGIK
ABCDGIJL CJBDAGLI
ABCDGIKL IGBCADLK
ABCDGJKL CJBDAGLK
ABCDHIJK HJBCADIK
ABCDHIJL HJBCADLI
ABCDHIKL HIBCADLK
ABCDHJKL HJBCADLK
ABCDIJKL IJBCADLK
ABCEFGHI HGBCAFEI
ABCEFGHJ HGBCAFEJ
ABCEFGHK HGBCAFEK
ABCEFGHL HGBCAFLE
ABCEFGIJ EGBCAFIJ
ABCEFGIK EGBCAFIK
ABCEFGIL EGBCAFLI
ABCEFGJK EGBCAFJK
ABCEFGJL EGBCAFLJ
ABCEFGKL EGBCAFLK
ABCEFHIJ HJBCAFEI
ABCEFHIK HEBCAFIK
ABCEFHIL HEBCAFLI
ABCEFHJK HJBCAFEK
ABCEFHJL HJBCAFLE
ABCEFHKL HEBCAFLK
ABCEFIJK EJBCAFIK
ABCEFIJL EJBCAFLI
ABCEFIKL EIBCAFLK
ABCEFJKL EJBCAFLK
ABCEGHIJ HJBCAGEI
ABCEGHIK EGBCAHIK
ABCEGHIL EGBCAHLI
ABCEGHJK HJBCAGEK
ABCEGHJL HJBCAGLE
ABCEGHKL EGBCAHLK
ABCEGIJK EJBCAGIK
ABCEGIJL EJBCAGLI
ABCEGIKL EGBAICLK
ABCEGJKL EJBCAGLK
ABCEHIJK EJBCAHIK
ABCEHIJL EJBCAHLI
ABCEHIKL EIBCAHLK
ABCEHJKL EJBCAHLK
ABCEIJKL EJBAICLK
ABCFGHIJ HGBCAFIJ
ABCFGHIK HGBCAFIK
ABCFGHIL HGBCAFLI
ABCFGHJK HGBCAFJK
ABCFGHJL HGBCAFLJ
ABCFGHKL HGBCAFLK
ABCFGIJK CJBFAGIK
ABCFGIJL CJBFAGLI
ABCFGIKL IGBCAFLK
ABCFGJKL CJBFAGLK
ABCFHIJK HJBCAFIK
ABCFHIJL HJBCAFLI
ABCFHIKL HIBCAFLK
ABCFHJKL HJBCAFLK
ABCFIJKL IJBCAFLK
ABCGHIJK HJBCAGIK
ABCGHIJL HJBCAGLI
ABCGHIKL IGBCAHLK
ABCGHJKL HJBCAGLK
ABCGIJKL IJBCAGLK
ABCHIJKL IJBCAHLK
ABDEFGHI HGBDAFEI
ABDEFGHJ HGBDAFEJ
ABDEFGHK HGBDAFEK
ABDEFGHL HGBDAFLE
ABDEFGIJ EGBDAFIJ
ABDEFGIK EGBDAFIK
ABDEFGIL EGBDAFLI
ABDEFGJK EGBDAFJK
ABDEFGJL EGBDAFLJ
ABDEFGKL EGBDAFLK
ABDEFHIJ HJBDAFEI
ABDEFHIK HEBDAFIK
ABDEFHIL HEBDAFLI
ABDEFHJK HJBDAFEK
ABDEFHJL HJBDAFLE
ABDEFHKL HEBDAFLK
ABDEFIJK EJBDAFIK
ABDEFIJL EJBDAFLI
ABDEFIKL EIBDAFLK
ABDEFJKL EJBDAFLK
ABDEGHIJ HJBDAGEI
ABDEGHIK EGBDAHIK
ABDEGHIL EGBDAHLI
ABDEGHJK HJBDAGEK
ABDEGHJL HJBDAGLE
ABDEGHKL EGBDAHLK
ABDEGIJK EJBDAGIK
ABDEGIJL EJBDAGLI
ABDEGIKL EGBAIDLK
ABDEGJKL EJBDAGLK
ABDEHIJK EJBDAHIK
ABDEHIJL EJBDAHLI
ABDEHIKL EIBDAHLK
ABDEHJKL EJBDAHLK
ABDEIJKL EJBAIDLK
ABDFGHIJ HGBDAFIJ
ABDFGHIK HGBDAFIK
ABDFGHIL HGBDAFLI
ABDFGHJK HGBDAFJK
ABDFGHJL HGBDAFLJ
ABDFGHKL HGBDAFLK
ABDFGIJK FJBDAGIK
ABDFGIJL FJBDAGLI
ABDFGIKL IGBDAFLK
ABDFGJKL FJBDAGLK
ABDFHIJK HJBDAFIK
ABDFHIJL HJBDAFLI
ABDFHIKL HIBDAFLK
ABDFHJKL HJBDAFLK
ABDFIJKL IJBDAFLK
ABDGHIJK HJBDAGIK
ABDGHIJL HJBDAGLI
ABDGHIKL IGBDAHLK
ABDGHJKL HJBDAGLK
ABDGIJKL IJBDAGLK
ABDHIJKL IJBDAHLK
ABEFGHIJ HJBFAGEI
ABEFGHIK EGBFAHIK
ABEFGHIL EGBFAHLI
ABEFGHJK HJBFAGEK
ABEFGHJL HJBFAGLE
ABEFGHKL EGBFAHLK
ABEFGIJK EJBFAGIK
ABEFGIJL EJBFAGLI
ABEFGIKL EGBAIFLK
ABEFGJKL EJBFAGLK
ABEFHIJK EJBFAHIK
ABEFHIJL EJBFAHLI
ABEFHIKL EIBFAHLK
ABEFHJKL EJBFAHLK
ABEFIJKL EJBAIFLK
ABEGHIJK EJBAHGIK
ABEGHIJL EJBAHGLI
ABEGHIKL EGBAIHLK
ABEGHJKL EJBAHGLK
ABEGIJKL EJBAIGLK
ABEHIJKL EJBAIHLK
ABFGHIJK HJBFAGIK
ABFGHIJL HJBFAGLI
ABFGHIKL HGBAIFLK
ABFGHJKL HJBFAGLK
ABFGIJKL IJBFAGLK
ABFHIJKL HJBAIFLK
ABGHIJKL HJBAIGLK
ACDEFGHI HGECAFDI
ACDEFGHJ HGJCAFDE
ACDEFGHK HGECAFDK
ACDEFGHL HGFCADLE
ACDEFGIJ CGJDAFEI
ACDEFGIK CGEDAFIK
ACDEFGIL CGEDAFLI
ACDEFGJK CGJDAFEK
ACDEFGJL CGJDAFLE
ACDEFGKL CGEDAFLK
ACDEFHIJ HJECAFDI
ACDEFHIK HEFCADIK
ACDEFHIL HEFCADLI
ACDEFHJK HJECAFDK
ACDEFHJL HJFCADLE
ACDEFHKL HEFCADLK
ACDEFIJK CJEDAFIK
ACDEFIJL CJEDAFLI
ACDEFIKL CEIDAFLK
ACDEFJKL CJEDAFLK
ACDEGHIJ HGJCADEI
ACDEGHIK HGECADIK
ACDEGHIL HGECADLI
ACDEGHJK HGJCADEK
ACDEGHJL HGJCADLE
ACDEGHKL HGECADLK
ACDEGIJK EGJCADIK
ACDEGIJL EGJCADLI
ACDEGIKL EGICADLK
ACDEGJKL EGJCADLK
ACDEHIJK HJECADIK
ACDEHIJL HJECADLI
ACDEHIKL HEICADLK
ACDEHJKL HJECADLK
ACDEIJKL EJICADLK
ACDFGHIJ HGJCAFDI
ACDFGHIK HGFCADIK
ACDFGHIL HGFCADLI
ACDFGHJK HGJCAFDK
ACDFGHJL CGJDAFLH
ACDFGHKL HGFCADLK
ACDFGIJK CGJDAFIK
ACDFGIJL CGJDAFLI
ACDFGIKL CGIDAFLK
ACDFGJKL CGJDAFLK
ACDFHIJK HJFCADIK
ACDFHIJL HJFCADLI
ACDFHIKL HFICADLK
ACDFHJKL HJFCADLK
ACDFIJKL CJIDAFLK
ACDGHIJK HGJCADIK
ACDGHIJL HGJCADLI
ACDGHIKL HGICADLK
ACDGHJKL HGJCADLK
ACDGIJKL IGJCADLK
ACDHIJKL HJICADLK
ACEFGHIJ HGJCAFEI
ACEFGHIK HGECAFIK
ACEFGHIL HGECAFLI
ACEFGHJK HGJCAFEK
ACEFGHJL HGJCAFLE
ACEFGHKL HGECAFLK
ACEFGIJK EGJCAFIK
ACEFGIJL EGJCAFLI
ACEFGIKL EGICAFLK
ACEFGJKL EGJCAFLK
ACEFHIJK HJECAFIK
ACEFHIJL HJECAFLI
ACEFHIKL HEICAFLK
ACEFHJKL HJECAFLK
ACEFIJKL EJICAFLK
ACEGHIJK EGJCAHIK
ACEGHIJL EGJCAHLI
ACEGHIKL EGICAHLK
ACEGHJKL EGJCAHLK
ACEGIJKL EJICAGLK
ACEHIJKL EJICAHLK
ACFGHIJK HGJCAFIK
ACFGHIJL HGJCAFLI
ACFGHIKL HGICAFLK
ACFGHJKL HGJCAFLK
ACFGIJKL IGJCAFLK
ACFHIJKL HJICAFLK
ACGHIJKL HJICAGLK
ADEFGHIJ HGJDAFEI
ADEFGHIK HGEDAFIK
ADEFGHIL HGEDAFLI
ADEFGHJK HGJDAFEK
ADEFGHJL HGJDAFLE
ADEFGHKL HGEDAFLK
ADEFGIJK EGJDAFIK
ADEFGIJL EGJDAFLI
ADEFGIKL EGIDAFLK
ADEFGJKL EGJDAFLK
ADEFHIJK HJEDAFIK
ADEFHIJL HJEDAFLI
ADEFHIKL HEIDAFLK
ADEFHJKL HJEDAFLK
ADEFIJKL EJIDAFLK
ADEGHIJK EGJDAHIK
ADEGHIJL EGJDAHLI
ADEGHIKL EGIDAHLK
ADEGHJKL EGJDAHLK
ADEGIJKL EJIDAGLK
ADEHIJKL EJIDAHLK
ADFGHIJK HGJDAFIK
ADFGHIJL HGJDAFLI
ADFGHIKL HGIDAFLK
ADFGHJKL HGJDAFLK
ADFGIJKL IGJDAFLK
ADFHIJKL HJIDAFLK
ADGHIJKL HJIDAGLK
AEFGHIJK EGJFAHIK
AEFGHIJL EGJFAHLI
AEFGHIKL EGIFAHLK
AEFGHJKL EGJFAHLK
AEFGIJKL EJIFAGLK
AEFHIJKL EJIFAHLK
AEGHIJKL EJIAHGLK
AFGHIJKL HJIFAGLK
BCDEFGHI CGBDHFEI
BCDEFGHJ HGBCJFDE
BCDEFGHK CGBDHFEK
BCDEFGHL CGBDHFLE
BCDEFGIJ CGBDJFEI
BCDEFGIK CGBDEFIK
BCDEFGIL CGBDEFLI
BCDEFGJK CGBDJFEK
BCDEFGJL CGBDJFLE
BCDEFGKL CGBDEFLK
BCDEFHIJ CJBDHFEI
BCDEFHIK CEBDHFIK
BCDEFHIL CEBDHFLI
BCDEFHJK CJBDHFEK
BCDEFHJL CJBDHFLE
BCDEFHKL CEBDHFLK
BCDEFIJK CJBDEFIK
BCDEFIJL CJBDEFLI
BCDEFIKL CEBDIFLK
BCDEFJKL CJBDEFLK
BCDEGHIJ HGBCJDEI
BCDEGHIK EGBCHDIK
BCDEGHIL EGBCHDLI
BCDEGHJK HGBCJDEK
BCDEGHJL HGBCJDLE
BCDEGHKL EGBCHDLK
BCDEGIJK EGBCJDIK
BCDEGIJL EGBCJDLI
BCDEGIKL EGBCIDLK
BCDEGJKL EGBCJDLK
BCDEHIJK EJBCHDIK
BCDEHIJL EJBCHDLI
BCDEHIKL EIBCHDLK
BCDEHJKL EJBCHDLK
BCDEIJKL EJBCIDLK
BCDFGHIJ HGBCJFDI
BCDFGHIK CGBDHFIK
BCDFGHIL CGBDHFLI
BCDFGHJK HGBCJFDK
BCDFGHJL CGBDHFLJ
BCDFGHKL CGBDHFLK
BCDFGIJK CGBDJFIK
BCDFGIJL CGBDJFLI
BCDFGIKL CGBDIFLK
BCDFGJKL CGBDJFLK
BCDFHIJK CJBDHFIK
BCDFHIJL CJBDHFLI
BCDFHIKL CIBDHFLK
BCDFHJKL CJBDHFLK
BCDFIJKL CJBDIFLK
BCDGHIJK HGBCJDIK
BCDGHIJL HGBCJDLI
BCDGHIKL HGBCIDLK
BCDGHJKL HGBCJDLK
BCDGIJKL IGBCJDLK
BCDHIJKL HJBCIDLK
BCEFGHIJ HGBCJFEI
BCEFGHIK EGBCHFIK
BCEFGHIL EGBCHFLI
BCEFGHJK HGBCJFEK
BCEFGHJL HGBCJFLE
BCEFGHKL EGBCHFLK
BCEFGIJK EGBCJFIK
BCEFGIJL EGBCJFLI
BCEFGIKL EGBCIFLK
BCEFGJKL EGBCJFLK
BCEFHIJK EJBCHFIK
BCEFHIJL EJBCHFLI
BCEFHIKL EIBCHFLK
BCEFHJKL EJBCHFLK
BCEFIJKL EJBCIFLK
BCEGHIJK EJBCHGIK
BCEGHIJL EJBCHGLI
BCEGHIKL EGBCIHLK
BCEGHJKL EJBCHGLK
BCEGIJKL EJBCIGLK
BCEHIJKL EJBCIHLK
BCFGHIJK HGBCJFIK
BCFGHIJL HGBCJFLI
BCFGHIKL HGBCIFLK
BCFGHJKL HGBCJFLK
BCFGIJKL IGBCJFLK
BCFHIJKL HJBCIFLK
BCGHIJKL HJBCIGLK
BDEFGHIJ HGBDJFEI
BDEFGHIK EGBDHFIK
BDEFGHIL EGBDHFLI
BDEFGHJK HGBDJFEK
BDEFGHJL HGBDJFLE
BDEFGHKL EGBDHFLK
BDEFGIJK EGBDJFIK
BDEFGIJL EGBDJFLI
BDEFGIKL EGBDIFLK
BDEFGJKL EGBDJFLK
BDEFHIJK EJBDHFIK
BDEFHIJL EJBDHFLI
BDEFHIKL EIBDHFLK
BDEFHJKL EJBDHFLK
BDEFIJKL EJBDIFLK
BDEGHIJK EJBDHGIK
BDEGHIJL EJBDHGLI
BDEGHIKL EGBDIHLK
BDEGHJKL EJBDHGLK
BDEGIJKL EJBDIGLK
BDEHIJKL EJBDIHLK
BDFGHIJK HGBDJFIK
BDFGHIJL HGBDJFLI
BDFGHIKL HGBDIFLK
BDFGHJKL HGBDJFLK
BDFGIJKL IGBDJFLK
BDFHIJKL HJBDIFLK
BDGHIJKL HJBDIGLK
BEFGHIJK EJBFHGIK
BEFGHIJL EJBFHGLI
BEFGHIKL EGBFIHLK
BEFGHJKL EJBFHGLK
BEFGIJKL EJBFIGLK
BEFHIJKL EJBFIHLK
BEGHIJKL EJIBHGLK
BFGHIJKL HJBFIGLK
CDEFGHIJ CGJDHFEI
CDEFGHIK CGEDHFIK
CDEFGHIL CGEDHFLI
CDEFGHJK CGJDHFEK
CDEFGHJL CGJDHFLE
CDEFGHKL CGEDHFLK
CDEFGIJK CGEDJFIK
CDEFGIJL CGEDJFLI
CDEFGIKL CGEDIFLK
CDEFGJKL CGEDJFLK
CDEFHIJK CJEDHFIK
CDEFHIJL CJEDHFLI
CDEFHIKL CEIDHFLK
CDEFHJKL CJEDHFLK
CDEFIJKL CJEDIFLK
CDEGHIJK EGJCHDIK
CDEGHIJL EGJCHDLI
CDEGHIKL EGICHDLK
CDEGHJKL EGJCHDLK
CDEGIJKL EGICJDLK
CDEHIJKL EJICHDLK
CDFGHIJK CGJDHFIK
CDFGHIJL CGJDHFLI
CDFGHIKL CGIDHFLK
CDFGHJKL CGJDHFLK
CDFGIJKL CGIDJFLK
CDFHIJKL CJIDHFLK
CDGHIJKL HGICJDLK
CEFGHIJK EGJCHFIK
CEFGHIJL EGJCHFLI
CEFGHIKL EGICHFLK
CEFGHJKL EGJCHFLK
CEFGIJKL EGICJFLK
CEFHIJKL EJICHFLK
CEGHIJKL EJICHGLK
CFGHIJKL HGICJFLK
DEFGHIJK EGJDHFIK
DEFGHIJL EGJDHFLI
DEFGHIKL EGIDHFLK
DEFGHJKL EGJDHFLK
DEFGIJKL EGIDJFLK
DEFHIJKL EJIDHFLK
DEGHIJKL EJIDHGLK
DFGHIJKL HGIDJFLK
EFGHIJKL EJIFHGLK
"""

THIRD_ASSIGN = dict(line.split() for line in _THIRD_RAW.splitlines() if line.strip())
assert len(THIRD_ASSIGN) == 495, len(THIRD_ASSIGN)


def qualifying_thirds(standings, strength):
    """The eight groups whose third-placed team qualifies, ranked by model strength (best 8).

    `standings`: {group_letter: [team1st, team2nd, team3rd, team4th]} (projected order).
    `strength`:  callable team_name -> sortable strength (higher = stronger).
    Returns a sorted 8-letter key for THIRD_ASSIGN.
    """
    thirds = [(g, row[2]) for g, row in standings.items() if len(row) >= 3]
    thirds.sort(key=lambda gt: strength(gt[1]), reverse=True)
    return "".join(sorted(g for g, _ in thirds[:8]))


def resolve(standings, strength, played=None, third_groups=None):
    """Pour standings into the official slots and converge the bracket.

    Returns a dict:
      r32   : list of 16 (match_no, teamA, teamB) in bracket order
      rounds: [r32_teams(32), r16(16), qf(8), sf(4), final(2), champ(1)] -- flat top-to-bottom lists
      champ : the projected champion (the surviving finalist) or None

    By default advancement is "stronger team wins" by `strength` -- a most-likely projection.
    Two knobs make the SAME bracket reflect a tournament already in progress:

      `played`: {frozenset({teamA, teamB}): winner} of knockout ties that have actually been
                decided. Those matchups advance the RECORDED winner instead of the stronger side,
                so the map shows results as they come in and drops eliminated teams from the path.
                A tie that isn't in `played` (not yet played, or a draw whose shoot-out winner we
                don't store) falls back to `strength`. This fixes the deterministic bracket
                STRUCTURE; the per-team reach probabilities are conditioned separately once the
                group stage is decided (worldcup_fundamental._conditioned_forecast).

      `third_groups`: an iterable of the eight group letters whose third-placed team qualifies.
                Pin this to the REAL best-eight once the group stage is decided; when omitted the
                eight are chosen by `strength` (the pre-tournament projection).
    """
    played = played or {}
    # A team recorded as losing a knockout tie is OUT of the tournament -- it must never advance
    # again, even where an incomplete feed can't reproduce the exact matchup (e.g. its conqueror's
    # own earlier result is missing). This is a soft constraint on top of the exact-winner map.
    eliminated = set()
    for pair, w in played.items():
        if w in pair:
            eliminated |= set(pair) - {w}
    key = "".join(sorted(third_groups)) if third_groups is not None \
        else qualifying_thirds(standings, strength)
    assign = THIRD_ASSIGN.get(key)

    def team_for(slot):
        kind, who = slot
        if kind == "W":
            return standings[who][0]
        if kind == "R":
            return standings[who][1]
        if not assign:
            return None
        grp = assign[COLS.index(who)]
        return standings[grp][2]

    def advance(a, b):
        if a is None and b is None:
            return None
        if a is None:
            return b
        if b is None:
            return a
        w = played.get(frozenset((a, b)))
        if w in (a, b):                      # a recorded result trumps the model's projection
            return w
        if a in eliminated and b not in eliminated:   # a is already out (lost elsewhere)
            return b
        if b in eliminated and a not in eliminated:
            return a
        return a if strength(a) >= strength(b) else b

    r32 = [(m, team_for(a), team_for(b)) for (m, a, b) in R32]
    cur = []
    for _, a, b in r32:
        cur += [a, b]
    rounds = [cur]
    while len(cur) > 1:
        cur = [advance(a, b) for a, b in zip(cur[0::2], cur[1::2])]
        rounds.append(cur)
    champ = rounds[-1][0] if rounds[-1] else None
    return {"r32": r32, "rounds": rounds, "champ": champ}


# --------------------------------------------------------------------------------------------------
# Live state from results -- shared by the board and the share-image generators so every "outcome
# map" pours the SAME real standings into the slots and honours the SAME knockout results.
# --------------------------------------------------------------------------------------------------
def _group_key(table, team):
    s = table.get(team, {"Pts": 0, "GF": 0, "GA": 0})
    return (-s["Pts"], -(s["GF"] - s["GA"]), -s["GF"])   # points, then goal difference, then goals for


def group_table(groups, results):
    """Actual group standings from played GROUP results. Returns
    (ranked, table): `ranked` = {group_letter: [teams ordered by Pts, GD, GF]},
    `table` = {team: {"Pts","GF","GA","P"}}. Mirrors the group-stage tiebreak used by the sim."""
    table = {t: {"Pts": 0, "GF": 0, "GA": 0, "P": 0} for ts in groups.values() for t in ts}
    team_group = {t: g for g, ts in groups.items() for t in ts}
    for r in results or []:
        if r.get("stage", "group") != "group":
            continue
        a, b = r["a"], r["b"]
        if a not in team_group or b not in team_group:
            continue
        ga, gb = int(r["ga"]), int(r["gb"])
        for t, gf, ga_ in ((a, ga, gb), (b, gb, ga)):
            table[t]["P"] += 1
            table[t]["GF"] += gf
            table[t]["GA"] += ga_
        if ga > gb:
            table[a]["Pts"] += 3
        elif gb > ga:
            table[b]["Pts"] += 3
        else:
            table[a]["Pts"] += 1
            table[b]["Pts"] += 1
    ranked = {g: sorted(ts, key=lambda t: _group_key(table, t)) for g, ts in groups.items()}
    return ranked, table


def best_third_groups(ranked, table, n=8):
    """The `n` group letters whose third-placed team qualifies as a best-third, by real Pts/GD/GF."""
    thirds = [(g, row[2]) for g, row in ranked.items() if len(row) >= 3]
    thirds.sort(key=lambda gt: _group_key(table, gt[1]))
    return set(g for g, _ in thirds[:n])


def ko_winners(results):
    """{frozenset({a, b}): winner} for every DECIDED knockout tie (stage == 'ko'). A decisive
    scoreline gives the winner directly; a level scoreline means the tie went to a shoot-out, so
    the advancer is read from the result's optional `adv` field (recorded by feed_result --adv).
    A drawn tie with no `adv` is skipped, so resolve() falls back to model strength for it. Feed
    this to resolve(played=...)."""
    out = {}
    for r in results or []:
        if r.get("stage") != "ko":
            continue
        a, b, ga, gb = r["a"], r["b"], int(r["ga"]), int(r["gb"])
        if ga > gb:
            out[frozenset((a, b))] = a
        elif gb > ga:
            out[frozenset((a, b))] = b
        elif r.get("adv") in (a, b):             # drawn tie decided on penalties
            out[frozenset((a, b))] = r["adv"]
    return out


def groups_complete(groups, results):
    """True once every group match has been played (so the R32 line-up is real, not projected)."""
    need = sum(len(ts) * (len(ts) - 1) // 2 for ts in groups.values())
    got = sum(1 for r in (results or []) if r.get("stage", "group") == "group")
    return got >= need
