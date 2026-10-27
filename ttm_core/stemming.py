# SPDX-License-Identifier: LGPL-2.1-or-later
"""Crude word stemmers: enough to make inflected forms of one word equal, not linguistics.

    "Extrudiere", "extrudiert", "extrudieren" → "extrud"
    "füge", "fügt"                            → "fug"
"""

from ttm_core.langpack import View

GERMAN_FOLD = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})
GERMAN_SUFFIXES = ("ungen", "ieren", "ierst", "iert", "iere", "ung",
                   "en", "er", "es", "em", "st", "et", "t", "e", "s", "n")
MIN_STEM = 3


def stem_de(word):
    word = word.lower().translate(GERMAN_FOLD)
    for suffix in GERMAN_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= MIN_STEM:
            return word[:-len(suffix)]
    return word


ENGLISH_SUFFIXES = ("ations", "ation", "ingly", "ings", "ing", "edly", "ed", "ies", "es", "ly", "s")


def stem_en(word):
    """"extrudes", "extruded", "extrude" → "extrud"."""
    word = word.lower()
    for suffix in ENGLISH_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= MIN_STEM:
            word = word[:-len(suffix)] + ("y" if suffix == "ies" else "")
            break
    if word.endswith("e") and len(word) > MIN_STEM + 1:
        word = word[:-1]
    return word


ALGORITHMS = {"german": stem_de, "english": stem_en}

# language → stemming function, as named in the language pack.
STEMMERS = View("stemmer", convert=ALGORITHMS.get)
