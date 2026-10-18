"""Tests for the first, vocabulary-based matching stage (DESIGN.md section 7, stage 1)."""

from ttm_core.matching import match

COMMANDS = {
    "Sketcher_CreateRectangle": ["Rechteck", "Viereck"],
    "Sketcher_CreateCircle": ["Kreis"],
    "Sketcher_NewSketch": ["Neuer Sketch", "Öffne den Sketch", "Sketch öffnen"],
    "Sketcher_LeaveSketch": ["Schließe den Sketch", "Sketch schließen"],
}


def test_exact_phrase():
    assert match("Kreis", COMMANDS) == ("Sketcher_CreateCircle", 1.0)


def test_phrase_inside_sentence():
    cmd, score = match("Zeichne ein Rechteck!", COMMANDS)
    assert cmd == "Sketcher_CreateRectangle"
    assert score >= 0.9


def test_small_recognition_error_still_matches():
    assert match("Kreiß", COMMANDS)[0] == "Sketcher_CreateCircle"


def test_more_specific_phrase_wins():
    assert match("Schließe den Sketch", COMMANDS)[0] == "Sketcher_LeaveSketch"
    assert match("öffne den Sketch bitte", COMMANDS)[0] == "Sketcher_NewSketch"


def test_unrelated_sentence_matches_nothing():
    cmd, score = match("Wie spät ist es eigentlich?", COMMANDS)
    assert cmd is None
    assert score < 0.75


def test_empty_text():
    assert match("", COMMANDS) == (None, 0.0)
    assert match("  ...  ", COMMANDS) == (None, 0.0)


def test_threshold():
    assert match("Kreiß", COMMANDS, threshold=0.99)[0] is None
