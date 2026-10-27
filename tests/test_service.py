# SPDX-License-Identifier: LGPL-2.1-or-later
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
    """Frames with a faint noise floor like a real microphone; level 0.0 is a system-muted one."""

    def __init__(self, n_frames, levels=None, delay=0.0):
        self.n_frames = n_frames
        self.levels = levels or [1e-4] * n_frames
        self.delay = delay              # the user starts speaking a moment later
        self.running = False
        self.starts = 0

    def start(self, callback):
        self.running = True
        self.starts += 1
        def feed():
            time.sleep(self.delay)
            for level in self.levels[:self.n_frames]:
                if not self.running:
                    return
                callback(np.full(FRAME, level, dtype=np.float32))
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

    def play_samples(self, audio, sample_rate):
        self.played.append("speech")
        return 0.01


class FakeSpeaker:
    def __init__(self):
        self.said = []

    def synth(self, text):
        self.said.append(text)
        return np.zeros(100, dtype=np.float32), 22050


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
            self.sock.settimeout(max(0.01, deadline - time.monotonic()))
            try:
                data = self.sock.recv(4096)
            except socket.timeout:
                break
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
    assert msg["via"] == "name"
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


# --- sequences of commands --------------------------------------------------------------

SEQUENCE_CANDIDATES = CANDIDATES + [
    {"id": "workbench:PartDesignWorkbench", "level": "global", "phrases": ["Part Design"], "active": True},
]
AFTER_SWITCH = SEQUENCE_CANDIDATES + [
    {"id": "PartDesign_Body", "level": "workbench", "phrases": ["Körper"], "active": True},
]


def sequence_service(parts, text):
    parts["transcriber"] = FakeTranscriber(text)
    s = Service(token=TOKEN, log=lambda *a: None, **parts)
    s.start()
    c = connect(s)
    c.send("context", candidates=SEQUENCE_CANDIDATES)
    c.send("listen", on=True)
    return s, c


def test_sequence_runs_step_by_step_with_new_context(parts):
    s, c = sequence_service(parts, "Wechsle zu Part Design und erstelle einen Körper")
    first = c.wait_for("plan")
    assert first["command"] == "workbench:PartDesignWorkbench"
    assert first["more"] is True
    c.send("context", candidates=AFTER_SWITCH)          # the addon sends the new context first
    c.send("result", ok=True, id=first["id"])
    second = c.wait_for("plan")
    assert second["command"] == "PartDesign_Body"
    assert second["more"] is False
    assert parts["tones"].played == []                  # no tone between the steps
    c.send("result", ok=True, id=second["id"])
    wait_tones(parts["tones"], 1)
    assert parts["tones"].played == ["ok"]
    c.close()
    s.stop()


def test_failed_step_stops_the_sequence(parts):
    s, c = sequence_service(parts, "Wechsle zu Part Design und speichern")
    first = c.wait_for("plan")
    c.send("result", ok=False, id=first["id"])
    wait_tones(parts["tones"], 1)
    time.sleep(0.2)
    assert parts["tones"].played == ["error"]
    with pytest.raises(TimeoutError):
        c.wait_for("plan", timeout=0.3)
    c.close()
    s.stop()


def test_unclear_step_stops_with_error(parts):
    s, c = sequence_service(parts, "Speichern, Klaus, Rechteck")
    first = c.wait_for("plan")
    assert first["command"] == "Std_Save"
    c.send("result", ok=True, id=first["id"])
    msg = c.wait_for("not_understood")
    assert msg["text"] == "Klaus"
    wait_tones(parts["tones"], 1)
    assert parts["tones"].played == ["error"]
    with pytest.raises(TimeoutError):
        c.wait_for("plan", timeout=0.3)
    c.close()
    s.stop()


def test_stale_result_is_ignored(parts):
    s, c = sequence_service(parts, "Speichern und Rechteck")
    first = c.wait_for("plan")
    c.send("result", ok=True, id="something old")
    with pytest.raises(TimeoutError):
        c.wait_for("plan", timeout=0.3)
    c.send("result", ok=True, id=first["id"])
    assert c.wait_for("plan")["command"] == "Sketcher_CreateRectangle"
    c.close()
    s.stop()


def test_talk_over_several_clauses_is_ignored_as_a_whole(parts):
    """ "bis gleich" alone would be a short unclear utterance with error tone."""
    s, c = sequence_service(parts, "Ich gehe jetzt einen Kaffee trinken, bis gleich")
    c.wait_for("ignored")
    time.sleep(0.2)
    assert parts["tones"].played == []
    c.close()
    s.stop()


def test_skipped_clause_is_reported(parts):
    s, c = sequence_service(parts, "Speichern, und zwar von hier")
    first = c.wait_for("plan")
    assert first["more"] is True
    c.send("result", ok=True, id=first["id"])
    assert c.wait_for("ignored")["text"] == "und zwar von hier"
    wait_tones(parts["tones"], 1)
    assert parts["tones"].played == ["ok"]
    c.close()
    s.stop()


def test_microphone_off_wins_over_the_rest_of_the_utterance(parts):
    """ "Ok, kurze Pause" in a dialog must not press OK first."""
    candidates = [
        {"id": "ui:ok", "level": "dialog", "phrases": ["OK"], "active": True},
        {"id": "ui:mic_off", "level": "global", "phrases": ["kurze Pause", "Ok kurze Pause"], "active": True},
    ]
    parts["transcriber"] = FakeTranscriber("Ok, kurze Pause.")
    s = Service(token=TOKEN, log=lambda *a: None, **parts)
    s.start()
    c = connect(s)
    c.send("context", candidates=candidates)
    c.send("listen", on=True)
    msg = c.wait_for("plan")
    assert (msg["command"], msg["more"]) == ("ui:mic_off", False)
    c.close()
    s.stop()



# --- microphone muted by the system (keyboard key) ----------------------------------------

def test_system_mute_is_reported_and_lifted(parts):
    """Muted by the system, the microphone delivers exact zeros; real noise never does."""
    levels = [1e-4] * 5 + [0.0] * 60 + [1e-4] * 5
    parts["source"] = FakeSource(len(levels), levels)
    parts["vad"] = FakeVAD([0.0] * len(levels))
    s = Service(token=TOKEN, log=lambda *a: None, **parts)
    s.start()
    c = connect(s)
    c.send("listen", on=True)
    c.wait_for("state", state="muted")
    c.wait_for("state", state="listening")
    c.close()
    s.stop()


def test_muted_frames_skip_the_vad(parts):
    levels = [0.0] * 60
    parts["source"] = FakeSource(len(levels), levels)
    parts["vad"] = FakeVAD([0.9] * len(levels))          # would be speech if asked
    s = Service(token=TOKEN, log=lambda *a: None, **parts)
    s.start()
    c = connect(s)
    c.send("listen", on=True)
    c.wait_for("state", state="muted")
    with pytest.raises(TimeoutError):
        c.wait_for("speech_start", timeout=0.3)
    c.close()
    s.stop()


def test_rename_alone_is_not_talk(parts):
    """Four words without any command name would be ignored as talk."""
    s, c = sequence_service(parts, "Den nennen wir Bodenplatte")
    msg = c.wait_for("plan")
    assert (msg["command"], msg["args"]) == ("ui:rename", {"label": "Bodenplatte"})
    assert msg["utterance_id"] >= 1
    c.close()
    s.stop()


# --- follow-up choice from the same clause ------------------------------------------------

SKETCH = [{"id": "PartDesign_NewSketch", "level": "workbench", "phrases": ["Skizze"], "active": True}]
PLANE_DIALOG = SKETCH + [
    {"id": "ui:choose:" + p, "level": "dialog", "phrases": [p.split(" (")[0]], "active": True}
    for p in ("XY-Ebene (Basis-Ebene)", "XZ-Ebene (Basis-Ebene)", "YZ-Ebene (Basis-Ebene)")]


def sketch_service(parts, text):
    parts["transcriber"] = FakeTranscriber(text)
    s = Service(token=TOKEN, log=lambda *a: None, **parts)
    s.start()
    c = connect(s)
    c.send("context", candidates=SKETCH)
    c.send("listen", on=True)
    return s, c


def test_clause_chooses_in_the_dialog_its_command_opened(parts):
    s, c = sketch_service(parts, "Mach eine Skizze in der XY-Ebene")
    first = c.wait_for("plan")
    assert (first["command"], first["more"]) == ("PartDesign_NewSketch", False)
    c.send("context", candidates=PLANE_DIALOG)          # the sketch command opened the plane dialog
    c.send("result", ok=True, id=first["id"])
    second = c.wait_for("plan")
    assert second["command"] == "ui:choose:XY-Ebene (Basis-Ebene)"
    assert parts["tones"].played == []
    c.send("result", ok=True, id=second["id"])
    wait_tones(parts["tones"], 1)
    assert parts["tones"].played == ["ok"]
    c.close()
    s.stop()


def test_no_follow_up_without_a_matching_choice(parts):
    s, c = sketch_service(parts, "Mach eine Skizze")
    first = c.wait_for("plan")
    c.send("context", candidates=PLANE_DIALOG)
    c.send("result", ok=True, id=first["id"])
    wait_tones(parts["tones"], 1)
    assert parts["tones"].played == ["ok"]
    with pytest.raises(TimeoutError):
        c.wait_for("plan", timeout=0.3)
    c.close()
    s.stop()


def test_a_choice_has_no_follow_up_of_its_own(parts):
    """The clause of a choice step must not be matched against the choices once more."""
    parts["transcriber"] = FakeTranscriber("XY-Ebene")
    s = Service(token=TOKEN, log=lambda *a: None, **parts)
    s.start()
    c = connect(s)
    c.send("context", candidates=PLANE_DIALOG)
    c.send("listen", on=True)
    first = c.wait_for("plan")
    c.send("context", candidates=PLANE_DIALOG)          # e.g. a dialog that stays open
    c.send("result", ok=True, id=first["id"])
    with pytest.raises(TimeoutError):
        c.wait_for("plan", timeout=0.5)
    c.close()
    s.stop()


# --- training: recognize only -----------------------------------------------------------------

def test_training_mode_only_transcribes(parts):
    parts["transcriber"] = FakeTranscriber("Zeichne ein Rechteck")
    s = Service(token=TOKEN, log=lambda *a: None, **parts)
    s.start()
    c = connect(s)
    c.send("context", candidates=CANDIDATES)
    c.send("train", on=True)
    c.send("listen", on=True)
    assert c.wait_for("transcript")["text"] == "Zeichne ein Rechteck"
    for kind in ("plan", "not_understood", "ignored"):
        with pytest.raises(TimeoutError):
            c.wait_for(kind, timeout=0.2)
    assert parts["tones"].played == []
    c.close()
    s.stop()


def test_learned_patterns_come_with_the_context(parts):
    parts["transcriber"] = FakeTranscriber("Nenndas Bodenplatte")
    s = Service(token=TOKEN, log=lambda *a: None, **parts)
    s.start()
    c = connect(s)
    c.send("context", candidates=CANDIDATES, patterns={"ui:rename": ["nenndas {label}"]})
    c.send("listen", on=True)
    msg = c.wait_for("plan")
    assert (msg["command"], msg["args"]) == ("ui:rename", {"label": "Bodenplatte"})
    c.close()
    s.stop()



# --- speech output (DESIGN.md 10.1) ---------------------------------------------------------------

def speaking_service(parts, text, level="important", candidates=None):
    """The greeting "Ich höre zu." makes the microphone deaf for a moment; speech starts after it."""
    parts["transcriber"] = FakeTranscriber(text)
    parts["source"].delay = 0.4
    speaker = FakeSpeaker()
    s = Service(token=TOKEN, log=lambda *a: None, speaker=speaker, speech_level=level, info={"language": "de"}, **parts)
    s.start()
    c = connect(s)
    c.send("context", candidates=candidates or CANDIDATES)
    c.send("listen", on=True)
    return s, c, speaker


def wait_said(speaker, n, timeout=5):
    deadline = time.monotonic() + timeout
    while len(speaker.said) < n and time.monotonic() < deadline:
        time.sleep(0.01)


def test_ready_is_said_once(parts):
    s, c, speaker = speaking_service(parts, "")
    wait_said(speaker, 1)
    c.send("listen", on=False)
    c.send("listen", on=True)
    time.sleep(0.2)
    assert speaker.said.count("Ich höre zu.") == 1
    c.close()
    s.stop()


def test_not_understood_is_said_instead_of_the_error_tone(parts):
    s, c, speaker = speaking_service(parts, "Klaus")
    c.wait_for("not_understood")
    msg = c.wait_for("said")
    assert msg["text"] == "Das habe ich nicht verstanden."
    assert "error" not in parts["tones"].played
    c.close()
    s.stop()


def test_ambiguity_names_the_choices(parts):
    candidates = [{"id": "A_Rect", "level": "edit", "phrases": ["Rechteck"], "label": "Rechteck A", "active": True},
                  {"id": "B_Rect", "level": "edit", "phrases": ["Rechteck"], "label": "Rechteck B", "active": True}]
    s, c, speaker = speaking_service(parts, "Rechteck", candidates=candidates)
    c.wait_for("not_understood")
    assert c.wait_for("said")["text"] in ("Meinst du Rechteck A oder Rechteck B?", "Meinst du Rechteck B oder Rechteck A?")
    c.close()
    s.stop()


def test_chatty_confirms_by_voice(parts):
    s, c, speaker = speaking_service(parts, "Zeichne ein Rechteck", level="chatty")
    msg = c.wait_for("plan")
    c.send("result", ok=True, id=msg["id"])
    assert c.wait_for("said")["text"] in ("Mache ich.", "Okay.", "Erledigt.")
    assert "ok" not in parts["tones"].played
    c.close()
    s.stop()


def test_important_level_keeps_the_ok_tone(parts):
    s, c, speaker = speaking_service(parts, "Zeichne ein Rechteck")
    msg = c.wait_for("plan")
    c.send("result", ok=True, id=msg["id"])
    wait_tones(parts["tones"], 2)                         # "Ich höre zu." and the ok tone
    assert parts["tones"].played[-1] == "ok"
    c.close()
    s.stop()


def test_addon_can_ask_for_a_sentence(parts):
    s, c, speaker = speaking_service(parts, "")
    c.send("say", kind="train_again", n=2)
    deadline = time.monotonic() + 5
    while "Bitte noch 2 mal." not in speaker.said and time.monotonic() < deadline:
        time.sleep(0.01)
    assert "Bitte noch 2 mal." in speaker.said
    c.close()
    s.stop()


def test_without_voice_tones_stay(parts):
    parts["transcriber"] = FakeTranscriber("Klaus")
    s = Service(token=TOKEN, log=lambda *a: None, speaker=None, speech_level="important", **parts)
    s.start()
    c = connect(s)
    c.send("context", candidates=CANDIDATES)
    c.send("listen", on=True)
    c.wait_for("not_understood")
    wait_tones(parts["tones"], 1)
    assert parts["tones"].played == ["error"]
    c.close()
    s.stop()


# --- values for a running tool (DESIGN.md 6.5) -----------------------------------------------------

SKETCHER = [
    {"id": "Sketcher_CreateRectangle", "level": "edit", "phrases": ["Rechteck"], "active": True},
    {"id": "Sketcher_CreateCircle", "level": "edit", "phrases": ["Kreis"], "active": True},
]


def tool_service(parts, text, tool, extra=()):
    parts["transcriber"] = FakeTranscriber(text)
    s = Service(token=TOKEN, log=lambda *a: None, info={"language": "de"}, **parts)
    s.start()
    c = connect(s)
    c.send("context", candidates=SKETCHER + list(extra), tool=tool)
    c.send("listen", on=True)
    return s, c


def test_values_go_to_the_running_tool(parts):
    s, c = tool_service(parts, "50 mal 30", {"running": True})
    msg = c.wait_for("plan")
    assert (msg["command"], msg["args"]) == ("ui:values", {"values": [[None, 50.0, "length"], [None, 30.0, "length"]]})
    c.close()
    s.stop()


def test_values_without_a_tool_are_nothing(parts):
    s, c = tool_service(parts, "50 mal 30", {"running": False})
    with pytest.raises(TimeoutError):
        c.wait_for("plan", timeout=0.5)
    c.close()
    s.stop()


def test_a_command_wins_over_values_in_a_tool(parts):
    s, c = tool_service(parts, "Kreis", {"running": True})
    assert c.wait_for("plan")["command"] == "Sketcher_CreateCircle"
    c.close()
    s.stop()


def test_values_said_with_the_command_follow_it(parts):
    """ "Zeichne ein Rechteck 50 mal 30": the tool starts, the values wait for its fields."""
    s, c = tool_service(parts, "Zeichne ein Rechteck 50 mal 30", {"running": False})
    first = c.wait_for("plan")
    assert first["command"] == "Sketcher_CreateRectangle"
    c.send("context", candidates=SKETCHER, tool={"running": True})       # the rectangle tool runs now
    c.send("result", ok=True, id=first["id"])
    second = c.wait_for("plan")
    assert (second["command"], second["args"]) == ("ui:values", {"values": [[None, 50.0, "length"], [None, 30.0, "length"]]})
    c.close()
    s.stop()


def test_named_values_are_one_step_and_no_workbench_switch(parts):
    """ "Breite" sounds like "Part": with a tool running, it is a value, never a workbench switch."""
    s, c = tool_service(parts, "Breite 50, Höhe 30", {"running": True},
                        extra=[{"id": "workbench:PartWorkbench", "level": "global", "phrases": ["Part"], "active": True}])
    msg = c.wait_for("plan")
    assert (msg["command"], msg["args"], msg["more"]) == \
        ("ui:values", {"values": [[0, 50.0, "length"], [1, 30.0, "length"]]}, False)
    c.close()
    s.stop()
