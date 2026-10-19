"""Decisions in contexts recorded from FreeCAD 1.1.4 (German), with all their real labels and
help texts. Small hand-made candidate lists miss the coincidences of 80 real commands.

Recorded with talktome.context.collect(): a new document, Part workbench; and a new document
with a body, PartDesign workbench.
"""

import json
import os

import pytest

from ttm_core.clauses import split_clauses
from ttm_core.decision import decide
from ttm_core.sequence import next_step

DATA = os.path.join(os.path.dirname(__file__), "data")


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


PART = load("context_fc114_part_de.json")
PART_DESIGN = load("context_fc114_partdesign_de.json")


def steps(text, candidates):
    """Steps of an utterance, all in one context: [(kind, command, clauses consumed)]."""
    clauses, result = split_clauses(text, "de"), []
    while clauses:
        d, n = next_step(clauses, candidates, "de")
        result.append((d.kind, d.command, n))
        clauses = clauses[n:]
        if d.kind == "not_understood":
            break
    return result


@pytest.mark.parametrize("text, command", [
    ("Extrudiere das und ziehe es vom bestehenden Körper ab", "PartDesign_Pocket"),
    ("Extrudiere die Skizze und füge sie dem Körper hinzu", "PartDesign_Pad"),
    ("Drehe die Skizze um die Achse und zieh das ab", "PartDesign_Groove"),
    ("Mach die vorherige Aktion rückgängig", "Std_Undo"),
    ("Versieh die Kanten mit einer Verrundung", "PartDesign_Fillet"),
    ("Mach eine Fase", "PartDesign_Chamfer"),
    ("Speichere das Dokument", "Std_Save"),
])
def test_part_design_commands(text, command):
    d = decide(text, PART_DESIGN, "de")
    assert (d.kind, d.command) == ("execute", command)


@pytest.mark.parametrize("text", [
    "Das sieht schon ganz gut aus, finde ich",
    "Ich trinke jetzt einen Kaffee",
    "und zwar von hier nach hier",
])
def test_talk_is_ignored(text):
    assert decide(text, PART, "de").kind == "ignore"
    assert decide(text, PART_DESIGN, "de").kind == "ignore"


def test_workbench_switch_in_part():
    assert steps("Wechsle bitte zum PartDesigner", PART) == [("execute", "workbench:PartDesignWorkbench", 1)]


def test_body_does_not_swallow_the_naming_clause():
    """ "Den nennen wir Bodenplatte" adds nothing to "erstelle einen neuen Körper"."""
    first = steps("erstelle einen neuen Körper, den nennen wir Bodenplatte", PART_DESIGN)[0]
    assert first == ("execute", "PartDesign_Body", 1)


def test_sketch_is_not_undo():
    """ "machen" is rare among the help texts (only Undo); one rare word must not decide."""
    d = decide("und mach eine Skizze in der XY-Ebene", PART_DESIGN, "de")
    assert not (d.kind == "execute" and d.command == "Std_Undo")


def test_plane_is_not_open():
    """ "Ebene" sounds like the English label "Open" in German phonetics."""
    d = decide("und mach eine Skizze in der XY-Ebene", PART_DESIGN, "de")
    assert d.command != "Std_Open"


VOCAB = load(os.path.join("..", "..", "vocab", "de.json"))
MIC_OFF = {"id": "ui:mic_off", "level": "global", "phrases": VOCAB["ui:mic_off"], "foreign": [],
           "active": True, "description": ""}


@pytest.mark.parametrize("text", [
    "Ok kurze Pause", "Kurze Pause", "Stoppe mal die Aufnahme", "Mach mal das Mikro zu",
    "Höre nicht mehr zu", "Mikro aus", "Mikrofon aus", "Hör auf zuzuhören",
])
def test_microphone_off(text):
    d = decide(text, PART_DESIGN + [MIC_OFF], "de")
    assert (d.kind, d.command) == ("execute", "ui:mic_off")
