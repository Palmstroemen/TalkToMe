# SPDX-License-Identifier: LGPL-2.1-or-later
"""Microphone button and connection to the speech service.

The addon sends the command candidates of the current context, the service decides,
and the addon executes the resulting plan (Phase 1: single commands).
"""

import os
import secrets
import socket
import sys

import FreeCAD as App
import FreeCADGui as Gui

from talktome import command
from talktome import context as ttm_context
from talktome import executor
from talktome.qt import QtCore, QtGui, QtWidgets
from ttm_core.protocol import VERSION, LineDecoder, encode, make_message

ADDON_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_DIR = os.path.join(ADDON_DIR, "service")
ICON_DIR    = os.path.join(ADDON_DIR, "Resources", "icons")
PARAMS      = App.ParamGet("User parameter:BaseApp/Preferences/Mod/TalkToMe")
POLL_MS     = 50
STATUS_MS   = 8000
STDERR_KEEP = 20

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
        self.vocab = ttm_context.load_vocabulary(self.language)
        self.process = None
        self.stderr_tail = []
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

    def send_context(self):
        """Send the command candidates of the current context (DESIGN.md 6)."""
        if self.sock is None:
            return
        try:
            candidates = ttm_context.collect(self.vocab, self.language)
        except Exception as e:
            log("collecting the context failed: {}".format(e))
            return
        self.send("context", candidates=candidates)

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
        elif kind == "plan":
            self.on_plan(msg)
        elif kind == "not_understood":
            self.status("not understood: »{}« ({})".format(msg.get("text", ""), msg.get("reason")))
            log("not understood »{}«, reason {}, candidates {}".format(
                msg.get("text"), msg.get("reason"), msg.get("alternatives")))
        elif kind == "ignored":
            log("ignored »{}«".format(msg.get("text", "")))
        elif kind == "error":
            App.Console.PrintWarning("Talk to me: {}\n".format(msg.get("message")))

    def on_plan(self, msg):
        command, text = msg.get("command", ""), msg.get("text", "")
        if command == "ui:mic_off":
            self.action.setChecked(False)      # switching on again is the button's job
            ok, reason = True, ""
        elif PARAMS.GetBool("DryRun", False):
            ok, reason = True, "dry run, not executed"
        else:
            try:
                ok, reason = executor.execute(command)
            except Exception as e:
                ok, reason = False, str(e)
        if ok and msg.get("more"):
            self.send_context()                # the next step is decided in the new context
        if msg.get("via") == "description":
            command += " (from help text)"
        if ok:
            self.status("»{}« → {}{}".format(text, command, "  ({})".format(reason) if reason else ""))
            App.Console.PrintMessage("Talk to me: »{}« → {}\n".format(text, command))
        else:
            self.status("»{}« → {} failed: {}".format(text, command, reason))
            App.Console.PrintWarning("Talk to me: »{}« → {} failed: {}\n".format(text, command, reason))
        self.send("result", ok=ok, id=msg.get("id"))


_controller = None


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
