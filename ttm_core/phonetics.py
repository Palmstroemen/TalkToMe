# SPDX-License-Identifier: LGPL-2.1-or-later
"""Phonetic codes for matching misheard words (DESIGN.md, section 7).

German uses the Cologne phonetics, English Metaphone; a language pack names its algorithm.
Without one, sound-alike matching is skipped and only spelling counts.
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


VOWELS_EN = set("AEIOU")
FRONT = set("EIY")                     # vowels that soften C and G


@lru_cache(maxsize=50_000)
def metaphone(word):
    """Metaphone (Lawrence Philips, 1990) for English: "Pad" and "Pat" both become "PT",
    "chamfer" and "shamfur" "XMFR". "0" stands for TH."""
    w = "".join(c for c in word.upper() if "A" <= c <= "Z")
    if not w:
        return ""
    if w[:2] in ("AE", "GN", "KN", "PN", "WR"):
        w = w[1:]
    if w[0] == "X":
        w = "S" + w[1:]
    elif w[:2] == "WH":
        w = "W" + w[2:]

    def at(i):
        return w[i] if 0 <= i < len(w) else ""

    code = []
    for i, c in enumerate(w):
        if c == at(i - 1) and c != "C":
            continue                           # double letters count once
        nxt, prev = at(i + 1), at(i - 1)
        if c in VOWELS_EN:
            if i == 0:
                code.append(c)
        elif c == "B":
            if not (prev == "M" and i == len(w) - 1):
                code.append("B")
        elif c == "C":
            if nxt == "I" and at(i + 2) == "A" or nxt == "H":
                code.append("K" if prev == "S" else "X")
            elif nxt in FRONT:
                if prev != "S":
                    code.append("S")
            else:
                code.append("K")
        elif c == "D":
            code.append("J" if nxt == "G" and at(i + 2) in FRONT else "T")
        elif c == "G":
            if nxt == "H" and at(i + 2) and at(i + 2) not in VOWELS_EN:
                continue                       # "night": silent
            if nxt == "N" and (i + 2 == len(w) or w[i + 2:i + 4] == "ED"):
                continue                       # "sign", "signed"
            if prev == "D" and nxt in FRONT:
                continue                       # "judge": the D gave J already
            code.append("J" if nxt in FRONT and prev != "G" else "K")
        elif c == "H":
            if prev in VOWELS_EN and nxt not in VOWELS_EN or prev in ("C", "S", "P", "T", "G"):
                continue
            code.append("H")
        elif c == "K":
            if prev != "C":
                code.append("K")
        elif c == "P":
            code.append("F" if nxt == "H" else "P")
        elif c == "Q":
            code.append("K")
        elif c == "S":
            if nxt == "H" or nxt == "I" and at(i + 2) in ("O", "A"):
                code.append("X")
            else:
                code.append("S")
        elif c == "T":
            if nxt == "I" and at(i + 2) in ("O", "A"):
                code.append("X")
            elif nxt == "H":
                code.append("0")
            elif not (nxt == "C" and at(i + 2) == "H"):
                code.append("T")
        elif c == "V":
            code.append("F")
        elif c in ("W", "Y"):
            if nxt in VOWELS_EN:
                code.append(c)
        elif c == "X":
            code.append("KS")
        elif c == "Z":
            code.append("S")
        else:                                  # F, J, L, M, N, R
            code.append(c)
    return "".join(code)


ALGORITHMS = {"cologne": cologne, "metaphone": metaphone}

# language → phonetic function, as named in the language pack; None: compare spelling only.
PHONETICS = View("phonetics", convert=ALGORITHMS.get)
