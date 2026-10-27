# SPDX-License-Identifier: LGPL-2.1-or-later
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


# --- variants: a pack inherits from its base (DESIGN.md 16.3) --------------------------------------

def write(directory, name, data):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def packs(tmp_path, monkeypatch):
    """The real packs plus a variant de-AT, in a copy of the lang folder."""
    import shutil
    lang = tmp_path / "packs"
    shutil.copytree(langpack.LANG_DIR, lang)
    monkeypatch.setattr(langpack, "LANG_DIR", str(lang))
    langpack.configure(None)
    write(lang / "de-AT", "language.json", {
        "name": "Deutsch (Österreich)", "base": "de",
        "+filler_words": ["gell", "eh"],
        "number_values": {"zwoa": 2},
    })
    write(lang / "de-AT", "vocab.json", {"Std_Save": ["sicher das"]})
    write(lang / "de-AT", "patterns.json", {"patterns": [["ui:rename", "tauf(?:e)? {pronoun} (?P<label>.+)"]]})
    write(lang / "de-AT", "speech.json", {"messages": {"ready": {"level": "important", "text": ["Servus, ich höre zu."]}}})
    yield lang
    langpack.configure(None)


def test_variant_inherits_everything_it_does_not_change(packs):
    at, de = langpack.pack("de-AT"), langpack.pack("de")
    assert at.name == "Deutsch (Österreich)"
    assert at.phonetics == "cologne" and at.stemmer == de.stemmer
    assert at.parameter_words == de.parameter_words
    assert at.voice == de.voice


def test_variant_extends_lists_and_merges_tables(packs):
    at, de = langpack.pack("de-AT"), langpack.pack("de")
    assert at.filler_words == de.filler_words | {"gell", "eh"}
    assert at.stop_words >= {"gell", "eh"}
    assert at.number_values["zwoa"] == 2 and at.number_values["zwei"] == 2


def test_variant_phrases_come_first(packs):
    assert langpack.pack("de-AT").vocab["Std_Save"][0] == "sicher das"
    assert "speichern" in langpack.pack("de-AT").vocab["Std_Save"]
    assert langpack.pack("de-AT").vocab["ui:cancel"] == langpack.pack("de").vocab["ui:cancel"]


def test_variant_patterns_come_first_and_use_base_macros(packs):
    patterns = langpack.pack("de-AT").patterns
    assert patterns[0][0] == "ui:rename" and patterns[0][1].startswith("tauf")
    assert "{pronoun}" not in patterns[0][1]
    assert patterns[1:] == langpack.pack("de").patterns


def test_variant_messages_override_single_entries(packs):
    at = langpack.pack("de-AT")
    assert at.messages["ready"]["text"] == ["Servus, ich höre zu."]
    assert at.messages["not_understood"] == langpack.pack("de").messages["not_understood"]


def test_base_is_not_changed_by_its_variant(packs):
    de = langpack.pack("de")
    assert "gell" not in de.filler_words and "zwoa" not in de.number_values


def test_chain_and_recognition_language(packs):
    at = langpack.pack("de-AT")
    assert at.chain == ["de", "de-AT"]
    assert at.recognition_language == "de"           # Whisper knows "de", not "de-AT"
    assert langpack.pack("de").recognition_language == "de"
    assert "de-AT" in langpack.languages()


def test_deeper_chain(packs):
    write(packs / "de-AT-x-wien", "language.json", {"base": "de-AT", "+filler_words": ["oida"]})
    v = langpack.pack("de-AT-x-wien")
    assert v.chain == ["de", "de-AT", "de-AT-x-wien"]
    assert {"gell", "oida", "und"} <= v.filler_words
    assert v.name == "de-AT-x-wien"                   # the name is not inherited
    assert v.recognition_language == "de"


def test_missing_or_circular_base_is_harmless(packs):
    write(packs / "xx", "language.json", {"base": "nope", "filler_words": ["a"]})
    write(packs / "yy", "language.json", {"base": "zz"})
    write(packs / "zz", "language.json", {"base": "yy"})
    assert langpack.pack("xx").filler_words == {"a"}
    assert langpack.pack("yy").chain == ["zz", "yy"]


def test_user_changes_apply_on_top_of_the_variant(packs, tmp_path):
    user = tmp_path / "user"
    write(user / "lang" / "de-AT", "language.json", {"filler_words": ["nur"]})
    langpack.configure(str(user))
    assert langpack.pack("de-AT").filler_words == {"nur"}
    assert "gell" in langpack.pack_list("de-AT", "filler_words")    # as the packs ship it


def test_save_list_compares_with_the_inherited_list(packs, tmp_path):
    langpack.configure(str(tmp_path / "user"))
    langpack.save_list("de-AT", "filler_words", langpack.pack_list("de-AT", "filler_words"))
    assert not (tmp_path / "user" / "lang" / "de-AT" / "language.json").exists() or \
        "filler_words" not in json.loads((tmp_path / "user" / "lang" / "de-AT" / "language.json").read_text())


def test_default_language_follows_the_user_interface():
    available = ["de", "de-AT", "en"]
    assert langpack.default_language("de", available) == "de"
    assert langpack.default_language("de-AT", available) == "de-AT"
    assert langpack.default_language("de_CH", available) == "de"       # a variant without a pack: its base
    assert langpack.default_language("en-US", available) == "en"
    assert langpack.default_language("fr", available) == "en"          # no pack: English
    assert langpack.default_language(None, available) == "en"
    assert langpack.default_language("fr", ["de"]) == "de"             # without English: any pack
