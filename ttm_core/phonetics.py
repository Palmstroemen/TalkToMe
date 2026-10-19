"""Phonetic codes for matching misheard words (DESIGN.md, section 7).

Only German is supported so far (Cologne phonetics). Other languages need their own
algorithm, e.g. Metaphone for English; without one, sound-alike matching is skipped.
"""

from functools import lru_cache

from ttm_core.langpack import View

VOWELS = set("aeijouyäöü")


@lru_cache(maxsize=50_000)
def cologne(word):
    """Kölner Phonetik: "Rechteck" and "Richtig" both become "7424"."""
    w = [c for c in word.lower().replace("ß", "s") if c.isalpha()]
    codes = []
    for i, c in enumerate(w):
        prev = w[i - 1] if i > 0 else ""
        nxt = w[i + 1] if i + 1 < len(w) else ""
        if c in VOWELS:
            code = "0"
        elif c == "h":
            code = ""
        elif c == "b":
            code = "1"
        elif c == "p":
            code = "3" if nxt == "h" else "1"
        elif c in "dt":
            code = "8" if nxt and nxt in "csz" else "2"
        elif c in "fvw":
            code = "3"
        elif c in "gkq":
            code = "4"
        elif c == "c":
            if i == 0:
                code = "4" if nxt and nxt in "ahkloqrux" else "8"
            else:
                code = "4" if nxt and nxt in "ahkoqux" and prev not in "sz" else "8"
        elif c == "x":
            code = "8" if prev and prev in "ckq" else "48"
        elif c == "l":
            code = "5"
        elif c in "mn":
            code = "6"
        elif c == "r":
            code = "7"
        elif c in "sz":
            code = "8"
        else:
            code = ""
        codes.append(code)

    collapsed = ""
    for digit in "".join(codes):
        if not collapsed or collapsed[-1] != digit:
            collapsed += digit
    if not collapsed:
        return ""
    return collapsed[0] + collapsed[1:].replace("0", "")


ALGORITHMS = {"cologne": cologne}

# language → phonetic function, as named in the language pack; None: compare spelling only.
PHONETICS = View("phonetics", convert=ALGORITHMS.get)
