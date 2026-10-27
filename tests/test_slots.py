# SPDX-License-Identifier: LGPL-2.1-or-later
"""Sentence patterns of an application with slots filled from its lists of names (DESIGN.md 7).

The examples are a file manager's ("Lege das in Eingangsrechnungen ab"): the application sends
its patterns and the names of its places; a slot named like a list takes one of its names.
"""

import pytest

from ttm_core.objects import find_entity
from ttm_core.params import Grammar, parse
from ttm_core.sequence import plan_utterance

ROLES = [
    {"id": "04_Finanz/Ausgaben", "phrases": ["Ausgaben", "Finanz Ausgaben", "Eingangsrechnungen"]},
    {"id": "04_Finanz/Einnahmen", "phrases": ["Einnahmen", "Finanz Einnahmen", "Ausgangsrechnungen"]},
    {"id": "05_Rechtliches", "phrases": ["Rechtliches", "Verträge"]},
]
PROJECTS = [{"id": "Haus", "phrases": ["Haus"]}, {"id": "Gartenhaus", "phrases": ["Gartenhaus"]}]
PATTERNS = [
    ["file", r"(?:lege|leg)\s+(?:{pronoun}\s+)?(?:in|unter|zu)\s+(?:den\s+|die\s+|das\s+)?(?P<role>.+?)\s+ab"],
    ["copy", r"kopiere\s+(?:{pronoun}\s+)?(?:nach|in|zu)\s+(?:den\s+|die\s+|das\s+)?(?P<role>.+)"],
    ["move_to_project", r"verschiebe\s+(?:{pronoun}\s+)?(?:ins|in\s+das)\s+projekt\s+(?P<project>.+)"],
    ["note", r"notiere\s+(?P<text>.+)"],
]
GRAMMAR = Grammar(own=PATTERNS, entities={"role": ROLES, "project": PROJECTS})


@pytest.mark.parametrize("spoken, role", [
    ("Ausgaben", "04_Finanz/Ausgaben"),
    ("die Ausgaben", "04_Finanz/Ausgaben"),
    ("Eingangsrechnungen", "04_Finanz/Ausgaben"),          # a synonym of the application
    ("Finanz Ausgaben", "04_Finanz/Ausgaben"),
    ("Ausgabe", "04_Finanz/Ausgaben"),                     # misheard, close in spelling
    ("Einnamen", "04_Finanz/Einnahmen"),                   # same sound
    ("Verträge", "05_Rechtliches"),
])
def test_find_entity(spoken, role):
    assert find_entity(spoken, ROLES, "de") == role


@pytest.mark.parametrize("spoken", ["Bananen", "", "die"])
def test_find_no_entity(spoken):
    assert find_entity(spoken, ROLES, "de") is None


def test_find_entity_not_between_two_alike():
    alike = [{"id": "a", "phrases": ["Rechnungen 2025"]}, {"id": "b", "phrases": ["Rechnungen 2026"]}]
    assert find_entity("Rechnungen", alike, "de") is None


@pytest.mark.parametrize("text, command, args", [
    ("Lege das in Eingangsrechnungen ab", "file", {"role": "04_Finanz/Ausgaben"}),
    ("Leg die in Ausgaben ab", "file", {"role": "04_Finanz/Ausgaben"}),
    ("lege das unter Verträge ab.", "file", {"role": "05_Rechtliches"}),
    ("Kopiere das nach Einnahmen", "copy", {"role": "04_Finanz/Einnahmen"}),
    ("Verschiebe das ins Projekt Gartenhaus", "move_to_project", {"project": "Gartenhaus"}),
    ("Notiere Milch kaufen", "note", {"text": "Milch kaufen"}),     # a slot without a list: free text
])
def test_patterns_of_the_application(text, command, args):
    assert parse(text, "de", GRAMMAR) == (command, args)


def test_unknown_name_is_no_command():
    assert parse("Lege das in Bananen ab", "de", GRAMMAR) is None


def test_slot_with_an_empty_list_is_no_command():
    """No roles yet: nothing to file into."""
    assert parse("Lege das in Ausgaben ab", "de", Grammar(own=PATTERNS, entities={"role": [], "project": []})) is None


def test_language_patterns_still_apply():
    assert parse("Den nennen wir Bodenplatte", "de", GRAMMAR) == ("ui:rename", {"label": "Bodenplatte"})


def test_learned_patterns_as_before():
    learned = {"ui:rename": ["nenndas {label}"]}
    assert parse("Nenndas Bodenplatte", "de", learned) == ("ui:rename", {"label": "Bodenplatte"})
    assert parse("Nenndas Bodenplatte", "de", Grammar(learned=learned)) == ("ui:rename", {"label": "Bodenplatte"})


def test_a_sequence_of_application_commands():
    steps = plan_utterance("Lege das in Ausgaben ab und kopiere es nach Verträge", [], "de", GRAMMAR)
    assert [(d.kind, d.command, d.args) for d, _ in steps] == [
        ("execute", "file", {"role": "04_Finanz/Ausgaben"}),
        ("execute", "copy", {"role": "05_Rechtliches"}),
    ]


def test_context_changing_is_a_property_of_the_candidate():
    """A step that changes the context ("workbench:" in FreeCAD, another view elsewhere) is not
    offered while a tool waits for values: it would leave the tool."""
    from ttm_core.sequence import step
    candidates = [
        {"id": "view:finance", "level": "global", "phrases": ["Finanzen"], "active": True, "changes_context": True},
        {"id": "sort", "level": "global", "phrases": ["Sortieren"], "active": True},
    ]
    assert step(["Finanzen"], candidates, "de")[0].command == "view:finance"
    assert step(["Finanzen"], candidates, "de", tool_running=True)[0].command != "view:finance"
    assert step(["Sortieren"], candidates, "de", tool_running=True)[0].command == "sort"
