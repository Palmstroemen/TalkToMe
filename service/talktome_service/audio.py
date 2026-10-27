# SPDX-License-Identifier: LGPL-2.1-or-later
"""Audio sources delivering float32 frames of FRAME samples at 16 kHz."""

import threading
import time
import wave

import numpy as np

SAMPLE_RATE = 16000
FRAME = 512


class Microphone:
    def __init__(self, device=None):
        self.device = device
        self._stream = None

    def start(self, callback):
        import sounddevice as sd

        def on_audio(indata, frames, time_info, status):
            callback(indata[:, 0].copy())

        self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                      blocksize=FRAME, device=self.device, callback=on_audio)
        self._stream.start()

    def stop(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()


def read_wav(path):
    """Read a 16 kHz mono 16-bit WAV file as float32 in [-1, 1]."""
    with wave.open(path, "rb") as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            raise ValueError("{}: need 16 kHz mono 16-bit WAV".format(path))
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def write_wav(path, audio):
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())


class WavSource:
    """Plays WAV files into the pipeline instead of a microphone (for tests and measurements)."""

    def __init__(self, paths, realtime=True, gap_s=1.5):
        self.paths = list(paths)
        self.realtime = realtime
        self.gap_s = gap_s
        self._running = False

    def start(self, callback):
        self._running = True
        threading.Thread(target=self._feed, args=(callback,), daemon=True).start()

    def stop(self):
        self._running = False

    def _feed(self, callback):
        gap = np.zeros(int(self.gap_s * SAMPLE_RATE), dtype=np.float32)
        audio = np.concatenate([gap] + [x for p in self.paths for x in (read_wav(p), gap)])
        audio = np.pad(audio, (0, -len(audio) % FRAME))
        for i in range(0, len(audio), FRAME):
            if not self._running:
                return
            callback(audio[i:i + FRAME])
            if self.realtime:
                time.sleep(FRAME / SAMPLE_RATE)
