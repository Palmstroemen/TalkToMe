# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tests for turning button texts and vocabulary files into phrases."""

import pytest

from ttm_core.vocabulary import clean_label, merge_phrases


@pytest.mark.parametrize("raw, clean", [
    ("&Rechteck", "Rechteck"),
    ("Rechteck...", "Rechteck"),
    ("Neue Skizze erstellen…", "Neue Skizze erstellen"),
    ("  Pad  ", "Pad"),
    ("Save &As...", "Save As"),
    ("Fit all (V, F)", "Fit all"),
    ("&&Copy", "&Copy"),
    ("", ""),
    ("...", ""),
])
def test_clean_label(raw, clean):
    assert clean_label(raw) == clean


def test_merge_phrases_order_and_dedupe():
    assert merge_phrases(["Klotz"], ["Polster", "extrudieren"], ["&Aufpolstern", "Pad...", "polster"]) == \
        ["Klotz", "Polster", "extrudieren", "Aufpolstern", "Pad"]


def test_merge_phrases_skips_empty():
    assert merge_phrases(None, [], ["", "..."]) == []
