"""Tests for the first, vocabulary-based matching stage (DESIGN.md section 7, stage 1)."""

from ttm_core.matching import hotwords, match

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


# --- sound-alike matching (German, Cologne phonetics) -----------------------------

DE = dict(language="de")
CAD = dict(COMMANDS, PartDesign_Chamfer=["Fase"], PartDesign_Pocket=["Tasche"])


def test_misheard_word_matches_by_sound():
    assert match("Zeichen ein Richtig", CAD, **DE)[0] == "Sketcher_CreateRectangle"


def test_homophone_with_parameters():
    assert match("Phase 2 mm", CAD, **DE)[0] == "PartDesign_Chamfer"
    assert match("Phase zwei Millimeter", CAD, **DE)[0] == "PartDesign_Chamfer"


def test_parameters_do_not_lower_the_score():
    assert match("Tasche 5 mm", CAD, **DE) == ("PartDesign_Pocket", 1.0)


def test_short_sound_code_needs_the_whole_sentence():
    # "Vase" sounds like "Fase" (code 38), but inside a longer sentence that's too weak
    assert match("Das ist eine schöne Vase", CAD, **DE)[0] is None


def test_sound_match_scores_below_exact_match():
    _, sound = match("Richtig", CAD, **DE)
    _, exact = match("Rechteck", CAD, **DE)
    assert sound < exact


def test_without_language_no_sound_matching():
    assert match("Zeichen ein Richtig", CAD)[0] is None


# --- compound words: spaces and hyphens don't matter --------------------------------

WB = {"workbench:PartDesignWorkbench": ["PartDesign"],
      "workbench:SketcherWorkbench": ["Sketcher"]}


def test_separated_words_match_compound_phrase():
    assert match("Wechsle zu Part Design", WB)[0] == "workbench:PartDesignWorkbench"
    assert match("Part-Design", WB)[0] == "workbench:PartDesignWorkbench"


def test_compound_text_matches_separated_phrase():
    assert match("partdesign bitte", {"x": ["Part Design"]})[0] == "x"


def test_joined_words_still_score_as_exact():
    assert match("Part Design", WB) == ("workbench:PartDesignWorkbench", 1.0)


# --- hotwords for the speech recognition ---------------------------------------------

def test_hotwords_are_unique_and_keep_order():
    assert hotwords(["Rechteck", "Kreis", "rechteck", " Linie "]) == "Rechteck, Kreis, Linie"


def test_hotwords_are_limited():
    text = hotwords(["Wort{}".format(i) for i in range(500)], max_chars=50)
    assert len(text) <= 50
    assert text.startswith("Wort0, Wort1")


def test_hotwords_empty():
    assert hotwords([]) is None
    assert hotwords(["", "  "]) is None


# --- function words ------------------------------------------------------------------------

def test_function_words_do_not_match_by_sound():
    """ "und" sounds like "Undo" (Kölner Phonetik 062)."""
    assert match("Extrudiere das und ziehe es ab", {"Std_Undo": ["Undo"]}, language="de")[0] is None


def test_function_words_do_not_match_by_spelling():
    """ "einen" looks like "Einfügen", "gut" like "Cut"."""
    commands = {"Std_Paste": ["Einfügen"], "Std_Cut": ["Cut"]}
    assert match("Ich trinke einen Kaffee", commands, language="de")[0] is None
    assert match("Das sieht gut aus", commands, language="de")[0] is None


def test_phrase_with_function_words_still_matches():
    assert match("Ansicht von vorne", {"Std_ViewFront": ["von vorne"]}, language="de")[0] == "Std_ViewFront"
