# SPDX-License-Identifier: LGPL-2.1-or-later
"""Microphone button and connection to the speech service.

The addon sends the command candidates of the current context, the service decides,
and the addon executes the resulting plan (Phase 1: single commands).
"""

import os
import secrets
import socket
import sys
import time

import FreeCAD as App
import FreeCADGui as Gui

from talktome import command
from talktome import context as ttm_context
from talktome import executor
from talktome.qt import QtCore, QtGui, QtWidgets
from ttm_core.protocol import VERSION, LineDecoder, encode, make_message
from ttm_core.training import classify, learn, options

ADDON_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_DIR = os.path.join(ADDON_DIR, "service")
ICON_DIR    = os.path.join(ADDON_DIR, "Resources", "icons")
PARAMS      = App.ParamGet("User parameter:BaseApp/Preferences/Mod/TalkToMe")
POLL_MS     = 50
STATUS_MS   = 8000
STDERR_KEEP = 20
MISSES_KEEP = 8              # not understood utterances offered in the training page

# Set by FreeCAD's AppImage or bundle for its own Python; the service runs on another Python.
FOREIGN_ENV = ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "LD_LIBRARY_PATH", "LD_PRELOAD")

ICONS = {
    "off":        "mic_off.svg",
    "starting":   "mic_wait.svg",
    "idle":       "mic_wait.svg",
    "listening":  "mic_on.svg",
    "muted":      "mic_muted.svg",
    "processing": "mic_busy.svg",
    "error":      "mic_error.svg",
}
TOOLTIPS = {
    "off":        "Talk to me: microphone off",
    "starting":   "Talk to me: starting speech service ...",
    "idle":       "Talk to me: connected, microphone off",
    "listening":  "Talk to me: listening",
    "muted":      "Talk to me: microphone muted by the system (e.g. its keyboard key)",
    "processing": "Talk to me: recognizing ...",
    "error":      "Talk to me: speech service not available",
}


def default_python():
    if sys.platform.startswith("win"):
        return os.path.join(SERVICE_DIR, ".venv", "Scripts", "python.exe")
    return os.path.join(SERVICE_DIR, ".venv", "bin", "python")


def log(text):
    App.Console.PrintLog("Talk to me: {}\n".format(text))


class Controller(QtCore.QObject):
    """Drives the microphone command's action, owns the service process and the connection."""

    def __init__(self, main_window, action):
        super().__init__(main_window)
        self.mw = main_window
        self.action = action
        self.action.toggled.connect(self.on_toggled)

        self.language = PARAMS.GetString("Language", "de")
        self.vocab, self.heard = ttm_context.load_vocabulary(self.language)
        self.last_candidates = None  # the context sent last; a training situation is taken from it
        self.misses = []             # recent not understood utterances with their situation
        self.trainer = None          # the open training page
        self.training_candidates = None
        self.training_restore = None # microphone state to restore after training
        self.asking = None           # the open question menu: {"text", "options", "candidates", "popup"}
        self.process = None
        self.stderr_tail = []
        self.created = None          # (utterance id, document, object) of the last object a step created
        self.sock = None
        self.decoder = LineDecoder()
        self.token = secrets.token_hex(16)
        self.want_listen = False
        self.poll = QtCore.QTimer(self)
        self.poll.setInterval(POLL_MS)
        self.poll.timeout.connect(self.on_poll)
        self.set_state("off")

    # --- UI ----------------------------------------------------------------------------

    def set_state(self, state):
        self.state = state
        self.action.setIcon(QtGui.QIcon(os.path.join(ICON_DIR, ICONS[state])))
        self.action.setToolTip(TOOLTIPS[state])
        self.action.setText("Talk to me")

    def status(self, text):
        self.mw.statusBar().showMessage("Talk to me: " + text, STATUS_MS)

    def on_workbench_activated(self, *args):
        self.send_context()

    def training(self):
        return self.trainer is not None and self.trainer.recording

    def send_context(self):
        """Send the command candidates of the current context (DESIGN.md 6)."""
        if self.sock is None:
            return
        if self.training():                    # the trained situation stays, for its hints
            self.send("context", candidates=self.training_candidates)
            return
        try:
            candidates = ttm_context.collect(self.vocab, self.language, self.heard)
        except Exception as e:
            log("collecting the context failed: {}".format(e))
            return
        self.last_candidates = candidates
        self.send("context", candidates=candidates)

    def reload_vocabulary(self):
        self.vocab, self.heard = ttm_context.load_vocabulary(self.language)
        self.send_context()

    # --- training (DESIGN.md 8.7) ------------------------------------------------------------

    def open_training(self):
        if self.trainer is None:
            from talktome.training import TrainingDialog
            if self.last_candidates is None:
                try:
                    self.last_candidates = ttm_context.collect(self.vocab, self.language, self.heard)
                except Exception as e:
                    log("collecting the context failed: {}".format(e))
            self.trainer = TrainingDialog(self, self.mw)
        self.trainer.show()
        self.trainer.raise_()
        self.trainer.activateWindow()

    def start_training(self, candidates):
        """Transcribe only, with the hints of the trained situation."""
        self.training_candidates = candidates
        self.training_restore = self.action.isChecked()
        self.send("context", candidates=candidates)
        self.send("train", on=True)
        if not self.action.isChecked():
            self.action.setChecked(True)       # starts the service if needed
        else:
            self.send("listen", on=True)

    def stop_training(self):
        self.send("train", on=False)
        if self.training_restore is False:
            self.action.setChecked(False)
        self.training_restore = None
        self.send_context()

    def remember_miss(self, msg):
        self.misses = (self.misses + [{"time": time.time(), "text": msg.get("text", ""),
                                       "alternatives": msg.get("alternatives") or [],
                                       "candidates": self.last_candidates}])[-MISSES_KEEP:]

    def on_toggled(self, checked):
        self.want_listen = checked
        if checked:
            if not self.start_service():
                return
            if self.sock is None:
                return                       # listen is sent once connected
        self.send("listen", on=checked)
        if not checked and self.state != "error":
            self.set_state("idle" if self.sock else "off")

    def fail(self, text):
        self.set_state("error")
        self.status(text)
        App.Console.PrintWarning("Talk to me: {}\n".format(text))
        self.action.blockSignals(True)
        self.action.setChecked(False)
        self.action.blockSignals(False)
        self.want_listen = False

    # --- service process ---------------------------------------------------------------

    def start_service(self):
        if self.process is not None and self.process.state() != QtCore.QProcess.ProcessState.NotRunning:
            return True
        python = PARAMS.GetString("ServicePython", "") or default_python()
        if not os.path.exists(python):
            self.fail("speech service not installed ({} not found), see README".format(python))
            return False
        args = ["-m", "talktome_service",
                "--language", PARAMS.GetString("Language", "de"),
                "--device", PARAMS.GetString("Device", "auto")]
        model = PARAMS.GetString("Model", "")
        if model:
            args += ["--model", model]
        args += PARAMS.GetString("ExtraArgs", "").split()

        env = QtCore.QProcessEnvironment.systemEnvironment()
        for name in FOREIGN_ENV:
            env.remove(name)
        env.insert("TTM_TOKEN", self.token)
        env.insert("PYTHONPATH", os.pathsep.join([ADDON_DIR, SERVICE_DIR]))
        env.insert("PYTHONIOENCODING", "utf-8")
        self.stderr_tail = []
        self.process = QtCore.QProcess(self)
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(SERVICE_DIR)
        self.process.readyReadStandardOutput.connect(self.on_stdout)
        self.process.readyReadStandardError.connect(self.on_stderr)
        self.process.finished.connect(self.on_finished)
        self.set_state("starting")
        self.status("starting speech service (the first start downloads the model) ...")
        self.process.start(python, args)
        return True

    def on_stdout(self):
        out = self.process.readAllStandardOutput().data().decode("utf-8", "replace")
        for line in out.splitlines():
            if line.startswith("TTM_PORT="):
                self.connect(int(line.split("=", 1)[1]))

    def on_stderr(self):
        err = self.process.readAllStandardError().data().decode("utf-8", "replace")
        for line in err.splitlines():
            log(line)
            self.stderr_tail = (self.stderr_tail + [line])[-STDERR_KEEP:]

    def on_finished(self, *args):
        self.disconnect_socket()
        self.process = None
        if self.state != "off":
            if self.stderr_tail:
                App.Console.PrintWarning("Talk to me: speech service output:\n  {}\n".format(
                    "\n  ".join(self.stderr_tail)))
            self.fail("speech service stopped, see Report view for details")

    def shutdown(self):
        self.send("bye")
        self.disconnect_socket()
        if self.process is not None:
            self.process.finished.disconnect(self.on_finished)
            if not self.process.waitForFinished(3000):
                self.process.kill()
                self.process.waitForFinished(1000)
            self.process = None

    # --- socket ------------------------------------------------------------------------

    def connect(self, port):
        try:
            self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        except OSError as e:
            self.fail("cannot connect to speech service: {}".format(e))
            return
        self.sock.setblocking(False)
        self.decoder = LineDecoder()
        self.send("hello", token=self.token, version=VERSION, language=PARAMS.GetString("Language", "de"))
        self.send("train", on=self.training())
        self.send_context()
        if self.want_listen:
            self.send("listen", on=True)
        self.poll.start()

    def disconnect_socket(self):
        self.poll.stop()
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    def send(self, type_, **fields):
        if self.sock is None:
            return
        try:
            self.sock.setblocking(True)
            self.sock.sendall(encode(make_message(type_, **fields)))
        except OSError as e:
            log("send failed: {}".format(e))
        finally:
            if self.sock is not None:
                self.sock.setblocking(False)

    def on_poll(self):
        while self.sock is not None:
            try:
                data = self.sock.recv(65536)
            except (BlockingIOError, InterruptedError):
                return
            except OSError as e:
                log("connection error: {}".format(e))
                data = b""
            if not data:
                self.disconnect_socket()
                if self.state != "off":
                    self.fail("connection to speech service lost")
                return
            for msg in self.decoder.feed(data):
                self.on_message(msg)

    def on_message(self, msg):
        kind = msg["type"]
        if kind == "welcome":
            log("model {model} on {device} ({compute_type}), language {language}".format(**msg))
            if msg.get("fallback"):
                self.status("no usable GPU found, using the CPU")
        elif kind == "state":
            self.set_state(msg.get("state", "idle"))
        elif kind == "speech_start":
            self.send_context()                # fresh snapshot while the user is speaking
        elif kind == "transcript":
            log("»{}« ({} ms)".format(msg.get("text", ""), msg.get("stt_ms", 0)))
            if self.training():
                self.trainer.add_recording(msg.get("text", ""))
        elif kind == "plan":
            self.on_plan(msg)
        elif kind == "not_understood":
            self.remember_miss(msg)
            self.ask(msg)
            self.status("not understood: »{}« ({})".format(msg.get("text", ""), msg.get("reason")))
            log("not understood »{}«, reason {}, candidates {}".format(
                msg.get("text"), msg.get("reason"), msg.get("alternatives")))
        elif kind == "ignored":
            log("ignored »{}«".format(msg.get("text", "")))
        elif kind == "error":
            App.Console.PrintWarning("Talk to me: {}\n".format(msg.get("message")))

    def rename_target(self, utterance_id):
        """What "den", "das", "ihn" refer to: an object created in the same utterance, else the
        single selected object, else the object created last."""
        doc = App.ActiveDocument
        created = None
        if self.created is not None and doc is not None and self.created[1] == doc.Name:
            created = doc.getObject(self.created[2])
        if created is not None and self.created[0] == utterance_id:
            return created
        selection = Gui.Selection.getSelection()
        if len(selection) == 1:
            return selection[0]
        return created

    def remember_created(self, doc_name, before, utterance_id):
        doc = App.ActiveDocument
        if doc is None or doc.Name != doc_name:
            return
        created = executor.created_objects(doc, before)
        if len(created) == 1:
            self.created = (utterance_id, doc.Name, created[0].Name)

    # --- question menu (DESIGN.md 8.8) -------------------------------------------------------

    def ask(self, msg):
        """Offer the likely commands of a not understood utterance next to the mouse pointer."""
        if not PARAMS.GetBool("AskMenu", True) or not self.last_candidates:
            return
        found = options(msg.get("alternatives") or [], self.last_candidates)
        if not found:
            return
        from talktome.ask import AskPopup
        from talktome.training import describe
        by_id = {c["id"]: c for c in self.last_candidates}
        entries = [(describe(by_id[cmd]).split("   (")[0], active) for cmd, active in found]
        if self.asking is not None:
            self.asking["popup"].close()
        popup = AskPopup(self.mw, msg.get("text", ""), entries,
                         on_pick=lambda i: self.send("result", ok=self.choose(i)[0]),
                         on_train=self.open_training)
        self.asking = {"text": msg.get("text", ""), "options": [cmd for cmd, _ in found],
                       "candidates": self.last_candidates, "popup": popup}
        popup.destroyed.connect(lambda *a, p=popup: self.asking_closed(p))
        popup.show()

    def asking_closed(self, popup):
        if self.asking is not None and self.asking["popup"] is popup:
            self.asking = None

    def choose(self, index):
        """Run the command picked in the question menu and learn what was heard for it."""
        asking = self.asking
        if asking is None or not 0 <= index < len(asking["options"]):
            return False, "nothing to pick"
        asking["popup"].close()
        command = asking["options"][index]
        ok, reason, shown = self.run_command(command, {}, None)
        self.report(asking["text"], shown, ok, reason)
        if ok and classify(asking["text"], command, asking["candidates"], self.language) == "learn":
            data = ttm_context.read_custom(self.language)
            ttm_context.save_custom(self.language, learn(data, command, heard=[asking["text"]]))
            self.reload_vocabulary()
            log("learned »{}« for {}".format(asking["text"], command))
        return ok, reason

    # --- executing ------------------------------------------------------------------------------

    def report(self, text, shown, ok, reason):
        if ok:
            self.status("»{}« → {}{}".format(text, shown, "  ({})".format(reason) if reason else ""))
            App.Console.PrintMessage("Talk to me: »{}« → {}\n".format(text, shown))
        else:
            self.status("»{}« → {} failed: {}".format(text, shown, reason))
            App.Console.PrintWarning("Talk to me: »{}« → {} failed: {}\n".format(text, shown, reason))

    def on_plan(self, msg):
        command, text = msg.get("command", ""), msg.get("text", "")
        if command == "ui:pick":
            ok, reason = self.choose((msg.get("args") or {}).get("pick", 0) - 1)
            if not ok:
                self.report(text, "pick", ok, reason)
            self.send("result", ok=ok, id=msg.get("id"))
            return
        ok, reason, shown = self.run_command(command, msg.get("args") or {}, msg.get("utterance_id"))
        if ok:
            # The next step is decided in the new context; a dialog the step opened may ask
            # for what was said already ("Skizze in der XY-Ebene").
            self.send_context()
        if msg.get("via") == "description":
            shown += " (from help text)"
        self.report(text, shown, ok, reason)
        self.send("result", ok=ok, id=msg.get("id"))

    def run_command(self, command, args, utterance_id):
        """Execute one command. Returns (ok, reason, how to show it)."""
        doc = App.ActiveDocument
        doc_name, before = (doc.Name, {o.Name for o in doc.Objects}) if doc else (None, set())
        if command == "ui:mic_off":
            self.action.setChecked(False)      # switching on again is the button's job
            ok, reason = True, ""
        elif PARAMS.GetBool("DryRun", False):
            ok, reason = True, "dry run, not executed"
        elif command == "ui:rename":
            target = self.rename_target(utterance_id)
            if target is None:
                ok, reason = False, "nothing to rename: select an object"
            else:
                ok, reason = executor.rename(target, args.get("label", ""))
                command = "rename {} to »{}«".format(target.Name, target.Label)
        else:
            try:
                ok, reason = executor.execute(command)
            except Exception as e:
                ok, reason = False, str(e)
            if ok:
                self.remember_created(doc_name, before, utterance_id)
        return ok, reason, command


_controller = None


def open_training():
    if _controller is not None:
        _controller.open_training()


def setup():
    """Create the controller once FreeCAD has created the command's action. Returns True when done."""
    global _controller
    mw = Gui.getMainWindow()
    action = command.action()
    if mw is None or action is None:
        return False
    if _controller is None:
        _controller = Controller(mw, action)
        mw.workbenchActivated.connect(_controller.on_workbench_activated)
        QtWidgets.QApplication.instance().aboutToQuit.connect(_controller.shutdown)
    return True
