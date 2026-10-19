"""Crude word stemmers: enough to make inflected forms of one word equal, not linguistics.

    "Extrudiere", "extrudiert", "extrudieren" → "extrud"
    "füge", "fügt"                            → "fug"
"""

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


STEMMERS = {"de": stem_de}
