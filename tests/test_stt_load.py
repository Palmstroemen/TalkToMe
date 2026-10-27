# SPDX-License-Identifier: LGPL-2.1-or-later
"""Loading the speech recognition: a GPU whose CUDA libraries are missing falls back to the CPU."""

from talktome_service.profiles import select_profile
from talktome_service.stt import load_transcriber


class FakeTranscriber:
    def __init__(self, profile, language, broken_on=(), broken_load=False, **kwargs):
        if broken_load and profile.device in broken_on:
            raise RuntimeError("Could not load library cudnn_ops64_9.dll")
        self.profile = profile
        self.broken = profile.device in broken_on

    def transcribe(self, audio, hotwords=None):
        if self.broken:
            raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
        return {"text": ""}


def make(broken_on=(), broken_load=False):
    return lambda profile, language, **kwargs: FakeTranscriber(profile, language, broken_on, broken_load, **kwargs)


def test_working_gpu_is_kept():
    t = load_transcriber(select_profile("auto", 1), "de", make=make())
    assert t.profile.device == "cuda"
    assert not t.profile.fallback


def test_gpu_without_cuda_libraries_falls_back_to_cpu():
    logged = []
    t = load_transcriber(select_profile("auto", 1), "de", log=logged.append, make=make(broken_on=("cuda",)))
    assert (t.profile.device, t.profile.compute_type) == ("cpu", "int8")
    assert t.profile.model == "base"            # the CPU's default model, the GPU's is too slow there
    assert t.profile.fallback
    assert any("cublas64_12.dll" in line for line in logged)


def test_gpu_failing_to_load_falls_back_to_cpu():
    t = load_transcriber(select_profile("auto", 1), "de", make=make(broken_on=("cuda",), broken_load=True))
    assert t.profile.device == "cpu" and t.profile.fallback


def test_chosen_model_stays_on_fallback():
    t = load_transcriber(select_profile("auto", 1, model="small"), "de", model="small",
                         make=make(broken_on=("cuda",)))
    assert t.profile.model == "small"


def test_cpu_failure_is_not_hidden():
    import pytest
    with pytest.raises(RuntimeError):
        load_transcriber(select_profile("cpu", 0), "de", make=make(broken_on=("cpu",)))
