"""Tests for language packs: the language data of the recognition, outside the code (DESIGN.md 13.1)."""

import json

import pytest

from ttm_core import langpack
from ttm_core.languages import FILLER_WORDS, STOP_WORDS
from ttm_core.phonetics import PHONETICS


@pytest.fixture(autouse=True)
def no_user_dir():
    langpack.configure(None)
    yield
    langpack.configure(None)


def test_german_pack():
    de = langpack.pack("de")
    assert "und" in de.filler_words
    assert "mm" in de.parameter_words
    assert de.phonetics == "cologne"
    assert de.number_values["zwei"] == 2
    assert de.vocab["ui:cancel"][0] == "Abbrechen"


def test_stop_words_include_fillers_and_particles():
    de = langpack.pack("de")
    assert de.filler_words <= de.stop_words
    assert de.particles <= de.stop_words


def test_pattern_macros_are_expanded():
    for command, regex in langpack.pack("de").patterns:
        assert "{pronoun}" not in regex, command


def test_unknown_language_is_empty():
    xx = langpack.pack("xx")
    assert xx.filler_words == set() and xx.patterns == [] and xx.vocab == {} and xx.phonetics is None


def test_available_languages():
    assert "de" in langpack.languages()


def test_views_keep_the_old_interface():
    assert "und" in FILLER_WORDS.get("de", set())
    assert FILLER_WORDS.get("xx", set()) == set()
    assert STOP_WORDS.get(None, frozenset()) == frozenset()
    assert PHONETICS.get("de")("Rechteck") == "7424"
    assert PHONETICS.get("xx") is None


def test_user_changes_replace_lists_and_add_patterns(tmp_path):
    user = tmp_path / "lang" / "de"
    user.mkdir(parents=True)
    (user / "language.json").write_text(json.dumps({"filler_words": ["sozusagen"]}), encoding="utf-8")
    (user / "patterns.json").write_text(json.dumps(
        {"patterns": [["ui:rename", "taufe (?P<label>.+)"]]}), encoding="utf-8")
    langpack.configure(str(tmp_path))
    de = langpack.pack("de")
    assert de.filler_words == {"sozusagen"}
    assert "mm" in de.parameter_words                      # untouched lists stay
    assert de.patterns[0] == ("ui:rename", "taufe (?P<label>.+)")
    assert len(de.patterns) > 1                             # the pack's patterns follow


# --- editing lists on the settings page ------------------------------------------------------------

def test_editable_lists():
    assert "filler_words" in langpack.EDITABLE_LISTS
    assert "stop_words" in langpack.EDITABLE_LISTS


def test_save_list_stores_only_differences(tmp_path):
    langpack.configure(str(tmp_path))
    pack_fillers = langpack.pack_list("de", "filler_words")
    langpack.save_list("de", "filler_words", pack_fillers + ["sozusagen"])
    assert "sozusagen" in langpack.pack("de").filler_words
    saved = json.loads((tmp_path / "lang" / "de" / "language.json").read_text(encoding="utf-8"))
    assert "sozusagen" in saved["filler_words"]

    langpack.save_list("de", "filler_words", pack_fillers)          # back to the pack's list
    saved = json.loads((tmp_path / "lang" / "de" / "language.json").read_text(encoding="utf-8"))
    assert "filler_words" not in saved
    assert "sozusagen" not in langpack.pack("de").filler_words


def test_pack_list_ignores_user_changes(tmp_path):
    langpack.configure(str(tmp_path))
    langpack.save_list("de", "filler_words", ["nur", "das"])
    assert "und" in langpack.pack_list("de", "filler_words")
    assert langpack.pack("de").filler_words == {"nur", "das"}


def test_save_list_needs_a_user_dir():
    with pytest.raises(RuntimeError):
        langpack.save_list("de", "filler_words", ["x"])
