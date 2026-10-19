"""Tests for commands with free-text parameters, recognized by sentence patterns (DESIGN.md 7)."""

import pytest

from ttm_core.params import parse


@pytest.mark.parametrize("text, name", [
    ("Den nennen wir Bodenplatte", "Bodenplatte"),
    ("den nennen wir Bodenplatte.", "Bodenplatte"),
    ("und den nennen wir mal Bodenplatte", "Bodenplatte"),
    ("Nenne ihn Deckel", "Deckel"),
    ("Nenn das Halter links", "Halter links"),
    ("Benenne ihn um in Grundkörper", "Grundkörper"),
    ("Umbenennen in Platte", "Platte"),
    ("Der soll Bodenplatte heißen", "Bodenplatte"),
    ("Das heißt Bodenplatte", "Bodenplatte"),
    ("Gib ihm den Namen Bodenplatte", "Bodenplatte"),
    ("Name Bodenplatte", "Bodenplatte"),
    ("den nennen wir bodenplatte bitte", "Bodenplatte"),
])
def test_rename(text, name):
    assert parse(text, "de") == ("ui:rename", {"label": name})


@pytest.mark.parametrize("text", [
    "Rechteck",
    "Wie nennen wir das",              # the "name" would be a pronoun
    "Das heißt also",
    "Wechsle zu Part Design",
    "",
])
def test_no_rename(text):
    assert parse(text, "de") is None


def test_unknown_language():
    assert parse("Den nennen wir Bodenplatte", "xx") is None


# --- picking an entry of the question menu ---------------------------------------------------

@pytest.mark.parametrize("text, n", [
    ("eins", 1), ("Die Erste", 1), ("Nummer zwei", 2), ("die zweite.", 2), ("2", 2), ("drei", 3), ("den dritten", 3),
])
def test_pick(text, n):
    assert parse(text, "de") == ("ui:pick", {"pick": n})


@pytest.mark.parametrize("text", ["Fase 2 mm", "zwei Rechtecke", "die Skizze"])
def test_no_pick(text):
    assert parse(text, "de") is None or parse(text, "de")[0] != "ui:pick"
