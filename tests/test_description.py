"""Tests for matching a sentence with the help texts of commands (DESIGN.md 7, stage 1b)."""

from ttm_core.description import DescriptionIndex, terms

# Status tips of FreeCAD 1.1.4, German translation.
TIPS = {
    "PartDesign_Pocket": "Extrudiert die ausgewählte Skizze oder das ausgewählte Profil und zieht das Ergebnis von dem Körper ab",
    "PartDesign_Pad": "Extrudiert die ausgewählte Skizze oder das ausgewählte Profil und fügt das Ergebnis dem Körper hinzu",
    "PartDesign_Hole": "Erstellt im aktiven Körper Bohrungen an den Mittelpunkten von Kreisen oder Kreisbögen der ausgewählten Skizze oder des ausgewählten Profils",
    "PartDesign_Chamfer": "Versieht die ausgewählten Kanten mit einer Fase",
    "PartDesign_Fillet": "Versieht die ausgewählten Kanten mit einer Verrundung",
    "PartDesign_Revolution": "Dreht die Skizze oder das Profil um eine Linie oder Achse herum und fügt das Ergebnis dem Körper hinzu",
    "PartDesign_Groove": "Dreht die Skizze oder das Profil um eine Linie oder Achse herum und zieht das Ergebnis von dem Körper ab",
    "Sketcher_CreateRectangle": "Erstellt ein Rechteck aus 2 Eckpunkten",
    "Std_Undo": "Die vorherige Aktion rückgängig machen",
    "Std_Save": "Speichert das aktive Dokument",
}


def best(text):
    return DescriptionIndex(TIPS, "de").ranking(text)[0]


def test_inflections_share_a_stem():
    assert terms("Extrudiere", "de") == terms("extrudiert", "de")
    assert terms("füge", "de") == terms("fügt", "de")


def test_separable_verb_joins_its_particle():
    assert "ab+zieh" in terms("zieht das Ergebnis von dem Körper ab", "de")
    assert "ab+zieh" in terms("ziehe es ab", "de")


def test_particle_inside_a_clause_is_a_preposition():
    assert not any("+" in t for t in terms("Erstellt ein Rechteck aus 2 Eckpunkten", "de"))


def test_stop_words_are_dropped():
    assert terms("das und es von dem", "de") == set()


def test_pocket_from_paraphrase():
    assert best("Extrudiere das und ziehe es vom bestehenden Körper ab")[0] == "PartDesign_Pocket"


def test_pad_from_paraphrase():
    assert best("Extrudiere die Skizze und füge sie dem Körper hinzu")[0] == "PartDesign_Pad"


def test_groove_from_paraphrase():
    assert best("Drehe die Skizze um die Achse und zieh das ab")[0] == "PartDesign_Groove"


def test_undo_from_paraphrase():
    assert best("Mach die vorherige Aktion rückgängig") == ("Std_Undo", 1.0)


def test_unrelated_words_do_not_count():
    """Words that appear in no help text are left out instead of lowering every score."""
    index = DescriptionIndex(TIPS, "de")
    assert index.ranking("Speichere bitte das Dokument")[0] == index.ranking("Speichere das Dokument")[0]


def test_known_terms_reports_how_much_was_recognized():
    index = DescriptionIndex(TIPS, "de")
    assert index.known_terms("und zwar von hier nach hier") == 0
    assert index.known_terms("Extrudiere das und ziehe es ab") == 2


def test_empty_index():
    assert DescriptionIndex({}, "de").ranking("Extrudiere") == []
