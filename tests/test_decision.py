"""Tests for deciding whether to execute, reject or ignore an utterance (DESIGN.md 7 and 9.3)."""

import pytest

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


# --- help texts as a fallback (stage 1b) -------------------------------------------------

def described(id_, phrases, description, level="workbench", active=True):
    return dict(cand(id_, phrases, level, active), description=description)


DESCRIBED = [
    described("PartDesign_Pocket", ["Vertiefung"],
              "Extrudiert die ausgewählte Skizze oder das ausgewählte Profil und zieht das Ergebnis von dem Körper ab"),
    described("PartDesign_Pad", ["Aufpolsterung"],
              "Extrudiert die ausgewählte Skizze oder das ausgewählte Profil und fügt das Ergebnis dem Körper hinzu"),
    described("PartDesign_Groove", ["Nut"],
              "Dreht die Skizze oder das Profil um eine Linie oder Achse herum und zieht das Ergebnis von dem Körper ab"),
    described("Std_Undo", ["Rückgängig"], "Die vorherige Aktion rückgängig machen", "global"),
]


def test_description_finds_command_without_its_name():
    d = decide("Extrudiere das und ziehe es vom bestehenden Körper ab", DESCRIBED, language="de")
    assert d.kind == "execute"
    assert d.command == "PartDesign_Pocket"
    assert d.via == "description"


def test_name_wins_over_description():
    d = decide("Aufpolsterung", DESCRIBED, language="de")
    assert d.command == "PartDesign_Pad"
    assert d.via == "name"


def test_description_needs_a_clear_lead():
    """Only "extrudieren" and "Körper": Pocket and Pad fit equally well."""
    d = decide("Extrudiere den Körper", DESCRIBED, language="de")
    assert d.kind == "not_understood"


def test_description_needs_more_than_one_known_word():
    d = decide("Ich mag meinen Körper, und zwar sehr", DESCRIBED, language="de")
    assert d.kind == "ignore"


def test_inactive_command_found_by_description_is_not_executed():
    candidates = [dict(c, active=c["id"] != "PartDesign_Pocket") for c in DESCRIBED]
    d = decide("Extrudiere das und ziehe es vom Körper ab", candidates, language="de")
    assert d.kind == "not_understood"
    assert d.reason == "inactive"


def test_without_descriptions_long_sentences_are_still_ignored():
    d = decide("Ich ziehe es jetzt vom Körper ab", CANDIDATES, language="de")
    assert d.kind == "ignore"


def test_description_wins_over_a_name_explaining_little_of_the_sentence():
    """The vocabulary maps "extrudieren" to Pad, the whole sentence describes Pocket."""
    candidates = [dict(c, phrases=c["phrases"] + ["extrudieren"]) if c["id"] == "PartDesign_Pad" else c
                  for c in DESCRIBED]
    d = decide("Extrudiere das und ziehe es vom bestehenden Körper ab", candidates, language="de")
    assert (d.kind, d.command, d.via) == ("execute", "PartDesign_Pocket", "description")


def test_name_stays_when_it_explains_the_sentence():
    candidates = [dict(c, phrases=c["phrases"] + ["extrudieren"]) if c["id"] == "PartDesign_Pad" else c
                  for c in DESCRIBED]
    d = decide("Extrudieren", candidates, language="de")
    assert (d.command, d.via) == ("PartDesign_Pad", "name")


def test_talk_with_weak_similarities_is_ignored():
    """ "schon" looks a bit like the English label "Cone" (0.63): talk, not a command attempt."""
    candidates = CANDIDATES + [cand("Part_Cone", ["Kegel", "Cone"])]
    assert decide("Das sieht schon ganz gut aus", candidates, language="de").kind == "ignore"


def test_longer_phrase_wins_a_tie():
    """ "Part" is contained in "Part Design": the longer phrase is meant, not ambiguity."""
    candidates = [cand("Std_Part", ["Part"], "global"),
                  cand("workbench:PartDesignWorkbench", ["Part Design"], "global")]
    d = decide("Wechsle zu Part Design", candidates, language="de")
    assert (d.kind, d.command) == ("execute", "workbench:PartDesignWorkbench")



# --- foreign labels (English command names for a German speaker) ---------------------------

def test_foreign_labels_match_by_spelling():
    candidates = [dict(cand("PartDesign_Pad", ["Aufpolsterung"]), foreign=["Pad"])]
    assert decide("Pad", candidates, language="de").command == "PartDesign_Pad"


def test_foreign_labels_do_not_match_by_sound():
    """German sound rules on English words: "Ebene" and "Open" are both 016."""
    candidates = [dict(cand("Std_Open", ["Öffnen"], "global"), foreign=["Open"])]
    d = decide("Skizze in der XY-Ebene", candidates, language="de")
    assert d.kind != "execute"


# --- statements, questions, opinions are talk (statement_words in the language pack) --------------

@pytest.mark.parametrize("text", [
    "Der Kreis ist irgendwie zu groß", "Das Rechteck sitzt noch nicht richtig", "Wie spät ist es eigentlich",
    "Ich glaube das Rechteck passt so", "Ich habe gestern einen Kreis gezeichnet",
])
def test_statements_are_talk(text):
    d = decide(text, CANDIDATES, language="de")
    assert (d.kind, d.reason) == ("ignore", "statement"), d


@pytest.mark.parametrize("text, command", [
    ("Ich brauche hier jetzt einen Kreis", "Sketcher_CreateCircle"),
    ("Zeichne jetzt mal bitte ein Rechteck", "Sketcher_CreateRectangle"),
    ("Kreis", "Sketcher_CreateCircle"),
])
def test_commands_without_statement_words_still_work(text, command):
    d = decide(text, CANDIDATES, language="de")
    assert (d.kind, d.command) == ("execute", command)


def test_statement_words_english():
    en = [cand("Sketcher_CreateCircle", ["Circle"], "edit")]
    assert decide("The circle is a bit too big", en, language="en").reason == "statement"
    assert decide("I need a circle here now", en, language="en").kind == "execute"


def test_short_statements_are_not_judged():
    """Under three words a statement word is no evidence: "Ist Kreis" is a clumsy command."""
    assert decide("Ist Kreis", CANDIDATES, language="de").kind == "execute"


# --- short forms of labels -----------------------------------------------------------------------

PARALLEL = [{"id": "Sketcher_ConstrainParallel", "phrases": ["Parallel festlegen"], "short": ["Parallel"],
             "level": "edit", "active": True},
            {"id": "Std_ViewFitSelection", "phrases": ["Fit Selection"], "short": ["Fit"], "level": "global", "active": True}]


def test_short_form_inside_a_sentence_only_when_spelled_exactly():
    assert decide("Mach die beiden mal parallel", PARALLEL, language="de").command == "Sketcher_ConstrainParallel"
    assert decide("Let me get a coffee first", PARALLEL, language="en").kind != "execute"
