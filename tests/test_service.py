"""Integration test of the speech service with fake microphone, VAD, recognizer and tones."""

import socket
import threading
import time

import numpy as np
import pytest

from talktome_service.server import Service
from ttm_core.protocol import VERSION, LineDecoder, encode, make_message

TOKEN = "secret"
FRAME = 512
SPEECH_PATTERN = [0.0] * 10 + [0.9] * 20 + [0.0] * 30


class FakeSource:
    def __init__(self, n_frames):
        self.n_frames = n_frames
        self.running = False
        self.starts = 0

    def start(self, callback):
        self.running = True
        self.starts += 1
        def feed():
            for _ in range(self.n_frames):
                if not self.running:
                    return
                callback(np.zeros(FRAME, dtype=np.float32))
        threading.Thread(target=feed, daemon=True).start()

    def stop(self):
        self.running = False


class FakeVAD:
    def __init__(self, probs):
        self.probs = list(probs)

    def prob(self, frame):
        return self.probs.pop(0) if self.probs else 0.0

    def reset(self):
        pass


class FakeTranscriber:
    def __init__(self, text):
        self.text = text
        self.samples = []
        self.hotwords = []

    def transcribe(self, audio, hotwords=None):
        self.samples.append(len(audio))
        self.hotwords.append(hotwords)
        return {"text": self.text, "stt_ms": 5}


class FakeTones:
    def __init__(self):
        self.played = []

    def play(self, kind):
        self.played.append(kind)
        return 0.01


class Client:
    def __init__(self, port):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.decoder = LineDecoder()
        self.pending = []

    def send(self, type_, **fields):
        self.sock.sendall(encode(make_message(type_, **fields)))

    def wait_for(self, type_, timeout=5, **match):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for msg in list(self.pending):
                self.pending.remove(msg)
                if msg["type"] == type_ and all(msg.get(k) == v for k, v in match.items()):
                    return msg
            data = self.sock.recv(4096)
            if not data:
                raise ConnectionError("closed by service")
            self.pending.extend(self.decoder.feed(data))
        raise TimeoutError(type_)

    def is_closed(self, timeout=5):
        self.sock.settimeout(timeout)
        try:
            while True:
                data = self.sock.recv(4096)
                if not data:
                    return True
                self.pending.extend(self.decoder.feed(data))
        except ConnectionResetError:
            return True
        except socket.timeout:
            return False

    def close(self):
        self.sock.close()


@pytest.fixture
def parts():
    return {
        "source": FakeSource(len(SPEECH_PATTERN)),
        "vad": FakeVAD(SPEECH_PATTERN),
        "transcriber": FakeTranscriber("Zeichne ein Rechteck"),
        "tones": FakeTones(),
    }


@pytest.fixture
def service(parts):
    s = Service(token=TOKEN, log=lambda *a: None, **parts)
    s.start()
    yield s
    s.stop()


def connect(service):
    c = Client(service.port)
    c.send("hello", token=TOKEN, version=VERSION, language="de")
    c.wait_for("state", state="idle")
    return c


def test_transcript_after_listen_on(service, parts):
    c = connect(service)
    c.send("listen", on=True)
    c.wait_for("state", state="listening")
    msg = c.wait_for("transcript")
    assert msg["text"] == "Zeichne ein Rechteck"
    assert msg["audio_ms"] > 0 and msg["speech_ms"] > 0
    assert parts["transcriber"].samples and parts["transcriber"].samples[0] % FRAME == 0
    c.close()


def test_context_hotwords_reach_the_recognizer(service, parts):
    c = connect(service)
    c.send("context", hotwords=["Rechteck", "Kreis", "rechteck"])
    c.send("listen", on=True)
    c.wait_for("transcript")
    assert parts["transcriber"].hotwords[-1] == "Rechteck, Kreis"
    c.close()


def test_result_plays_tone(service, parts):
    c = connect(service)
    c.send("result", ok=True)
    c.send("result", ok=False)
    deadline = time.monotonic() + 5
    while len(parts["tones"].played) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert parts["tones"].played == ["ok", "error"]
    c.close()


def test_listen_off_stops_source(service, parts):
    c = connect(service)
    c.send("listen", on=True)
    c.wait_for("state", state="listening")
    c.send("listen", on=False)
    c.wait_for("state", state="idle")
    assert not parts["source"].running
    c.close()


def test_wrong_token_is_rejected(service, parts):
    c = Client(service.port)
    c.send("hello", token="wrong", version=VERSION)
    assert c.is_closed()
    assert parts["source"].starts == 0


def test_commands_before_hello_are_rejected(service, parts):
    c = Client(service.port)
    c.send("listen", on=True)
    assert c.is_closed()
    assert parts["source"].starts == 0


def test_new_client_after_disconnect(service):
    c = connect(service)
    c.close()
    c2 = connect(service)
    c2.close()


def test_speech_starting_during_tone_keeps_its_beginning(parts):
    """Frames during the post-tone mute can't start an utterance, but stay in the pre-roll."""
    parts["vad"] = FakeVAD([])
    s = Service(token=TOKEN, log=lambda *a: None, **parts)
    s._listening = True
    s._mute_until = float("inf")
    frames = [np.full(FRAME, i, dtype=np.float32) for i in range(40)]
    for f in frames[:5]:                         # speech begins while muted
        assert s._process_frame(f, prob=0.9) is None
    s._mute_until = 0.0
    utterance = None
    for f in frames[5:15]:                       # speech continues after the mute
        utterance = utterance or s._process_frame(f, prob=0.9)
    for f in frames[15:]:
        utterance = utterance or s._process_frame(f, prob=0.0)
    assert utterance is not None
    first = int(utterance.frames[0][0])
    assert first < 5, "the beginning spoken during the mute was dropped"


def test_disconnect_stops_listening(service, parts):
    c = connect(service)
    c.send("listen", on=True)
    c.wait_for("state", state="listening")
    c.close()
    deadline = time.monotonic() + 5
    while parts["source"].running and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not parts["source"].running


# --- Phase 1: decisions in the service ----------------------------------------------

CANDIDATES = [
    {"id": "Sketcher_CreateRectangle", "level": "edit", "phrases": ["Rechteck"], "active": True},
    {"id": "Std_Save", "level": "global", "phrases": ["Speichern"], "active": True},
]


def service_saying(parts, text):
    parts["transcriber"] = FakeTranscriber(text)
    s = Service(token=TOKEN, log=lambda *a: None, **parts)
    s.start()
    c = connect(s)
    c.send("context", candidates=CANDIDATES)
    c.send("listen", on=True)
    return s, c


def wait_tones(tones, n, timeout=5):
    deadline = time.monotonic() + timeout
    while len(tones.played) < n and time.monotonic() < deadline:
        time.sleep(0.01)


def test_speech_start_is_announced(parts):
    s, c = service_saying(parts, "Zeichne ein Rechteck")
    c.wait_for("speech_start")
    c.wait_for("transcript")
    c.close()
    s.stop()


def test_plan_for_known_command(parts):
    s, c = service_saying(parts, "Zeichne ein Rechteck")
    msg = c.wait_for("plan")
    assert msg["command"] == "Sketcher_CreateRectangle"
    assert msg["score"] >= 0.75
    assert parts["tones"].played == []          # the tone follows the addon's result
    c.send("result", ok=True)
    wait_tones(parts["tones"], 1)
    assert parts["tones"].played == ["ok"]
    c.close()
    s.stop()


def test_not_understood_plays_error_tone(parts):
    s, c = service_saying(parts, "Klaus")
    msg = c.wait_for("not_understood")
    assert msg["reason"] == "no_match"
    wait_tones(parts["tones"], 1)
    assert parts["tones"].played == ["error"]
    c.close()
    s.stop()


def test_unrelated_talk_is_ignored_silently(parts):
    s, c = service_saying(parts, "Ich gehe jetzt erst mal einen Kaffee trinken")
    c.wait_for("ignored")
    time.sleep(0.2)
    assert parts["tones"].played == []
    c.close()
    s.stop()


def test_candidates_become_hotwords(parts):
    s, c = service_saying(parts, "Zeichne ein Rechteck")
    c.wait_for("plan")
    assert parts["transcriber"].hotwords[-1] == "Rechteck, Speichern"
    c.close()
    s.stop()
