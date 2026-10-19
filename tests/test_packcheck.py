"""Tests for checking a language pack before a pull request (tools/check_pack.py, DESIGN.md 16.1)."""

import json
import shutil

import pytest

from ttm_core import langpack, packcheck


@pytest.fixture
def packs(tmp_path, monkeypatch):
    lang = tmp_path / "lang"
    shutil.copytree(langpack.LANG_DIR, lang)
    monkeypatch.setattr(langpack, "LANG_DIR", str(lang))
    langpack.configure(None)
    yield lang
    langpack.configure(None)


def errors(language):
    return [m for level, m in packcheck.check(language) if level == "error"]


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize("language", ["de", "en"])
def test_shipped_packs_are_fine(language):
    assert errors(language) == []


def test_missing_pack(packs):
    assert any("language.json" in m for m in errors("fr"))


def test_broken_json(packs):
    write(packs / "fr" / "language.json", '{"name": "Français",')
    assert any("language.json" in m and "JSON" in m for m in errors("fr"))


def test_minimal_pack_gets_warnings_not_errors(packs):
    write(packs / "fr" / "language.json", {"name": "Français"})
    result = packcheck.check("fr")
    assert [m for level, m in result if level == "error"] == []
    warnings = " ".join(m for level, m in result if level == "warning")
    assert "filler_words" in warnings                       # missing compared to English
    assert "phonetics" in warnings and "corpus" in warnings


def test_unknown_algorithm(packs):
    write(packs / "fr" / "language.json", {"name": "Français", "phonetics": "soundex-fr"})
    assert any("soundex-fr" in m for level, m in packcheck.check("fr") if level == "warning")


def test_bad_pattern(packs):
    write(packs / "fr" / "language.json", {"name": "Français"})
    write(packs / "fr" / "patterns.json", {"patterns": [["ui:rename", "appelle-le (?P<label>.+"]]})
    assert any("pattern" in m for m in errors("fr"))


def test_unknown_pattern_group(packs):
    write(packs / "fr" / "language.json", {"name": "Français"})
    write(packs / "fr" / "patterns.json", {"patterns": [["ui:rename", "appelle-le (?P<nom>.+)"]]})
    assert any("nom" in m for m in errors("fr"))


def test_wrong_types(packs):
    write(packs / "fr" / "language.json", {"name": "Français", "filler_words": "et alors"})
    write(packs / "fr" / "vocab.json", {"PartDesign_Pad": "protrusion"})
    found = " ".join(errors("fr"))
    assert "filler_words" in found and "PartDesign_Pad" in found


def test_corpus_with_unknown_context(packs):
    write(packs / "fr" / "language.json", {"name": "Français"})
    write(packs / "fr" / "corpus.jsonl", '{"text": "Protrusion", "context": "nowhere", "expect": ["PartDesign_Pad"]}\n')
    assert any("nowhere" in m for m in errors("fr"))


def test_failing_corpus_case_is_an_error(packs):
    with open(packs / "de" / "corpus.jsonl", "a", encoding="utf-8") as f:
        f.write('{"text": "Speichern", "context": "fc114_partdesign", "expect": ["Std_Undo"]}\n')
    assert any("Speichern" in m for m in errors("de"))


def test_variant_with_missing_base(packs):
    write(packs / "de-AT" / "language.json", {"name": "Deutsch (Österreich)", "base": "de-XX"})
    assert any("de-XX" in m for m in errors("de-AT"))


def test_variant_inherits_what_is_missing(packs):
    write(packs / "de-AT" / "language.json", {"name": "Deutsch (Österreich)", "base": "de", "+filler_words": ["gell"]})
    warnings = " ".join(m for level, m in packcheck.check("de-AT") if level == "warning")
    assert "filler_words" not in warnings and errors("de-AT") == []
