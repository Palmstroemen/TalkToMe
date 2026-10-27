# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tests for cutting a stream of VAD probabilities into utterances."""

import pytest

from talktome_service.segmenter import Segmenter

SPEECH, SILENCE = 0.9, 0.05


def run(segmenter, probs):
    """Feed one frame per probability; frames are their own index."""
    utterances = []
    for i, p in enumerate(probs):
        u = segmenter.push(i, p)
        if u is not None:
            utterances.append(u)
    return utterances


def make(**kw):
    # 10 ms frames make the arithmetic in the tests easy to follow.
    defaults = dict(frame_ms=10, threshold=0.5, start_ms=30, end_silence_ms=100,
                    min_speech_ms=50, max_utterance_ms=1000, pre_roll_ms=40, post_roll_ms=20)
    defaults.update(kw)
    return Segmenter(**defaults)


def test_silence_gives_nothing():
    assert run(make(), [SILENCE] * 200) == []


def test_short_noise_gives_nothing():
    assert run(make(), [SILENCE] * 10 + [SPEECH] * 2 + [SILENCE] * 50) == []


def test_one_utterance_with_pre_and_post_roll():
    probs = [SILENCE] * 10 + [SPEECH] * 20 + [SILENCE] * 30
    [u] = run(make(), probs)
    # speech is frames 10..29; pre-roll 4 frames (6..9), post-roll 2 frames (30, 31)
    assert u.frames == list(range(6, 32))
    assert u.speech_ms == 200
    assert not u.truncated


def test_utterance_ends_only_after_end_silence():
    seg = make()
    probs = [SPEECH] * 20 + [SILENCE] * 9
    assert run(seg, probs) == []          # 90 ms silence < 100 ms
    assert seg.push(99, SILENCE) is not None


def test_short_pause_does_not_split():
    probs = [SPEECH] * 20 + [SILENCE] * 5 + [SPEECH] * 20 + [SILENCE] * 30
    [u] = run(make(), probs)
    assert u.speech_ms == 400


def test_too_short_speech_is_discarded():
    probs = [SILENCE] * 5 + [SPEECH] * 4 + [SILENCE] * 30     # 40 ms < min 50 ms
    assert run(make(), probs) == []


def test_hysteresis_keeps_utterance_alive():
    # 0.4 is below the start threshold, but above the default end threshold (0.35)
    probs = [SPEECH] * 10 + [0.4] * 30 + [SILENCE] * 30
    [u] = run(make(), probs)
    assert u.speech_ms == 400


def test_weak_signal_does_not_start_utterance():
    assert run(make(), [0.4] * 100) == []


def test_max_length_truncates():
    probs = [SPEECH] * 150 + [SILENCE] * 30
    utterances = run(make(max_utterance_ms=1000), probs)
    assert utterances[0].truncated
    assert len(utterances[0].frames) == 100
    # the rest of the speech becomes a second utterance
    assert len(utterances) == 2
    assert not utterances[1].truncated


def test_reset_drops_running_utterance():
    seg = make()
    run(seg, [SPEECH] * 20)
    seg.reset()
    assert run(seg, [SILENCE] * 30) == []


def test_invalid_config():
    with pytest.raises(ValueError):
        make(frame_ms=0)
    with pytest.raises(ValueError):
        make(end_threshold=0.6)        # above the start threshold


def test_in_speech_reports_running_utterance():
    seg = make()
    assert not seg.in_speech
    run(seg, [SPEECH] * 3)
    assert seg.in_speech
    run(seg, [SILENCE] * 10)
    assert not seg.in_speech
