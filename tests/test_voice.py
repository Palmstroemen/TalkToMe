# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tests for finding and loading Piper voices (DESIGN.md 10.1); no download, no model."""

import numpy as np
import pytest

from talktome_service.tones import TonePlayer
from talktome_service.voice import LazySpeaker, voice_files, voice_url


def test_url_of_a_voice_name():
    assert voice_url("de_DE-thorsten-medium", ".onnx") == (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx")


def test_bad_voice_name():
    with pytest.raises(ValueError):
        voice_url("thorsten", ".onnx")


def test_a_path_is_used_as_is(tmp_path):
    model = tmp_path / "glados.onnx"
    model.write_bytes(b"x")
    assert voice_files(str(model), str(tmp_path / "cache")) == (str(model), str(model) + ".json")


def test_a_name_lives_in_the_cache(tmp_path):
    assert voice_files("de_DE-thorsten-medium", str(tmp_path)) == (
        str(tmp_path / "de_DE-thorsten-medium.onnx"), str(tmp_path / "de_DE-thorsten-medium.onnx.json"))


def test_lazy_speaker_is_not_ready_without_a_voice():
    speaker = LazySpeaker(None, cache_dir=None, log=lambda *a: None)
    with pytest.raises(RuntimeError):
        speaker.synth("Hallo")


def test_samples_are_resampled_to_the_player_rate():
    player = TonePlayer(sample_rate=44100, volume=0)       # volume 0: nothing is played
    assert player.play_samples(np.zeros(22050, dtype=np.float32), 22050) == 0.0
    resampled = player.resample(np.ones(22050, dtype=np.float32), 22050)
    assert len(resampled) == 44100
