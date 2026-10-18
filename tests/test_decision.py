"""Tests for deciding whether to execute, reject or ignore an utterance (DESIGN.md 7 and 9.3)."""

from ttm_core.decision import decide


def cand(id_, phrases, level="workbench", active=True):
    return {"id": id_, "phrases": phrases, "level": level, "active": active}


CANDIDATES = [
    cand("Sketcher_CreateRectangle", ["Rechteck"], "edit"),
    cand("Sketcher_CreateCircle", ["Kreis"], "edit"),
    cand("Sketcher_LeaveSketch", ["Schließe den Sketch", "Sketch schließen"], "edit"),
    cand("Sketcher_NewSketch", ["Neuer Sketch", "Sketch öffnen"]),
    cand("PartDesign_Pad", ["Aufpolsterung", "extrudieren"], active=False),
    cand("Std_Save", ["Speichern"], "global"),
    cand("Std_ViewRear", ["Rückansicht"], "global"),
]


def test_execute_clear_command():
    d = decide("Zeichne ein Rechteck", CANDIDATES, language="de")
    assert d.kind == "execute"
    assert d.command == "Sketcher_CreateRectangle"


def test_execute_by_sound():
    assert decide("Zeichen ein Richtig", CANDIDATES, language="de").command == "Sketcher_CreateRectangle"


def test_inactive_command_is_not_executed():
    d = decide("extrudieren", CANDIDATES, language="de")
    assert d.kind == "not_understood"
    assert d.reason == "inactive"
    assert d.command == "PartDesign_Pad"


def test_higher_level_wins_on_equal_score():
    candidates = [cand("Draft_Rectangle", ["Rechteck"], "global"),
                  cand("Sketcher_CreateRectangle", ["Rechteck"], "edit")]
    d = decide("Rechteck", candidates, language="de")
    assert d.kind == "execute"
    assert d.command == "Sketcher_CreateRectangle"


def test_ambiguous_on_same_level_is_rejected():
    candidates = [cand("A_Rect", ["Rechteck"]), cand("B_Rect", ["Rechteck"])]
    d = decide("Rechteck", candidates, language="de")
    assert d.kind == "not_understood"
    assert d.reason == "ambiguous"
    assert {a[0] for a in d.alternatives[:2]} == {"A_Rect", "B_Rect"}


def test_short_unknown_utterance_gives_error():
    d = decide("Klaus", CANDIDATES, language="de")
    assert d.kind == "not_understood"
    assert d.reason == "no_match"


def test_long_unrelated_sentence_is_ignored():
    d = decide("Ich gehe jetzt erst mal einen Kaffee trinken", CANDIDATES, language="de")
    assert d.kind == "ignore"


def test_empty_text_is_ignored():
    assert decide("", CANDIDATES, language="de").kind == "ignore"
    assert decide(" ... ", CANDIDATES, language="de").kind == "ignore"


FOLLOW_UP = CANDIDATES + [cand("Std_ViewRear2", ["von hinten"], "global")]


def test_narration_while_drawing_is_ignored():
    # "Zeichne ein Rechteck ... und zwar von hier (click) nach hier (click)"
    assert decide("und zwar von hier", FOLLOW_UP, language="de").kind == "ignore"
    assert decide("nach hier", FOLLOW_UP, language="de").kind == "ignore"
    assert decide("so, genau, da", FOLLOW_UP, language="de").kind == "ignore"


def test_filler_only_is_ignored_with_reason():
    assert decide("und dann hier", FOLLOW_UP, language="de").reason == "filler"


def test_command_with_narration_in_one_sentence():
    d = decide("Zeichne ein Rechteck und zwar von hier", FOLLOW_UP, language="de")
    assert d.kind == "execute"
    assert d.command == "Sketcher_CreateRectangle"


def test_fillers_still_count_inside_phrases():
    assert decide("von hinten", FOLLOW_UP, language="de").command == "Std_ViewRear2"


def test_alternatives_are_sorted():
    d = decide("Rechteck", CANDIDATES, language="de")
    scores = [s for _, s in d.alternatives]
    assert scores == sorted(scores, reverse=True)
    assert len(d.alternatives) <= 3


def test_same_command_twice_is_not_ambiguous():
    candidates = [cand("Std_Save", ["Speichern"], "global"), cand("Std_Save", ["sichern"], "workbench")]
    assert decide("Speichern", candidates, language="de").kind == "execute"
