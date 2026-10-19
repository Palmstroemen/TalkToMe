"""Tests for finding a document object by its spoken name (DESIGN.md 7, Umbenennen)."""

import pytest

from ttm_core.objects import find_object

LABELS = ["Körper", "Körper001", "Körper002", "Skizze", "Skizze001", "Bodenplatte", "XY-Ebene"]


@pytest.mark.parametrize("spoken, label", [
    ("Körper", "Körper"),
    ("Körper2", "Körper002"),
    ("Körper 2", "Körper002"),
    ("Körper zwei", "Körper002"),
    ("körper eins", "Körper001"),
    ("Skizze 1", "Skizze001"),
    ("Bodenplatte", "Bodenplatte"),
    ("Bodenplate", "Bodenplatte"),          # misheard a little
    ("XY Ebene", "XY-Ebene"),
])
def test_find(spoken, label):
    assert find_object(spoken, LABELS, "de") == label


@pytest.mark.parametrize("spoken", ["Deckel", "Körper 7", ""])
def test_not_found(spoken):
    assert find_object(spoken, LABELS, "de") is None
