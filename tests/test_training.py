# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tests for training: learning how the recognizer hears the user (DESIGN.md 8.7)."""

import json
import os

from ttm_core.context import build_candidates
from ttm_core.decision import decide
from ttm_core.training import classify, learn

DATA = os.path.join(os.path.dirname(__file__), "data")
with open(os.path.join(DATA, "context_fc114_partdesign_de.json"), encoding="utf-8") as f:
    PART_DESIGN = json.load(f)

XY, XZ, YZ = ("ui:choose:{}-Ebene (Basis-Ebene)".format(p) for p in ("XY", "XZ", "YZ"))


def plane_dialog(heard=None):
    heard = heard or {}
    return PART_DESIGN + [
        {"id": cmd, "level": "dialog", "phrases": [cmd.split(":")[2].split(" (")[0]], "foreign": [],
         "heard": heard.get(cmd, []), "active": True, "description": ""} for cmd in (XY, XZ, YZ)]


# --- classify a recording ------------------------------------------------------------------

def test_already_understood():
    assert classify("XY-Ebene", XY, plane_dialog(), "de") == "ok"


def test_misheard_form_is_learned():
    assert classify("X-Upsilom-Ebene", XY, plane_dialog(), "de") == "learn"


def test_form_of_another_command_is_a_conflict():
    """Saying XY but hearing "XZ-Ebene" must not teach that XZ means XY."""
    assert classify("XZ-Ebene", XY, plane_dialog(), "de") == "conflict"


def test_nothing_heard():
    assert classify("", XY, plane_dialog(), "de") == "empty"


# --- learned forms in decisions --------------------------------------------------------------

def test_learned_form_and_its_sound_alikes_are_understood():
    candidates = plane_dialog({XY: ["X-Upsilom-Ebene"]})
    for text in ("X-Upsilom-Ebene", "X-Upsalon-Ebene", "Mach eine Skizze in der X-Upsalon-Ebene"):
        d = decide(text, candidates, "de")
        assert (d.kind, d.command) == ("execute", XY), text


def test_learned_forms_stay_apart_from_phrases():
    cands = build_candidates({"tb": ["PartDesign_Pad"]}, {"PartDesign_Pad": ["Aufpolsterung"]}, {},
                             heard={"PartDesign_Pad": ["Extrahiere"]})
    assert cands[0]["phrases"] == ["Aufpolsterung"]          # phrases become hints for Whisper
    assert cands[0]["heard"] == ["Extrahiere"]               # heard forms don't


# --- saving -------------------------------------------------------------------------------------

def test_learn_stores_heard_forms_once():
    custom = {}
    learn(custom, XY, heard=["X-Upsilom-Ebene", "x-upsilom-ebene", "Öx Y-Lebenen"])
    learn(custom, XY, heard=["X-Upsilom-Ebene"])
    assert custom == {"_heard": {XY: ["X-Upsilom-Ebene", "Öx Y-Lebenen"]}}


def test_learn_stores_a_typed_sentence_as_phrase():
    custom = {"PartDesign_Pad": ["hochziehen"]}
    learn(custom, "PartDesign_Pad", typed="Zieh das hoch")
    assert custom["PartDesign_Pad"] == ["hochziehen", "Zieh das hoch"]


# --- options of the question menu (DESIGN.md 8.8) ----------------------------------------------

from ttm_core.training import options


def test_options_are_the_likely_commands():
    alternatives = [(XY, 0.79), (YZ, 0.7), (XZ, 0.4)]
    assert options(alternatives, plane_dialog(), min_score=0.6) == [(XY, True), (YZ, True)]


def test_options_show_inactive_commands_as_such():
    candidates = [dict(c, active=c["id"] != "PartDesign_Pocket") for c in PART_DESIGN]
    assert options([("PartDesign_Pocket", 0.9)], candidates) == [("PartDesign_Pocket", False)]


def test_no_options_for_weak_guesses():
    assert options([(XY, 0.45)], plane_dialog(), min_score=0.6) == []


def test_options_are_limited_and_unique():
    alternatives = [(XY, 0.9), (XY, 0.8), (YZ, 0.8), (XZ, 0.8), ("PartDesign_Pad", 0.8)]
    assert [o for o, _ in options(alternatives, plane_dialog(), limit=3)] == [XY, YZ, XZ]


def test_options_unknown_in_the_situation_are_left_out():
    assert options([("Gone_Command", 0.9)], plane_dialog()) == []


def test_unlearn_removes_heard_forms_and_empty_entries():
    from ttm_core.training import unlearn
    custom = {"_heard": {XY: ["X-Upsilom-Ebene", "Öx Y-Lebenen"], YZ: ["Öpsel"]}}
    unlearn(custom, XY, ["x-upsilom-ebene"])
    unlearn(custom, YZ, ["Öpsel"])
    assert custom == {"_heard": {XY: ["Öx Y-Lebenen"]}}


def test_learn_stores_patterns_once():
    custom = {}
    learn(custom, "ui:rename", patterns=["nenndas {label}", "nenndas {label}"])
    assert custom == {"_patterns": {"ui:rename": ["nenndas {label}"]}}


def test_unlearn_removes_patterns():
    from ttm_core.training import unlearn
    custom = {"_patterns": {"ui:rename": ["nenndas {label}"]}}
    unlearn(custom, "ui:rename", [], patterns=["nenndas {label}"])
    assert custom == {"_patterns": {}}


# --- vocabulary editor (DESIGN.md 8.9) -------------------------------------------------------------

from ttm_core.training import add_phrase, entries, move_entry, remove_entry

PACK = {"PartDesign_Pad": ["Polster", "extrudieren"], "Std_Undo": ["rückgängig"]}
CUSTOM = {"PartDesign_Pad": ["hochziehen"],
          "_heard": {XY: ["X-Upsilom-Ebene"], "Std_Undo": ["Rück gängig"]},
          "_patterns": {"ui:rename": ["nenndas {label}"]}}


def test_entries_by_command_and_source():
    found = entries(PACK, CUSTOM)
    assert ("PartDesign_Pad", "pack", "Polster") in found
    assert ("PartDesign_Pad", "phrase", "hochziehen") in found
    assert (XY, "heard", "X-Upsilom-Ebene") in found
    assert ("ui:rename", "pattern", "nenndas {label}") in found
    assert found == sorted(found, key=lambda e: e[0])          # grouped by command


def test_remove_user_entries():
    custom = json_copy(CUSTOM)
    remove_entry(custom, "PartDesign_Pad", "phrase", "hochziehen")
    remove_entry(custom, XY, "heard", "X-Upsilom-Ebene")
    remove_entry(custom, "ui:rename", "pattern", "nenndas {label}")
    assert custom == {"_heard": {"Std_Undo": ["Rück gängig"]}, "_patterns": {}}


def test_pack_entries_cannot_be_removed():
    import pytest
    with pytest.raises(ValueError):
        remove_entry(json_copy(CUSTOM), "PartDesign_Pad", "pack", "Polster")


def test_move_a_wrongly_learned_form():
    custom = json_copy(CUSTOM)
    move_entry(custom, "heard", "X-Upsilom-Ebene", XY, YZ)
    assert custom["_heard"] == {"Std_Undo": ["Rück gängig"], YZ: ["X-Upsilom-Ebene"]}


def test_add_phrase():
    custom = json_copy(CUSTOM)
    add_phrase(custom, "Std_Undo", "mach das weg")
    add_phrase(custom, "Std_Undo", "Mach das weg")              # once
    assert custom["Std_Undo"] == ["mach das weg"]


def json_copy(data):
    import json
    return json.loads(json.dumps(data))
