# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tests for values spoken while a tool waits for them (DESIGN.md 6.5): "50 mal 30", "Höhe 30"."""

import pytest

from ttm_core.values import parse_values


@pytest.mark.parametrize("text, values", [
    ("50 mal 30", [(None, 50.0, "length"), (None, 30.0, "length")]),
    ("50 x 30", [(None, 50.0, "length"), (None, 30.0, "length")]),
    ("Breite 50, Höhe 30", [(0, 50.0, "length"), (1, 30.0, "length")]),
    ("Höhe 30 und Breite 50", [(1, 30.0, "length"), (0, 50.0, "length")]),
    ("Länge 40", [(0, 40.0, "length")]),
    ("Radius 20 mm", [(0, 20.0, "radius")]),
    ("12,5", [(None, 12.5, "length")]),
    ("12.5 mm", [(None, 12.5, "length")]),
    ("5 cm", [(None, 50.0, "length")]),
    ("zwei Meter", [(None, 2000.0, "length")]),
    ("zwölf mal fünf", [(None, 12.0, "length"), (None, 5.0, "length")]),
    ("Zeichne ein Rechteck 50 mal 30", [(None, 50.0, "length"), (None, 30.0, "length")]),
    ("minus 10", [(None, -10.0, "length")]),
])
def test_values(text, values):
    assert parse_values(text, "de") == values


@pytest.mark.parametrize("text", ["Rechteck", "Mach eine Fase", "", "und zwar von hier"])
def test_no_values(text):
    assert parse_values(text, "de") == []


@pytest.mark.parametrize("text, values", [
    ("50 by 30", [(None, 50.0, "length"), (None, 30.0, "length")]),
    ("width 50, height 30", [(0, 50.0, "length"), (1, 30.0, "length")]),
    ("two inches", [(None, 50.8, "length")]),
])
def test_english(text, values):
    assert parse_values(text, "en") == values


def test_article_counts_only_with_unit_or_name():
    assert parse_values("ein Meter", "de") == [(None, 1000.0, "length")]
    assert parse_values("Höhe eine", "de") == [(1, 1.0, "length")]


@pytest.mark.parametrize("text, values", [
    ("40 mm und 30 Grad", [(None, 40.0, "length"), (None, 30.0, "angle")]),
    ("Länge 40, Winkel 30", [(0, 40.0, "length"), (None, 30.0, "angle")]),
    ("Durchmesser 40", [(0, 40.0, "length")]),
])
def test_angles_and_radius(text, values):
    assert parse_values(text, "de") == values


from ttm_core.values import only_values   # noqa: E402


@pytest.mark.parametrize("text", ["Breite 50", "Höhe 30", "12 mm", "30 Grad", "50 mal 30", "minus 10",
                                  "und die Höhe 30", "Radius zwölf", "Länge 12,5 mm bitte"])
def test_only_values(text):
    assert only_values(text, "de")


@pytest.mark.parametrize("text", ["Zeichne ein Rechteck 50 mal 30", "Breite", "Speichern", "Aufpolsterung 12 mm",
                                  "ein Rechteck", ""])
def test_not_only_values(text):
    assert not only_values(text, "de")


def test_only_values_english():
    assert only_values("width 50", "en") and only_values("height 30 mm", "en")
    assert not only_values("pad 12 mm", "en")
