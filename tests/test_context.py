"""Tests for building the command candidates of the current context (DESIGN.md section 6)."""

from ttm_core.context import build_candidates

TOOLBARS = {
    "File": ["Std_New", "Std_Save", "Separator"],
    "View": ["Std_ViewFitAll", "Std_ViewFront"],
    "Sketcher geometries": ["Sketcher_CreateLine", "Sketcher_CreateRectangle", "Sketcher_CreateCircle"],
    "Part Design": ["PartDesign_Pad", "Sketcher_CreateLine"],          # duplicate on purpose
}
LABELS = {
    "Std_New": ["&Neu", "&New"],
    "Std_Save": ["&Speichern", "&Save"],
    "Std_ViewFitAll": ["Alles einpassen", "Fit all"],
    "Std_ViewFront": ["Vorderansicht", "Front"],
    "Sketcher_CreateLine": ["Linie", "Line"],
    "Sketcher_CreateRectangle": ["Rechteck", "Rectangle"],
    "Sketcher_CreateCircle": ["Kreis", "Circle"],
    "PartDesign_Pad": ["Aufpolsterung...", "Pad..."],
}
ACTIVE = {"PartDesign_Pad": False}       # everything else active


def by_id(candidates):
    return {c["id"]: c for c in candidates}


def test_levels_without_edit_mode():
    c = by_id(build_candidates(TOOLBARS, LABELS, ACTIVE))
    assert c["Std_Save"]["level"] == "global"
    assert c["Sketcher_CreateRectangle"]["level"] == "workbench"
    assert c["PartDesign_Pad"]["level"] == "workbench"
    assert "Separator" not in c


def test_edit_mode_lifts_matching_commands():
    c = by_id(build_candidates(TOOLBARS, LABELS, ACTIVE, edit_prefix="Sketcher_"))
    assert c["Sketcher_CreateRectangle"]["level"] == "edit"
    assert c["PartDesign_Pad"]["level"] == "workbench"


def test_commands_appear_once():
    ids = [c["id"] for c in build_candidates(TOOLBARS, LABELS, ACTIVE)]
    assert len(ids) == len(set(ids))


def test_phrases_from_labels_and_vocabulary():
    vocab = {"PartDesign_Pad": ["extrudieren", "hochziehen"]}
    c = by_id(build_candidates(TOOLBARS, LABELS, ACTIVE, vocab=vocab))
    assert c["PartDesign_Pad"]["phrases"] == ["extrudieren", "hochziehen", "Aufpolsterung", "Pad"]


def test_active_flag():
    c = by_id(build_candidates(TOOLBARS, LABELS, ACTIVE))
    assert c["PartDesign_Pad"]["active"] is False
    assert c["Sketcher_CreateRectangle"]["active"] is True


def test_commands_without_phrases_are_left_out():
    c = by_id(build_candidates({"X": ["Std_Unknown"]}, {}, {}))
    assert "Std_Unknown" not in c


def test_dialog_adds_ok_and_cancel_on_top():
    vocab = {"ui:ok": ["OK"], "ui:cancel": ["Abbrechen"]}
    c = by_id(build_candidates(TOOLBARS, LABELS, ACTIVE, dialog_open=True, vocab=vocab))
    assert c["ui:ok"]["level"] == "dialog"
    assert c["ui:cancel"]["level"] == "dialog"


def test_without_dialog_cancel_is_global_and_ok_absent():
    vocab = {"ui:ok": ["OK"], "ui:cancel": ["Abbrechen"]}
    c = by_id(build_candidates(TOOLBARS, LABELS, ACTIVE, vocab=vocab))
    assert c["ui:cancel"]["level"] == "global"
    assert "ui:ok" not in c


def test_workbench_switches_exclude_the_current_one():
    workbenches = {"PartDesignWorkbench": ["Part Design"], "SketcherWorkbench": ["Sketcher"]}
    c = by_id(build_candidates(TOOLBARS, LABELS, ACTIVE, workbenches=workbenches,
                               current_workbench="PartDesignWorkbench"))
    assert c["workbench:SketcherWorkbench"]["level"] == "global"
    assert c["workbench:SketcherWorkbench"]["phrases"] == ["Sketcher"]
    assert "workbench:PartDesignWorkbench" not in c


def test_descriptions_are_attached():
    cands = build_candidates({"tb": ["PartDesign_Pad"]}, {"PartDesign_Pad": ["Aufpolsterung"]}, {},
                             descriptions={"PartDesign_Pad": "Extrudiert die Skizze"})
    assert cands[0]["description"] == "Extrudiert die Skizze"


def test_description_is_empty_when_unknown():
    cands = build_candidates({"tb": ["PartDesign_Pad"]}, {"PartDesign_Pad": ["Aufpolsterung"]}, {})
    assert cands[0]["description"] == ""


def test_workbench_selector_is_no_candidate():
    """Std_Workbench carries all workbench names; switching is offered as workbench:<name>."""
    cands = build_candidates({"Workbench": ["Std_Workbench"]}, {"Std_Workbench": ["Part Design", "Draft"]}, {})
    assert cands == [] or "Std_Workbench" not in by_id(cands)


def test_foreign_labels_are_kept_apart():
    cands = build_candidates({"tb": ["Std_Open"]}, {"Std_Open": ["Öffnen"]}, {},
                             foreign_labels={"Std_Open": ["&Open...", "öffnen"]})
    assert cands[0]["phrases"] == ["Öffnen"]
    assert cands[0]["foreign"] == ["Open"]          # cleaned, without what the phrases have already


def test_foreign_labels_alone_make_a_candidate():
    cands = build_candidates({"tb": ["Std_Open"]}, {}, {}, foreign_labels={"Std_Open": ["Open"]})
    assert cands[0]["phrases"] == [] and cands[0]["foreign"] == ["Open"]


def test_microphone_off_is_always_offered():
    vocab = {"ui:mic_off": ["Mikro aus"]}
    for dialog_open in (False, True):
        c = by_id(build_candidates(TOOLBARS, LABELS, ACTIVE, dialog_open=dialog_open, vocab=vocab))
        assert c["ui:mic_off"]["level"] == "global"
