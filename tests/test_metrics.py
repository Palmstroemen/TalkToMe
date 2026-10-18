"""Tests for the word error rate used by the measurement tool."""

import pytest

from talktome_service.metrics import best_wer, normalize, wer


def test_normalize():
    assert normalize("  Zwölf  Millimeter. ") == "zwölf millimeter"
    assert normalize("Schließe den Sketch!") == "schließe den sketch"
    assert normalize("Part-Design, bitte?") == "part design bitte"
    assert normalize("12,5 mm") == "12,5 mm"          # keep decimal commas


@pytest.mark.parametrize("ref, hyp, expected", [
    ("zeichne ein rechteck", "Zeichne ein Rechteck.", 0.0),
    ("zeichne ein rechteck", "zeichne einen rechteck", 1 / 3),     # substitution
    ("zeichne ein rechteck", "zeichne rechteck", 1 / 3),           # deletion
    ("zeichne ein rechteck", "zeichne ein großes rechteck", 1 / 3),  # insertion
    ("kreis", "", 1.0),
    ("", "", 0.0),
    ("", "hallo", 1.0),
])
def test_wer(ref, hyp, expected):
    assert wer(ref, hyp) == pytest.approx(expected)


def test_best_wer_takes_best_alternative():
    assert best_wer(["zwölf millimeter", "12 mm"], "12 mm") == 0.0
    assert best_wer(["zwölf millimeter", "12 mm"], "zwölf milimeter") == pytest.approx(0.5)
