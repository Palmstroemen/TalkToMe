"""Tests for the sentences of the speech output (DESIGN.md 10.1)."""

import pytest

from ttm_core.speech import LEVELS, phrase


def test_levels():
    assert LEVELS == ("off", "important", "chatty")


def test_important_message_at_default_level():
    assert phrase("not_understood", "de", "important") == "Das habe ich nicht verstanden."


def test_nothing_when_off():
    assert phrase("not_understood", "de", "off") is None


def test_chatty_message_only_when_chatty():
    assert phrase("done", "de", "important") is None
    assert phrase("done", "de", "chatty") in ("Mache ich.", "Okay.", "Erledigt.")


def test_values_are_filled_in():
    assert phrase("ambiguous", "de", "important", first="XY-Ebene", second="YZ-Ebene") == \
        "Meinst du XY-Ebene oder YZ-Ebene?"


def test_variants_take_turns():
    said = {phrase("done", "de", "chatty", turn=i) for i in range(3)}
    assert len(said) == 3


def test_english():
    assert phrase("not_understood", "en", "important") == "Sorry, I didn't get that."


@pytest.mark.parametrize("kind", ["nonsense", ""])
def test_unknown_kind(kind):
    assert phrase(kind, "de", "chatty") is None


def test_unknown_language():
    assert phrase("not_understood", "xx", "chatty") is None
