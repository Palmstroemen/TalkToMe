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


# --- learned patterns (DESIGN.md 8.7) ----------------------------------------------------------

from ttm_core.params import make_template

LEARNED = {"ui:rename": ["nenndas {label}", "gip im den namen {label}"]}


@pytest.mark.parametrize("heard, name, template", [
    ("Nenndas Bodenplatte.", "Bodenplatte", "nenndas {label}"),
    ("Den nennen wir mal Boden Platte", "Boden Platte", "den nennen wir mal {label}"),
    ("Bodenplatte soll er heissen", "bodenplatte", "{label} soll er heissen"),
])
def test_template_from_heard_sentence(heard, name, template):
    assert make_template(heard, name, "de") == template


@pytest.mark.parametrize("heard, name", [
    ("Nenndas Bodenplatte", "Deckel"),          # name not in the sentence
    ("Bodenplatte", "Bodenplatte"),             # nothing but the name
    ("Nenndas Bodenplatte", ""),
])
def test_no_template(heard, name):
    assert make_template(heard, name, "de") is None


@pytest.mark.parametrize("text, label", [
    ("Nenndas Deckel", "Deckel"),
    ("nenndas linker Halter", "Linker Halter"),
    ("Nendas Deckel", "Deckel"),                # misheard a bit differently: similar spelling
    ("Gib ihm den Namen Deckel", "Deckel"),     # built-in pattern still first
    ("Gip im den Namen Deckel", "Deckel"),
])
def test_learned_pattern(text, label):
    assert parse(text, "de", LEARNED) == ("ui:rename", {"label": label})


@pytest.mark.parametrize("text", ["Deckel", "Fase", "Mach eine Fase", "nenndas"])
def test_learned_pattern_needs_its_fixed_part_and_a_label(text):
    assert parse(text, "de", LEARNED) is None


# --- rename with a named target --------------------------------------------------------------

@pytest.mark.parametrize("text, target, label", [
    ("Benenne doch bitte den Körper2 in Grundplatte um", "Körper2", "Grundplatte"),
    ("Benenne Skizze001 um in Deckel", "Skizze001", "Deckel"),
    ("Benenne den Körper zwei in Grundplatte um.", "Körper zwei", "Grundplatte"),
    ("Benenne die Bodenplatte um zu Deckplatte", "Bodenplatte", "Deckplatte"),
])
def test_rename_with_target(text, target, label):
    assert parse(text, "de") == ("ui:rename", {"label": label, "target": target})


def test_rename_with_pronoun_has_no_target():
    assert parse("Benenne ihn um in Grundkörper", "de") == ("ui:rename", {"label": "Grundkörper"})
