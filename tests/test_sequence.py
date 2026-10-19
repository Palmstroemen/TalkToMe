"""Tests for splitting an utterance into clauses and finding the next step (DESIGN.md 7.x)."""

from ttm_core.clauses import split_clauses
from ttm_core.sequence import next_step


def cand(id_, phrases, level="workbench", active=True, description=""):
    return {"id": id_, "phrases": phrases, "level": level, "active": active, "description": description}


POCKET = "Extrudiert die ausgewählte Skizze oder das ausgewählte Profil und zieht das Ergebnis von dem Körper ab"
PAD = "Extrudiert die ausgewählte Skizze oder das ausgewählte Profil und fügt das Ergebnis dem Körper hinzu"

PART_DESIGN = [
    cand("PartDesign_Body", ["Körper"], description="Erstellt einen neuen Körper und aktiviert ihn"),
    cand("PartDesign_Pad", ["Aufpolsterung", "extrudieren"], description=PAD),
    cand("PartDesign_Pocket", ["Vertiefung"], description=POCKET),
    cand("PartDesign_Chamfer", ["Fase"], description="Versieht die ausgewählten Kanten mit einer Fase"),
    cand("PartDesign_Fillet", ["Verrundung"], description="Versieht die ausgewählten Kanten mit einer Verrundung"),
    cand("Std_Save", ["Speichern"], "global", description="Speichert das aktive Dokument"),
    cand("workbench:PartDesignWorkbench", ["Part Design"], "global"),
]


# --- clauses -------------------------------------------------------------------------------

def test_split_at_punctuation():
    assert split_clauses("Wechsle zu Part Design, erstelle einen Körper. Speichern!", "de") == \
        ["Wechsle zu Part Design", "erstelle einen Körper", "Speichern"]


def test_split_at_clause_words_keeps_them():
    assert split_clauses("Mach eine Fase und dann eine Verrundung", "de") == \
        ["Mach eine Fase", "und dann eine Verrundung"]


def test_decimal_comma_is_no_clause_boundary():
    assert split_clauses("Polster 12,5 mm", "de") == ["Polster 12,5 mm"]


def test_no_empty_clauses():
    assert split_clauses(" , und. ", "de") == []
    assert split_clauses("", "de") == []


# --- next step -----------------------------------------------------------------------------

def step(text, candidates=PART_DESIGN):
    d, n = next_step(split_clauses(text, "de"), candidates, "de")
    return d.kind, d.command, n


def test_single_command():
    assert step("Mach eine Fase") == ("execute", "PartDesign_Chamfer", 1)


def test_first_of_two_commands():
    assert step("Mach eine Fase und dann eine Verrundung") == ("execute", "PartDesign_Chamfer", 1)


def test_one_command_spread_over_two_clauses():
    """The help text of Pocket explains both clauses; "extrudieren" (Pad) only the first."""
    assert step("Extrudiere das und ziehe es vom bestehenden Körper ab") == ("execute", "PartDesign_Pocket", 2)


def test_talk_clause_is_skipped():
    kind, _, n = step("und zwar von hier, Speichern")
    assert (kind, n) == ("ignore", 1)


def test_unclear_clause_stops():
    assert step("Klaus, Speichern")[0] == "not_understood"


def test_explained_words_are_reported():
    d, _ = next_step(["Erstelle einen neuen Körper"], PART_DESIGN, "de")
    assert d.command == "PartDesign_Body"
    assert d.words >= 2


def test_workbench_switch_is_a_step_of_its_own():
    """The following clauses are decided in the new workbench's context."""
    part_workbench = [
        cand("Std_Part", ["Part"], "global", description="Erstellt einen neuen Part-Container und aktiviert ihn"),
        cand("workbench:PartDesignWorkbench", ["Part Design"], "global"),
    ]
    assert step("Wechsle zu Part Design, und erstelle einen neuen Körper", part_workbench) == \
        ("execute", "workbench:PartDesignWorkbench", 1)



def test_rename_is_a_step_with_its_label():
    d, n = next_step(split_clauses("den nennen wir Bodenplatte, und mach eine Fase", "de"), PART_DESIGN, "de")
    assert (d.kind, d.command, d.args, n) == ("execute", "ui:rename", {"label": "Bodenplatte"}, 1)


def test_learned_pattern_in_a_sequence():
    clauses = split_clauses("Nenndas Bodenplatte, und mach eine Fase", "de")
    d, n = next_step(clauses, PART_DESIGN, "de", patterns={"ui:rename": ["nenndas {label}"]})
    assert (d.command, d.args, n) == ("ui:rename", {"label": "Bodenplatte"}, 1)


# --- a whole utterance, as the service decides it (used by the corpus, DESIGN.md 16.5) ----------

from ttm_core.sequence import plan_utterance, start_utterance, VALUES   # noqa: E402

MIC_OFF = cand("ui:mic_off", ["kurze Pause", "Ok kurze Pause"], "global")
OK = cand("ui:ok", ["OK"], "dialog")


def kinds(steps):
    return [(d.kind, d.command) for d, span in steps]


def test_plan_of_a_sequence():
    steps = plan_utterance("Mach eine Fase und dann eine Verrundung", PART_DESIGN, "de")
    assert kinds(steps) == [("execute", "PartDesign_Chamfer"), ("execute", "PartDesign_Fillet")]
    assert steps[0][1] == "Mach eine Fase"


def test_talk_is_ignored_as_a_whole():
    pending, ignored = start_utterance("Ich trinke jetzt einen Kaffee", PART_DESIGN, "de")
    assert pending == [] and ignored.kind == "ignore"
    assert [d.kind for d, _ in plan_utterance("Ich trinke jetzt einen Kaffee", PART_DESIGN, "de")] == ["ignore"]


def test_exclusive_command_replaces_the_rest():
    assert kinds(plan_utterance("Ok, kurze Pause", PART_DESIGN + [MIC_OFF, OK], "de")) == [("execute", "ui:mic_off")]


def test_values_only_while_a_tool_runs():
    assert kinds(plan_utterance("50 mal 30", PART_DESIGN, "de", tool_running=True)) == [("execute", VALUES)]
    assert plan_utterance("50 mal 30", PART_DESIGN, "de", tool_running=True)[0][0].args == \
        {"values": [[None, 50.0, "length"], [None, 30.0, "length"]]}
    assert kinds(plan_utterance("50 mal 30", PART_DESIGN, "de"))[0][0] != "execute"


def test_plan_stops_at_an_unclear_clause():
    steps = plan_utterance("Mach eine Fase, dann Blubberdings, dann Speichern", PART_DESIGN, "de")
    assert kinds(steps)[0] == ("execute", "PartDesign_Chamfer")
    assert steps[-1][0].kind in ("not_understood", "execute")
    assert all(d.kind != "not_understood" for d, _ in steps[:-1])


WORKBENCH_PART = cand("workbench:PartWorkbench", ["Part"], "global")


def test_values_win_over_a_sound_alike_while_a_tool_runs():
    """ "Breite" sounds like "Part": with a tool running, a clause of only values fills the tool."""
    steps = plan_utterance("Breite 50, Höhe 30", PART_DESIGN + [WORKBENCH_PART], "de", tool_running=True)
    assert kinds(steps) == [("execute", VALUES)]
    assert steps[0][0].args == {"values": [[0, 50.0, "length"], [1, 30.0, "length"]]}


def test_value_clauses_in_a_row_are_one_step():
    steps = plan_utterance("50, 30", PART_DESIGN, "de", tool_running=True)
    assert kinds(steps) == [("execute", VALUES)]


def test_command_name_still_wins_next_to_values():
    steps = plan_utterance("Mach eine Fase, 2 mm", PART_DESIGN, "de", tool_running=True)
    assert kinds(steps)[0] == ("execute", "PartDesign_Chamfer")


def test_no_workbench_switch_while_a_tool_runs():
    steps = plan_utterance("Part", PART_DESIGN + [WORKBENCH_PART], "de", tool_running=True)
    assert all(d.command != "workbench:PartWorkbench" for d, _ in steps if d.kind == "execute")
    assert kinds(plan_utterance("Part", PART_DESIGN + [WORKBENCH_PART], "de")) == [("execute", "workbench:PartWorkbench")]
