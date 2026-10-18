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
