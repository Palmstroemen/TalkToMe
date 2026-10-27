# SPDX-License-Identifier: LGPL-2.1-or-later
"""Speech recognition with faster-whisper in a fixed language."""

import time

import numpy as np

from talktome_service.profiles import select_profile


def cuda_device_count():
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


class Transcriber:
    # Spoken commands are short. Limiting the output stops Whisper's occasional
    # hallucination loops (measured: one 6.9 s outlier with hotwords, docs/phase0-results.md).
    MAX_NEW_TOKENS = 40

    def __init__(self, profile, language, beam_size=1, cpu_threads=0, download_root=None):
        from faster_whisper import WhisperModel
        self.profile = profile
        self.language = language
        self.beam_size = beam_size
        self.model = WhisperModel(profile.model, device=profile.device,
                                  compute_type=profile.compute_type,
                                  cpu_threads=cpu_threads, download_root=download_root)

    def transcribe(self, audio, hotwords=None):
        start = time.monotonic()
        segments, _ = self.model.transcribe(
            audio, language=self.language, beam_size=self.beam_size,
            vad_filter=False, condition_on_previous_text=False,
            without_timestamps=True, hotwords=hotwords, max_new_tokens=self.MAX_NEW_TOKENS)
        segments = list(segments)       # decoding happens while iterating
        stt_ms = int((time.monotonic() - start) * 1000)
        n = max(len(segments), 1)
        return {
            "text": " ".join(s.text.strip() for s in segments).strip(),
            "stt_ms": stt_ms,
            # Hints for telling commands from noise later (DESIGN.md 9.3).
            "no_speech_prob": round(max((s.no_speech_prob for s in segments), default=1.0), 3),
            "avg_logprob": round(sum(s.avg_logprob for s in segments) / n, 3),
        }


def load_transcriber(profile, language, model=None, log=print, make=Transcriber, **kwargs):
    """A Transcriber that has decoded once, so it works and the first command is fast.

    A GPU counts as found as soon as its driver is there, but decoding also needs the CUDA
    libraries (cuBLAS, cuDNN), which Windows in particular often lacks. They are only loaded on
    the first decoding: if it fails, the CPU profile takes over (DESIGN.md 12.1)."""
    try:
        transcriber = make(profile, language, **kwargs)
        transcriber.transcribe(np.zeros(16000, dtype=np.float32))
        return transcriber
    except Exception as e:
        if profile.device == "cpu":
            raise
        log("GPU not usable ({}), falling back to the CPU profile".format(e))
    cpu = select_profile("cpu", 0, model)
    cpu.fallback = True
    return make(cpu, language, **kwargs)
