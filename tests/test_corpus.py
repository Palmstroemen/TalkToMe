"""Tests for the ground-truth corpus (DESIGN.md 16.5): sentences with the steps they must produce,
played against recorded FreeCAD contexts with the vocabulary of the pack under test."""

import json

import pytest

from ttm_core import corpus, langpack
from ttm_core.decision import Decision


@pytest.fixture(autouse=True)
def no_user_dir():
    langpack.configure(None)
    yield
    langpack.configure(None)


# --- judging one case ---------------------------------------------------------------------------

def ex(command, **args):
    return (Decision("execute", command, args=args or None), "")


IGNORE = (Decision("ignore", None), "")
UNCLEAR = (Decision("not_understood", None), "")


@pytest.mark.parametrize("expect, steps, outcome", [
    (["PartDesign_Pad"], [ex("PartDesign_Pad")], "correct"),
    (["PartDesign_Pad"], [ex("PartDesign_Pocket")], "wrong"),
    (["PartDesign_Pad"], [IGNORE], "missed"),
    (["PartDesign_Pad"], [UNCLEAR], "unclear"),
    (["PartDesign_Pad", "Std_Save"], [ex("PartDesign_Pad"), IGNORE, ex("Std_Save")], "correct"),
    (["PartDesign_Pad", "Std_Save"], [ex("PartDesign_Pad"), UNCLEAR], "unclear"),
    (["PartDesign_Pad"], [ex("PartDesign_Pad"), ex("Std_Save")], "wrong"),          # one step too many
    ("ignore", [IGNORE], "correct"),
    ("ignore", [UNCLEAR], "unclear"),
    ("ignore", [ex("Std_Undo")], "false_trigger"),
    ("not_understood", [UNCLEAR], "correct"),
    ("not_understood", [IGNORE], "correct"),       # nothing executed: what matters
    ("not_understood", [ex("Std_Undo")], "false_trigger"),
    ([{"command": "ui:rename", "args": {"label": "Bodenplatte"}}], [ex("ui:rename", label="Bodenplatte")], "correct"),
    ([{"command": "ui:rename", "args": {"label": "Bodenplatte"}}], [ex("ui:rename", label="Boden")], "wrong"),
    # recognized, but not available now ("Rückgängig" in a new document): the right reaction
    (["Std_Undo"], [(Decision("not_understood", None, reason="inactive", alternatives=[("Std_Undo", 1.0)]), "")], "correct"),
    (["Std_Undo"], [(Decision("not_understood", None, reason="inactive", alternatives=[("Std_Redo", 1.0)]), "")], "unclear"),
    ("ignore", [(Decision("not_understood", None, reason="inactive", alternatives=[("Std_Paste", 0.8)]), "")], "unclear"),
])
def test_judge(expect, steps, outcome):
    assert corpus.judge(expect, steps) == outcome


def test_outcomes_are_ranked_by_harm():
    assert corpus.RANK["correct"] < corpus.RANK["unclear"] < corpus.RANK["missed"] \
        < corpus.RANK["false_trigger"] < corpus.RANK["wrong"]


# --- reading cases ------------------------------------------------------------------------------

def test_read_cases_skips_comments_and_blank_lines(tmp_path):
    f = tmp_path / "corpus.jsonl"
    f.write_text('# a comment\n\n{"text": "Fase", "context": "c", "expect": ["PartDesign_Chamfer"]}\n',
                 encoding="utf-8")
    cases = corpus.read_cases(str(f), "de")
    assert [(c["text"], c["line"], c["source"]) for c in cases] == [("Fase", 3, "de")]


def test_read_cases_reports_broken_lines(tmp_path):
    f = tmp_path / "corpus.jsonl"
    f.write_text('{"text": "Fase"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        corpus.read_cases(str(f), "de")


# --- running a pack -----------------------------------------------------------------------------

def test_cases_of_a_variant_include_its_base(tmp_path, monkeypatch):
    import shutil
    lang = tmp_path / "packs"
    shutil.copytree(langpack.LANG_DIR, lang)
    monkeypatch.setattr(langpack, "LANG_DIR", str(lang))
    langpack.configure(None)
    (lang / "de-AT").mkdir()
    (lang / "de-AT" / "language.json").write_text(json.dumps({"base": "de"}), encoding="utf-8")
    (lang / "de-AT" / "corpus.jsonl").write_text(
        '{"text": "Mach eine Fase, gell", "context": "fc114_partdesign", "expect": ["PartDesign_Chamfer"]}\n',
        encoding="utf-8")
    sources = {c["source"] for c in corpus.cases("de-AT")}
    assert sources == {"de", "de-AT"}
    assert corpus.context("de-AT", "fc114_partdesign")["context"]["current_workbench"] == "PartDesignWorkbench"


def test_run_and_summary():
    cases = [{"text": "Mach eine Fase", "context": "fc114_partdesign", "expect": ["PartDesign_Chamfer"]},
             {"text": "Ich trinke jetzt einen Kaffee", "context": "fc114_partdesign", "expect": "ignore"}]
    results = corpus.run("de", cases)
    assert [r.outcome for r in results] == ["correct", "correct"]
    assert corpus.summary(results)["correct"] == 2


def test_user_corrections_are_used(tmp_path):
    """A form learned in training makes a misheard sentence understood."""
    case = [{"text": "Mach eine Pfasel", "context": "fc114_partdesign", "expect": ["PartDesign_Chamfer"]}]
    before = corpus.run("de", case)[0].outcome
    (tmp_path / "custom.de.json").write_text(json.dumps({"_heard": {"PartDesign_Chamfer": ["Pfasel"]}}),
                                             encoding="utf-8")
    after = corpus.run("de", case, user_dir=str(tmp_path))[0].outcome
    assert after == "correct"


def test_compare_finds_worse_and_better():
    a = [corpus.Result({"text": "x", "line": 1, "source": "de"}, "correct", []),
         corpus.Result({"text": "y", "line": 2, "source": "de"}, "missed", [])]
    b = [corpus.Result({"text": "x", "line": 1, "source": "de"}, "wrong", []),
         corpus.Result({"text": "y", "line": 2, "source": "de"}, "correct", [])]
    worse, better = corpus.compare(a, b)
    assert [r.case["text"] for _, r in worse] == ["x"]
    assert [r.case["text"] for _, r in better] == ["y"]


# --- the corpora of the packs: the real ground truth ---------------------------------------------

@pytest.mark.parametrize("language", [lc for lc in langpack.languages() if corpus.cases(lc)])
def test_pack_corpus(language):
    """Every case is correct, except those marked "known" (a known weakness, still reported)."""
    results = corpus.run(language, corpus.cases(language))
    failed = [corpus.describe(r) for r in results if r.outcome != "correct" and not r.case.get("known")]
    assert not failed, "\n".join(failed)


def test_packs_have_a_corpus():
    assert len(corpus.cases("de")) >= 50
    assert len(corpus.cases("en")) >= 30


# --- coverage: how well each command is reached by voice (DESIGN.md 16.7) -----------------------

def case(text, command, ctx="fc114_partdesign"):
    return {"text": text, "context": ctx, "expect": [command], "line": 0, "source": "de"}


def test_coverage_counts_distinct_sentences_recognized_without_themselves():
    cov = corpus.coverage("de", [case("Mach eine Fase", "PartDesign_Chamfer"),
                                 case("Fase", "PartDesign_Chamfer"),                 # same meaningful words
                                 case("Versieh die Kanten mit einer Fase", "PartDesign_Chamfer")])
    row = cov["PartDesign_Chamfer"]
    assert row.sentences == 3 and row.distinct == 2
    assert row.recognized == 3


def test_coverage_leave_one_out():
    """A sentence that is a phrase of the command proves nothing: it is checked without itself."""
    pack_phrase = langpack.pack("de").vocab["Std_Save"][-1]               # "speichere das"
    row = corpus.coverage("de", [case(pack_phrase, "Std_Save")])["Std_Save"]
    assert row.sentences == 1 and row.recognized <= 1


def test_coverage_names_the_closest_rival():
    row = corpus.coverage("de", [case("Symmetrisch", "Sketcher_ConstrainSymmetric", "fc114_sketcher")])[
        "Sketcher_ConstrainSymmetric"]
    assert row.recognized == 0
    assert row.rivals and row.rivals[0] in ("Std_ViewIsometric", "Std_ViewGroup")
    assert row.light == "red"


def test_coverage_lists_commands_without_sentences():
    cov = corpus.coverage("de", [case("Fase", "PartDesign_Chamfer")])
    assert cov["PartDesign_Hole"].sentences == 0 and cov["PartDesign_Hole"].light == "red"


def test_traffic_light():
    assert corpus.light(distinct_recognized=5, min_margin=0.2) == "green"
    assert corpus.light(distinct_recognized=5, min_margin=0.01) == "yellow"     # a rival is close
    assert corpus.light(distinct_recognized=1, min_margin=0.5) == "yellow"
    assert corpus.light(distinct_recognized=0, min_margin=None) == "red"


def test_only_real_alternatives_count_as_variants():
    """ "Mach eine Fase" and "mach eine Fase." are no new variant; "Kantenabschrägung" is."""
    row = corpus.coverage("de", [case("Fase", "PartDesign_Chamfer"), case("Mach eine Fase", "PartDesign_Chamfer"),
                                 case("mach eine Fase.", "PartDesign_Chamfer"),
                                 case("Kantenabschrägung", "PartDesign_Chamfer")])["PartDesign_Chamfer"]
    assert row.sentences == 4 and row.distinct == 2
