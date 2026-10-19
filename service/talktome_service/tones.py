"""Synthetic confirmation and error tones. See DESIGN.md, section 10."""

import threading

import numpy as np

# Two short notes each: rising for "ok", falling and lower for "error".
TONES = {
    "ok":    [(880.0, 0.07), (1320.0, 0.07)],
    "error": [(330.0, 0.10), (220.0, 0.12)],
}
FADE_S = 0.008


def make_tone(kind, sample_rate, volume=0.4):
    if kind not in TONES:
        raise ValueError("unknown tone {!r}".format(kind))
    parts = []
    for freq, dur in TONES[kind]:
        t = np.arange(int(sample_rate * dur)) / sample_rate
        note = np.sin(2 * np.pi * freq * t)
        fade = min(int(sample_rate * FADE_S), len(t) // 2)
        env = np.ones_like(note)
        ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fade))
        env[:fade], env[len(env) - fade:] = ramp, ramp[::-1]
        parts.append(note * env)
    return (np.concatenate(parts) * volume).astype(np.float32)


class TonePlayer:
    """Plays tones through one output stream that stays open.

    Opening a stream per tone caused ALSA buffer underruns (crackling) on Linux; an open
    stream whose callback writes silence between tones avoids them.

    play() returns how long the tone keeps the speaker busy (output latency + duration),
    so the caller can mute the microphone for that time. Volume 0 plays nothing.
    """

    # Output latency in seconds. Lower values caused buffer underruns on a Linux laptop
    # (ALSA "default" device); 0.1 s ran without underruns.
    LATENCY_S = 0.1

    def __init__(self, sample_rate=44100, volume=0.4):
        self.sample_rate = sample_rate
        self.volume = volume
        self._pending = np.zeros(0, dtype=np.float32)
        self._lock = threading.Lock()
        self._stream = None

    def _callback(self, outdata, frames, time_info, status):
        with self._lock:
            n = min(frames, len(self._pending))
            outdata[:n, 0] = self._pending[:n]
            outdata[n:, 0] = 0.0
            self._pending = self._pending[n:]

    def _ensure_stream(self):
        if self._stream is None:
            import sounddevice as sd
            self._stream = sd.OutputStream(samplerate=self.sample_rate, channels=1, dtype="float32",
                                           callback=self._callback, latency=self.LATENCY_S)
            self._stream.start()

    def play(self, kind):
        tone = make_tone(kind, self.sample_rate, self.volume)
        if self.volume <= 0:
            return 0.0
        self._ensure_stream()
        with self._lock:
            self._pending = tone
        return self._stream.latency + len(tone) / self.sample_rate

    def resample(self, audio, rate):
        """To the player's sample rate (linear interpolation is good enough for speech)."""
        if rate == self.sample_rate:
            return audio.astype(np.float32)
        n = int(round(len(audio) * self.sample_rate / rate))
        return np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)

    def play_samples(self, audio, rate):
        """Play audio (e.g. speech) at rate; returns how long the speaker is busy, like play()."""
        if self.volume <= 0:
            return 0.0
        samples = self.resample(audio, rate) * min(1.0, self.volume * 2.5)
        self._ensure_stream()
        with self._lock:
            self._pending = samples
        return self._stream.latency + len(samples) / self.sample_rate

    def close(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
