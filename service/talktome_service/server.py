# SPDX-License-Identifier: LGPL-2.1-or-later
"""Socket server tying microphone, VAD, segmenter, speech recognition and tones together.

All hardware-facing parts are passed in, so the service can be tested with fakes:

  source       start(callback) / stop()   delivers float32 frames of FRAME samples at SAMPLE_RATE
  vad          prob(frame) / reset()      speech probability of one frame
  transcriber  transcribe(audio) -> {"text": ..., "stt_ms": ..., ...}
  tones        play(kind) -> seconds      kind is "ok" or "error"
               play_samples(audio, rate) -> seconds
  speaker      synth(text) -> (audio, rate)  speech output (Piper), optional
"""

import queue
import socket
import threading
import time

import numpy as np

from talktome_service.segmenter import Segmenter
from ttm_core.context import CHOOSE, LEVELS
from ttm_core.decision import decide
from ttm_core.matching import hotwords
from ttm_core.protocol import LineDecoder, check_hello, encode, make_message
from ttm_core.sequence import VALUES, start_utterance, step, values_step
from ttm_core.speech import phrase


SAMPLE_RATE = 16000
FRAME = 512
FRAME_MS = FRAME * 1000 // SAMPLE_RATE
MUTE_AFTER_TONE_S = 0.15     # keep the microphone deaf a bit longer than the tone itself
SYSTEM_MUTE_FRAMES = 500 // FRAME_MS   # exact digital silence this long: muted by the system


class Service:
    def __init__(self, token, source, vad, transcriber, tones, segmenter=None,
                 host="127.0.0.1", port=0, info=None, log=print, speaker=None, speech_level="off"):
        self.token = token
        self.source = source
        self.vad = vad
        self.transcriber = transcriber
        self.tones = tones
        self.speaker = speaker
        self.speech_level = speech_level
        self._turn = 0                        # variants of a sentence take turns
        self._greeted = False
        self.segmenter = segmenter or Segmenter(frame_ms=FRAME_MS)
        self.host, self.port = host, port
        self.info = info or {}
        self.log = log

        self._frames = queue.Queue(maxsize=1000)
        self._utterances = queue.Queue()
        self._client = None
        self._send_lock = threading.Lock()
        self._listening = False
        self._hotwords = None
        self._candidates = None      # None: no decisions, only transcripts (Phase 0 behavior)
        self._training = False       # training: only transcripts, nothing is decided or executed
        self._patterns = None        # learned sentence patterns {command: [templates]}
        self._tool = {}              # the running tool, e.g. {"running": True}: it takes spoken values
        self.language = self.info.get("language")
        self._mute_until = 0.0
        self._zero_frames = 0
        self._system_muted = False            # microphone muted by the system, e.g. a keyboard key
        self._seq_lock = threading.Lock()     # the sequence advances from the STT and the client thread
        self._pending = []                    # clauses of the current utterance not decided yet
        self._utterance = ""
        self._utterance_id = 0
        self._step_id = 0
        self._awaiting = None                 # id of the plan the addon is executing
        self._steps = 0
        self._last_span = None                # clause(s) of the step just executed, for a follow-up
        self._stop = threading.Event()
        self._threads = []

    # --- lifecycle -------------------------------------------------------------------

    def start(self):
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, self.port))
        self._server.listen(1)
        self._server.settimeout(0.2)
        self.port = self._server.getsockname()[1]
        for target in (self._accept_loop, self._process_loop, self._stt_loop):
            t = threading.Thread(target=target, daemon=True)
            t.start()
            self._threads.append(t)
        return self.port

    def stop(self):
        self._stop.set()
        self._set_listening(False, notify=False)
        self._close_client()
        self._server.close()
        for t in self._threads:
            t.join(timeout=2)

    def wait(self):
        while not self._stop.is_set():
            self._stop.wait(0.5)

    # --- connection ------------------------------------------------------------------

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            # Only one client at a time: a new connection replaces the old one.
            self._close_client()
            threading.Thread(target=self._client_loop, args=(conn,), daemon=True).start()

    def _client_loop(self, conn):
        decoder = LineDecoder()
        authenticated = False
        conn.settimeout(0.2)
        try:
            while not self._stop.is_set():
                try:
                    data = conn.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break
                for msg in decoder.feed(data):
                    if not authenticated:
                        if not check_hello(msg, self.token):
                            self.log("rejected client: no valid hello")
                            return
                        authenticated = True
                        self._client = conn
                        self.language = msg.get("language") or self.language
                        self.send("welcome", **self.info)
                        self.send("state", state=self._listen_state())
                        continue
                    self._dispatch(msg)
        except OSError:
            pass
        finally:
            if self._client is conn:
                self._client = None
                self._set_listening(False, notify=False)
            conn.close()

    def _close_client(self):
        conn, self._client = self._client, None
        if conn is not None:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def send(self, type_, **fields):
        conn = self._client
        if conn is None:
            return
        with self._send_lock:
            try:
                conn.sendall(encode(make_message(type_, **fields)))
            except OSError:
                pass

    def _dispatch(self, msg):
        kind = msg["type"]
        if kind == "listen":
            self._set_listening(bool(msg.get("on")))
        elif kind == "context":
            self._set_context(msg)
        elif kind == "train":
            self._training = bool(msg.get("on"))
        elif kind == "result":
            self._on_result(msg)
        elif kind == "say":
            values = {k: v for k, v in msg.items() if k not in ("type", "kind")}
            self._say(msg.get("kind", ""), **values)
        elif kind == "bye":
            self._stop.set()
        else:
            self.log("ignored message: {}".format(kind))

    def _set_context(self, msg):
        """Candidates for decisions; their phrases (higher levels first) also become hotwords."""
        candidates = msg.get("candidates")
        if candidates is not None:
            self._candidates = candidates
        if "patterns" in msg:
            self._patterns = msg["patterns"]
        if "tool" in msg:
            self._tool = msg["tool"] or {}
        words = msg.get("hotwords")
        if words is None and candidates is not None:
            order = {level: i for i, level in enumerate(LEVELS)}
            ranked = sorted(candidates, key=lambda c: order.get(c.get("level"), len(LEVELS)))
            words = [p for c in ranked for p in c.get("phrases", [])]
        if words is not None:
            self._hotwords = hotwords(words)

    # --- audio pipeline --------------------------------------------------------------

    def _set_listening(self, on, notify=True):
        if on and not self._listening:
            self.segmenter.reset()
            self.vad.reset()
            self._zero_frames, self._system_muted = 0, False
            self._listening = True
            self.source.start(self._on_frame)
            if not self._greeted:
                self._greeted = self._say("ready")
        elif not on and self._listening:
            self._listening = False
            self.source.stop()
        if notify:
            self.send("state", state=self._listen_state())

    def _listen_state(self):
        if not self._listening:
            return "idle"
        return "muted" if self._system_muted else "listening"

    def _on_frame(self, frame):
        try:
            self._frames.put_nowait(frame)
        except queue.Full:
            pass

    def _process_loop(self):
        while not self._stop.is_set():
            try:
                frame = self._frames.get(timeout=0.2)
            except queue.Empty:
                continue
            if not self._listening:
                continue
            utterance = self._process_frame(frame)
            if utterance is not None:
                self._utterances.put(utterance)

    def _process_frame(self, frame, prob=None):
        """Run one frame through VAD and segmenter. Returns a finished utterance or None.

        While a tone plays, frames count as silence: the tone can't start an utterance,
        but the frames stay in the pre-roll, so speech beginning during the tone keeps its start.
        """
        if not frame.any():
            # A muted microphone (system setting or keyboard key) delivers exact zeros, real
            # input always has some noise. No speech in there: skip the VAD.
            self._zero_frames += 1
            if self._zero_frames >= SYSTEM_MUTE_FRAMES and not self._system_muted:
                self._system_muted = True
                self.send("state", state="muted")
            prob = 0.0
        else:
            self._zero_frames = 0
            if self._system_muted:
                self._system_muted = False
                self.send("state", state="listening")
        if prob is None:
            prob = self.vad.prob(frame)
        if time.monotonic() < self._mute_until:
            prob = 0.0
        was_speaking = self.segmenter.in_speech
        utterance = self.segmenter.push(frame, prob)
        if self.segmenter.in_speech and not was_speaking:
            # The addon takes its context snapshot now (mouse position, selection, DESIGN.md 6.4).
            self.send("speech_start")
        return utterance

    def _stt_loop(self):
        while not self._stop.is_set():
            try:
                utterance = self._utterances.get(timeout=0.2)
            except queue.Empty:
                continue
            audio = np.concatenate(utterance.frames).astype(np.float32)
            self.send("state", state="processing")
            start = time.monotonic()
            try:
                result = dict(self.transcriber.transcribe(audio, hotwords=self._hotwords))
            except Exception as e:      # keep the service alive
                self.log("transcription failed: {}".format(e))
                self.send("error", message="transcription failed: {}".format(e))
                result = None
            if result is not None:
                result.setdefault("stt_ms", int((time.monotonic() - start) * 1000))
                result.update(audio_ms=int(len(audio) * 1000 / SAMPLE_RATE),
                              speech_ms=utterance.speech_ms, truncated=utterance.truncated)
                self.send("transcript", **result)
                if self._candidates is not None and not self._training:
                    self._decide(result["text"])
            self.send("state", state=self._listen_state())

    # --- decisions and sequences (DESIGN.md 7) --------------------------------------------

    def _decide(self, text):
        """Start a new utterance; it replaces what is left of the previous one."""
        with self._seq_lock:
            self._utterance = text
            self._utterance_id += 1
            self._pending = []
            self._awaiting = None
            self._last_span = None
            self._steps = 0
            if self._candidates is not None:
                self._pending, ignored = start_utterance(text, self._candidates, self.language,
                                                         self._patterns, self._tool.get("running"))
                if ignored is not None:
                    self.send("ignored", reason=ignored.reason, text=text)
                    return
            self._advance()

    def _on_result(self, msg):
        with self._seq_lock:
            if self._awaiting is None and "id" not in msg:
                self._play("ok" if msg.get("ok") else "error")      # a result without a plan
                return
            if self._awaiting is None or msg.get("id", self._awaiting) != self._awaiting:
                return                         # result of a step that is no longer current
            self._awaiting = None
            if not msg.get("ok"):
                self._pending = []
                self._say("failed") or self._play("error")
                return
            if self._follow_up():
                return
            last = self._advance()
            if self._awaiting is None and (last is None or last.kind == "ignore"):
                self._say("done") or self._play("ok")     # all steps done

    def _follow_up(self):
        """Did the step open a dialog asking for what its clause said already? "Mach eine Skizze
        in der XY-Ebene": the sketch command opens the plane choice, the clause names the plane.
        Sends the choice as one more step; uses the addon's context sent before its result."""
        span, self._last_span = self._last_span, None
        if span is None:
            return False
        choices = [c for c in self._candidates or [] if c["id"].startswith(CHOOSE)]
        d = decide(span, choices, self.language) if choices else None
        if d is None or d.kind != "execute":
            d = self._values(span)             # "Zeichne ein Rechteck 50 mal 30": the tool runs now
        if d is None or d.kind != "execute":
            return False
        self._send_step(d, span)
        return True

    def _values(self, clause):
        """Values for the running tool (DESIGN.md 6.5), or None."""
        return values_step(clause, self.language, self._tool.get("running"))

    def _send_step(self, d, span):
        self._step_id += 1
        self._awaiting = self._step_id
        self._steps += 1
        self.send("plan", id=self._step_id, more=bool(self._pending), text=span,
                  utterance=self._utterance, utterance_id=self._utterance_id, command=d.command,
                  args=d.args, score=d.score, level=d.level, alternatives=d.alternatives, via=d.via)

    def _advance(self):
        """Decide clauses until one step is sent, the sequence fails, or nothing is left.

        Returns the last decision. Talk between the steps is skipped silently; an unclear clause
        ends the sequence with the error tone: the later steps would run in an unexpected state.
        """
        last = None
        while self._pending and self._candidates is not None:
            d, n = step(self._pending, self._candidates, self.language, self._patterns, self._tool.get("running"))
            span, self._pending = ", ".join(self._pending[:n]), self._pending[n:]
            last = d
            info = dict(text=span, utterance=self._utterance, utterance_id=self._utterance_id,
                        command=d.command, args=d.args, score=d.score, level=d.level,
                        alternatives=d.alternatives, via=d.via)
            if d.kind == "execute":
                # A step may open a dialog asking for what its clause said; a choice is the answer.
                self._last_span = None if d.command.startswith(CHOOSE) or d.command == VALUES else span
                self._send_step(d, span)
                return d                       # the addon executes and answers with "result"
            if d.kind == "not_understood":
                self._pending = []
                self.send("not_understood", reason=d.reason, **info)
                self._say_not_understood(d) or self._play("error")
                return d
            self.send("ignored", reason=d.reason, text=span, utterance=self._utterance)
        return last

    # --- speech output (DESIGN.md 10.1) -----------------------------------------------------

    def _label(self, command):
        for c in self._candidates or []:
            if c["id"] == command:
                return c.get("label") or (c.get("phrases") or [command])[0]
        return command

    def _say_not_understood(self, d):
        names = [self._label(cmd) for cmd, _ in d.alternatives]
        if d.reason == "ambiguous" and len(names) >= 2:
            return self._say("ambiguous", first=names[0], second=names[1])
        if d.reason == "inactive" and names:
            return self._say("inactive", first=names[0])
        return self._say("not_understood")

    def _say(self, kind, **values):
        """Say the sentence for kind, if the speech level asks for it. True if something is said;
        the microphone stays deaf meanwhile."""
        if self.speaker is None:
            return False
        text = phrase(kind, self.language, self.speech_level, turn=self._turn, **values)
        if text is None:
            return False
        self._turn += 1
        try:
            audio, rate = self.speaker.synth(text)
            duration = self.tones.play_samples(audio, rate)
        except Exception as e:
            self.log("speech failed: {}".format(e))
            return False
        self._mute_until = time.monotonic() + duration + MUTE_AFTER_TONE_S
        self.send("said", text=text)
        return True

    def _play(self, kind):
        try:
            duration = self.tones.play(kind)
        except Exception as e:
            self.log("tone failed: {}".format(e))
            return
        self._mute_until = time.monotonic() + duration + MUTE_AFTER_TONE_S
