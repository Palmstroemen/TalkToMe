# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tests for the synthetic confirmation and error tones."""

import numpy as np
import pytest

from talktome_service.tones import make_tone

SR = 16000


def zero_crossings(x):
    return int(np.count_nonzero(np.diff(np.signbit(x))))


@pytest.mark.parametrize("kind", ["ok", "error"])
def test_tone_shape(kind):
    tone = make_tone(kind, SR, volume=0.5)
    assert tone.dtype == np.float32
    assert 0.08 <= len(tone) / SR <= 0.4
    assert np.max(np.abs(tone)) <= 0.5 + 1e-6
    assert np.max(np.abs(tone)) > 0.3
    # fade in / out avoids clicks
    assert abs(tone[0]) < 0.01 and abs(tone[-1]) < 0.01


def test_error_tone_is_lower_than_ok_tone():
    ok, err = make_tone("ok", SR), make_tone("error", SR)
    assert zero_crossings(err) / len(err) < zero_crossings(ok) / len(ok)


def test_volume_zero_is_silent():
    assert not np.any(make_tone("ok", SR, volume=0.0))


def test_unknown_kind():
    with pytest.raises(ValueError):
        make_tone("fanfare", SR)
