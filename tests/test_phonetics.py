# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tests for the Cologne phonetics (Kölner Phonetik) used to match misheard German words."""

import pytest

from ttm_core.phonetics import cologne


@pytest.mark.parametrize("word, code", [
    # reference examples from the literature / Wikipedia
    ("Müller-Lüdenscheidt", "65752682"),
    ("Wikipedia", "3412"),
    ("Breschnew", "17863"),
])
def test_reference_values(word, code):
    assert cologne(word) == code


@pytest.mark.parametrize("heard, meant", [
    ("Richtig", "Rechteck"),
    ("Phase", "Fase"),
    ("Spiegel", "Spiegel"),
])
def test_misheard_words_share_the_code(heard, meant):
    assert cologne(heard) == cologne(meant)


@pytest.mark.parametrize("word, code", [
    ("Rechteck", "7424"),
    ("Fase", "38"),
    ("Straße", "8278"),        # ß is treated like s
    ("Öse", "08"),             # leading vowel keeps its 0
    ("Hand", "062"),           # leading h is ignored, the vowel counts
])
def test_details(word, code):
    assert cologne(word) == code


def test_different_words_differ():
    assert cologne("Kreis") != cologne("Linie")
    assert cologne("Tasche") != cologne("Fase")


def test_empty():
    assert cologne("") == ""
    assert cologne("123") == ""


# --- Metaphone (English) ---------------------------------------------------------------------------

from ttm_core.phonetics import PHONETICS, metaphone


@pytest.mark.parametrize("word, code", [
    ("Thompson", "0MPSN"),      # TH → 0 (theta), vowels after the first letter dropped
    ("knight", "NT"),           # silent K, GH
    ("Smith", "SM0"),           # TH → 0 (theta)
    ("phone", "FN"),            # PH → F
    ("chamfer", "XMFR"),        # CH → X
    ("science", "SNS"),         # SC before E/I/Y: C silent
    ("extrude", "EKSTRT"),      # X → KS, initial vowel kept
    ("judge", "JJ"),            # DGE → J
    ("sketch", "SKX"),          # TCH: T silent
    ("wrench", "RNX"),          # initial WR → R
    ("Xavier", "SFR"),          # initial X → S
    ("lamb", "LM"),             # final MB: B silent
])
def test_metaphone_values(word, code):
    assert metaphone(word) == code


@pytest.mark.parametrize("heard, meant", [
    ("Pat", "Pad"),
    ("shamfur", "chamfer"),
    ("poquet", "pocket"),
    ("filit", "fillet"),
    ("skech", "sketch"),
    ("Smyth", "Smith"),
])
def test_misheard_english_words_share_the_code(heard, meant):
    assert metaphone(heard) == metaphone(meant)


def test_different_english_words_differ():
    assert metaphone("pad") != metaphone("pocket")
    assert metaphone("circle") != metaphone("line")


def test_english_pack_uses_metaphone():
    assert PHONETICS.get("en") is metaphone
    assert PHONETICS.get("de") is cologne
