"""Speech recognition with faster-whisper in a fixed language."""

import time


def cuda_device_count():
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


class Transcriber:
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
            without_timestamps=True, hotwords=hotwords)
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
