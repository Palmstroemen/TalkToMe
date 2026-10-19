"""English: decisions in contexts recorded from FreeCAD 1.1.4 with English user interface.

The same code as for German, only the language pack differs (lang/en/). Recorded like the German
fixtures: a new document in Part, and one with a body in PartDesign.
"""

import json
import os

import pytest

from ttm_core.clauses import split_clauses
from ttm_core.decision import decide
from ttm_core.description import terms
from ttm_core.params import parse
from ttm_core.sequence import next_step

DATA = os.path.join(os.path.dirname(__file__), "data")


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


PART = load("context_fc114_part_en.json")
PART_DESIGN = load("context_fc114_partdesign_en.json")


def steps(text, candidates):
    clauses, result = split_clauses(text, "en"), []
    while clauses:
        d, n = next_step(clauses, candidates, "en")
        result.append((d.kind, d.command))
        clauses = clauses[n:]
        if d.kind == "not_understood":
            break
    return result


@pytest.mark.parametrize("text, command", [
    ("Pad", "PartDesign_Pad"),
    ("Make a fillet", "PartDesign_Fillet"),
    ("Chamfer", "PartDesign_Chamfer"),
    ("Save the document", "Std_Save"),
    ("Undo that", "Std_Undo"),
    ("Create a new body", "PartDesign_Body"),
    ("New sketch", "PartDesign_CompSketches"),
    ("Pad it 12 mm", "PartDesign_Pad"),                         # parameters don't count
])
def test_commands_by_name(text, command):
    d = decide(text, PART_DESIGN, "en")
    assert (d.kind, d.command) == ("execute", command)


@pytest.mark.parametrize("text, command", [
    ("Extrude this and remove it from the body", "PartDesign_Pocket"),
    ("Extrude the sketch and add it to the body", "PartDesign_Pad"),
    ("Undo the previous action", "Std_Undo"),
])
def test_commands_by_help_text(text, command):
    d = decide(text, PART_DESIGN, "en")
    assert (d.kind, d.command) == ("execute", command), d


def test_stems():
    assert terms("extrudes", "en") == terms("extrude", "en") == terms("extruded", "en")
    assert terms("removes", "en") == terms("remove", "en")


@pytest.mark.parametrize("text", [
    "I think this already looks quite good",
    "Let me get a coffee first",
    "so from here to there",
])
def test_talk_is_ignored(text):
    assert decide(text, PART_DESIGN, "en").kind == "ignore"


def test_workbench_switch():
    d = decide("Switch to Part Design", PART, "en")
    assert (d.kind, d.command) == ("execute", "workbench:PartDesignWorkbench")


def test_sequence():
    assert steps("Create a new body, call it base plate, and then a new sketch", PART_DESIGN) == [
        ("execute", "PartDesign_Body"), ("execute", "ui:rename"), ("execute", "PartDesign_CompSketches")]


@pytest.mark.parametrize("text, args", [
    ("Call it base plate", {"label": "Base plate"}),
    ("Let's call it lid", {"label": "Lid"}),
    ("Name it Bracket", {"label": "Bracket"}),
    ("Rename it to base plate", {"label": "Base plate"}),
    ("Please rename body 2 to base plate", {"label": "Base plate", "target": "body 2"}),
])
def test_rename(text, args):
    assert parse(text, "en") == ("ui:rename", args)


@pytest.mark.parametrize("text, n", [("the second one", 2), ("number two", 2), ("three", 3), ("first", 1)])
def test_pick(text, n):
    assert parse(text, "en") == ("ui:pick", {"pick": n})


@pytest.mark.parametrize("text", ["Microphone off", "Stop listening", "Take a short break", "Mic off"])
def test_microphone_off(text):
    vocab = load(os.path.join("..", "..", "lang", "en", "vocab.json"))
    mic_off = {"id": "ui:mic_off", "level": "global", "phrases": vocab["ui:mic_off"], "foreign": [],
               "active": True, "description": ""}
    d = decide(text, PART_DESIGN + [mic_off], "en")
    assert (d.kind, d.command) == ("execute", "ui:mic_off")
