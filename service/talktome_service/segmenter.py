# SPDX-License-Identifier: LGPL-2.1-or-later
"""Cut a continuous stream of audio frames into utterances, using VAD probabilities.

Pure logic: frames are opaque objects, so this module needs neither numpy nor audio.
"""

from collections import deque
from dataclasses import dataclass, field


@dataclass
class Utterance:
    frames: list = field(default_factory=list)
    speech_ms: int = 0
    truncated: bool = False      # cut off at max_utterance_ms


class Segmenter:
    """State machine: idle -> speech (after start_ms of speech) -> idle (after end_silence_ms).

    threshold      probability needed to start an utterance
    end_threshold  probability below which a frame counts as silence while speaking
                   (hysteresis; defaults to threshold - 0.15)
    pre_roll_ms    audio kept from before the detected start, so the first syllable isn't cut
    post_roll_ms   silence kept after the end of speech
    """

    def __init__(self, frame_ms=32, threshold=0.5, end_threshold=None, start_ms=96,
                 end_silence_ms=640, min_speech_ms=250, max_utterance_ms=8000,
                 pre_roll_ms=320, post_roll_ms=160):
        if frame_ms <= 0:
            raise ValueError("frame_ms must be positive")
        if end_threshold is None:
            end_threshold = max(0.0, threshold - 0.15)
        if end_threshold > threshold:
            raise ValueError("end_threshold must not be above threshold")
        frames = lambda ms: max(1, round(ms / frame_ms))
        self.frame_ms = frame_ms
        self.threshold = threshold
        self.end_threshold = end_threshold
        self.start_frames = frames(start_ms)
        self.end_frames = frames(end_silence_ms)
        self.min_speech_frames = frames(min_speech_ms)
        self.max_frames = frames(max_utterance_ms)
        self.pre_frames = round(pre_roll_ms / frame_ms)
        self.post_frames = round(post_roll_ms / frame_ms)
        self.reset()

    def reset(self):
        self._ring = deque(maxlen=self.pre_frames + self.start_frames)
        self._speech_run = 0
        self._current = None
        self._speech_count = 0
        self._silence_run = 0

    @property
    def in_speech(self):
        """True while an utterance is being recorded."""
        return self._current is not None

    def push(self, frame, prob):
        """Add one frame. Returns a finished Utterance or None."""
        if self._current is None:
            return self._push_idle(frame, prob)
        return self._push_speech(frame, prob)

    def _push_idle(self, frame, prob):
        self._ring.append(frame)
        self._speech_run = self._speech_run + 1 if prob >= self.threshold else 0
        if self._speech_run >= self.start_frames:
            keep = min(len(self._ring), self.pre_frames + self._speech_run)
            self._current = list(self._ring)[-keep:]
            self._speech_count = self._speech_run
            self._silence_run = 0
            self._ring.clear()
            self._speech_run = 0
        return None

    def _push_speech(self, frame, prob):
        self._current.append(frame)
        if prob >= self.end_threshold:
            self._speech_count += 1
            self._silence_run = 0
        else:
            self._silence_run += 1

        if self._silence_run >= self.end_frames:
            drop = self._silence_run - self.post_frames
            frames = self._current[:-drop] if drop > 0 else self._current
            return self._finish(frames, truncated=False)
        if len(self._current) >= self.max_frames:
            return self._finish(self._current, truncated=True)
        return None

    def _finish(self, frames, truncated):
        speech = self._speech_count
        self.reset()
        if speech < self.min_speech_frames:
            return None
        return Utterance(frames=list(frames), speech_ms=speech * self.frame_ms, truncated=truncated)
