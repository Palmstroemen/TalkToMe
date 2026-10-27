# SPDX-License-Identifier: LGPL-2.1-or-later
"""Microphone button and connection to the speech service.

The addon sends the command candidates of the current context, the service decides,
and the addon executes the resulting plan step by step.
"""

import json
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
from talktome.qt import QT_TRANSLATE_NOOP, QtCore, QtGui, QtWidgets, translate
from ttm_core import install
from ttm_core.protocol import VERSION, LineDecoder, encode, make_message
from ttm_core.objects import find_object
from ttm_core.training import classify, learn, options

ADDON_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_DIR = os.path.join(ADDON_DIR, "service")
ICON_DIR    = os.path.join(ADDON_DIR, "Resources", "icons")
PARAMS      = App.ParamGet("User parameter:BaseApp/Preferences/Mod/TalkToMe")
POLL_MS     = 50
STATUS_MS   = 8000
STDERR_KEEP = 20
REASONS = {                  # why something was not understood, as shown in the status bar
    "no_match": QT_TRANSLATE_NOOP("TalkToMe", "no matching command"),
    "ambiguous": QT_TRANSLATE_NOOP("TalkToMe", "ambiguous"),
    "inactive": QT_TRANSLATE_NOOP("TalkToMe", "not available now"),
}
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
    "off":        QT_TRANSLATE_NOOP("TalkToMe", "Talk to me: microphone off"),
    "starting":   QT_TRANSLATE_NOOP("TalkToMe", "Talk to me: starting speech service ..."),
    "idle":       QT_TRANSLATE_NOOP("TalkToMe", "Talk to me: connected, microphone off"),
    "listening":  QT_TRANSLATE_NOOP("TalkToMe", "Talk to me: listening"),
    "muted":      QT_TRANSLATE_NOOP("TalkToMe", "Talk to me: microphone muted by the system (e.g. its keyboard key)"),
    "processing": QT_TRANSLATE_NOOP("TalkToMe", "Talk to me: recognizing ..."),
    "error":      QT_TRANSLATE_NOOP("TalkToMe", "Talk to me: speech service not available"),
}


def service_environment():
    """Environment for the service's Python: without the variables of FreeCAD's own Python."""
    env = QtCore.QProcessEnvironment.systemEnvironment()
    for name in FOREIGN_ENV:
        env.remove(name)
    env.insert("TTM_USER_DIR", ttm_context.user_dir())
    env.insert("PYTHONPATH", os.pathsep.join([ADDON_DIR, SERVICE_DIR]))
    env.insert("PYTHONIOENCODING", "utf-8")
    return env


def probe_service(timeout_ms=5000):
    """What the service's Python finds: microphones, CUDA devices, speech output. {} if not available."""
    python = service_python()
    if not os.path.exists(python):
        return {}
    process = QtCore.QProcess()
    process.setProcessEnvironment(service_environment())
    process.setWorkingDirectory(SERVICE_DIR)
    process.start(python, ["-m", "talktome_service", "--probe"])
    if not process.waitForFinished(timeout_ms):
        process.kill()
        return {}
    try:
        return json.loads(process.readAllStandardOutput().data().decode("utf-8", "replace"))
    except ValueError:
        return {}


def service_python():
    return PARAMS.GetString("ServicePython", "") or default_python()


def default_python():
    return install.default_python(ttm_context.user_dir(), SERVICE_DIR, windows=sys.platform.startswith("win"))


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
        self.vocab, self.heard, self.patterns = ttm_context.load_vocabulary(self.language)
        self.last_candidates = None  # the context sent last; a training situation is taken from it
        self.misses = []             # recent not understood utterances with their situation
        self.miss_count = 0
        self.trainer = None          # the open training page
        self.editor = None           # the open vocabulary editor
        self.training_candidates = None
        self.training_restore = None # microphone state to restore after training
        self.asking = None           # the open question menu: {"text", "options", "candidates", "popup"}
        self.pending_values = None   # values said before the tool showed its fields (DESIGN.md 6.5)
        self.tool_command = None     # the command that started the running tool, if started by voice
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
        self.action.setToolTip(translate("TalkToMe", TOOLTIPS[state]))
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
            self.send("context", candidates=self.training_candidates, patterns=self.patterns)
            return
        try:
            candidates = ttm_context.collect(self.vocab, self.language, self.heard)
        except Exception as e:
            log("collecting the context failed: {}".format(e))
            return
        self.last_candidates = candidates
        self.send("context", candidates=candidates, patterns=self.patterns,
                  tool={"running": ttm_context.values_expected()})

    def reload_vocabulary(self):
        self.vocab, self.heard, self.patterns = ttm_context.load_vocabulary(self.language)
        self.send_context()

    # --- training (DESIGN.md 8.7) ------------------------------------------------------------

    def open_training(self, parent=None):
        """parent: a modal window it is opened from (the preferences); it blocks all others."""
        if parent is not None and self.trainer is not None and self.trainer.parent() is not parent:
            self.trainer.close()
        if self.trainer is None:
            from talktome.training import TrainingDialog
            if self.last_candidates is None:
                try:
                    self.last_candidates = ttm_context.collect(self.vocab, self.language, self.heard)
                except Exception as e:
                    log("collecting the context failed: {}".format(e))
            self.trainer = TrainingDialog(self, parent or self.mw)
            if parent is not None:
                self.trainer.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        self.trainer.show()
        self.trainer.raise_()
        self.trainer.activateWindow()

    def open_vocabulary(self, parent=None):
        """parent: a modal window it is opened from (the preferences)."""
        if parent is not None and self.editor is not None and self.editor.parent() is not parent:
            self.editor.close()
        if self.editor is None:
            from talktome.vocabulary import VocabularyEditor
            self.editor = VocabularyEditor(self, parent or self.mw)
            if parent is not None:
                self.editor.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        self.editor.fill()
        self.editor.show()
        self.editor.raise_()
        self.editor.activateWindow()

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
        self.miss_count += 1
        self.misses = (self.misses + [{"id": self.miss_count, "time": time.time(), "text": msg.get("text", ""),
                                       "alternatives": msg.get("alternatives") or [],
                                       "candidates": self.last_candidates}])[-MISSES_KEEP:]
        if self.trainer is not None:
            self.trainer.fill_misses()

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
        python = service_python()
        if not os.path.exists(python):
            self.fail(translate("TalkToMe", "speech service not installed ({} not found)").format(python))
            if not PARAMS.GetString("ServicePython", ""):
                QtCore.QTimer.singleShot(0, self.offer_install)
            return False
        args = ["-m", "talktome_service",
                "--volume", str(PARAMS.GetInt("Volume", 40) / 100.0),
                "--language", PARAMS.GetString("Language", "de"),
                "--device", PARAMS.GetString("Device", "auto")]
        model = PARAMS.GetString("Model", "")
        if model:
            args += ["--model", model]
        args += ["--speech", PARAMS.GetString("Speech", "important")]
        voice = PARAMS.GetString("Voice", "")
        if voice:
            args += ["--voice", voice]
        microphone = PARAMS.GetString("Microphone", "")
        if microphone:
            args += ["--mic", microphone]
        args += PARAMS.GetString("ExtraArgs", "").split()

        env = service_environment()
        env.insert("TTM_TOKEN", self.token)
        self.stderr_tail = []
        self.process = QtCore.QProcess(self)
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(SERVICE_DIR)
        self.process.readyReadStandardOutput.connect(self.on_stdout)
        self.process.readyReadStandardError.connect(self.on_stderr)
        self.process.finished.connect(self.on_finished)
        self.set_state("starting")
        self.status(translate("TalkToMe", "starting speech service (the first start downloads the model) ..."))
        self.process.start(python, args)
        return True

    def offer_install(self):
        """The microphone was switched on without a speech service: install it, then listen."""
        import talktome.install
        if talktome.install.run(self.mw):
            self.action.setChecked(True)

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
                App.Console.PrintWarning(translate("TalkToMe", "Talk to me: speech service output:\n  {}\n").format(
                    "\n  ".join(self.stderr_tail)))
            self.fail(translate("TalkToMe", "speech service stopped, see Report view for details"))

    def restart_service(self):
        """Apply changed settings: language and vocabulary now, the service on its next start;
        a running service is restarted, listening again if it was."""
        self.language = PARAMS.GetString("Language", "de")
        self.vocab, self.heard, self.patterns = ttm_context.load_vocabulary(self.language)
        if self.process is None:
            return
        listening = self.action.isChecked()
        self.shutdown()
        self.set_state("off")
        if listening:
            self.want_listen = True
            self.start_service()

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
            self.fail(translate("TalkToMe", "cannot connect to speech service: {}").format(e))
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

    def fill_pending_values(self):
        """"Rechteck 50 mal 30": the fields appear after the first click; fill them then."""
        if self.pending_values is None:
            return
        if not ttm_context.tool_running():
            self.pending_values = None         # the tool ended without its fields
            return
        if executor.value_fields():
            values, self.pending_values = self.pending_values, None
            executor.fill_values(values, self.tool_command)

    def on_poll(self):
        self.fill_pending_values()
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
                    self.fail(translate("TalkToMe", "connection to speech service lost"))
                return
            for msg in self.decoder.feed(data):
                self.on_message(msg)

    def on_message(self, msg):
        kind = msg["type"]
        if kind == "welcome":
            log("model {model} on {device} ({compute_type}), language {language}".format(**msg))
            if msg.get("fallback"):
                self.status(translate("TalkToMe", "no usable GPU found, using the CPU"))
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
            reason = REASONS.get(msg.get("reason"), msg.get("reason") or "")
            self.status(translate("TalkToMe", "not understood: »{}« ({})").format(msg.get("text", ""),
                                                                               translate("TalkToMe", reason)))
            log("not understood »{}«, reason {}, candidates {}".format(
                msg.get("text"), msg.get("reason"), msg.get("alternatives")))
        elif kind == "said":
            log("said »{}«".format(msg.get("text", "")))
        elif kind == "ignored":
            log("ignored »{}«".format(msg.get("text", "")))
        elif kind == "error":
            App.Console.PrintWarning("Talk to me: {}\n".format(msg.get("message")))

    def named_object(self, spoken):
        """("object", obj) for an object named in the sentence, as read from the tree."""
        doc = App.ActiveDocument
        if doc is None:
            return None, None
        label = find_object(spoken, [o.Label for o in doc.Objects], self.language)
        found = doc.getObjectsByLabel(label) if label else []
        return ("object", found[0]) if found else (None, None)

    def rename_target(self, utterance_id):
        """What "den", "das", "ihn" refer to, by priority (DESIGN.md 7, Umbenennen):

        1. an open dimension dialog in the sketcher: its name field     ("dialog", dialog)
        2. the one dimension selected in the sketch being edited        ("constraint", (sketch, index))
        3. an object created in the same utterance                      ("object", obj) from here on
        4. the single selected object
        5. the object being edited, e.g. the open sketch
        6. the object created last by voice
        7. the active body (bold in the tree)
        """
        dialog = executor.datum_dialog()
        if dialog is not None and executor.datum_name_field(dialog) is not None:
            return "dialog", dialog
        constraint = executor.selected_constraint()
        if constraint is not None:
            return "constraint", constraint
        doc = App.ActiveDocument
        if doc is None:
            return None
        created = None
        if self.created is not None and self.created[1] == doc.Name:
            created = doc.getObject(self.created[2])
        if created is not None and self.created[0] == utterance_id:
            return "object", created
        selection = Gui.Selection.getSelection()
        if len(selection) == 1:
            return "object", selection[0]
        in_edit = Gui.ActiveDocument.getInEdit() if Gui.ActiveDocument else None
        if in_edit is not None:
            return "object", in_edit.Object
        if created is not None:
            return "object", created
        try:                                   # the active view may be no 3D view (a spreadsheet)
            body = Gui.ActiveDocument.ActiveView.getActiveObject("pdbody")
        except Exception:
            body = None
        if body is not None:
            return "object", body
        return None

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
            return False, translate("TalkToMe", "nothing to pick")
        asking["popup"].close()
        command = asking["options"][index]
        ok, reason, shown = self.run_command(command, {}, None)
        self.report(asking["text"], shown, ok, reason)
        if not ok:
            return ok, reason
        learned = classify(asking["text"], command, asking["candidates"], self.language) == "learn"
        if learned:
            data = ttm_context.read_custom(self.language)
            ttm_context.save_custom(self.language, learn(data, command, heard=[asking["text"]]))
            self.reload_vocabulary()
            log("learned »{}« for {}".format(asking["text"], command))
        label = next((c.get("label") or c["id"] for c in asking["candidates"] if c["id"] == command), command)
        for miss in reversed(self.misses):     # shown as assigned in the training page
            if miss["text"] == asking["text"] and not miss.get("assigned"):
                miss["assigned"] = {"command": command, "label": label,
                                    "forms": [asking["text"]] if learned else []}
                break
        if self.trainer is not None:
            self.trainer.fill_misses()
        return ok, reason

    # --- executing ------------------------------------------------------------------------------

    def report(self, text, shown, ok, reason):
        if ok:
            self.status("»{}« → {}{}".format(text, shown, "  ({})".format(reason) if reason else ""))
            App.Console.PrintMessage("Talk to me: »{}« → {}\n".format(text, shown))
        else:
            self.status(translate("TalkToMe", "»{}« → {} failed: {}").format(text, shown, reason))
            App.Console.PrintWarning(translate("TalkToMe", "Talk to me: »{}« → {} failed: {}\n").format(text, shown, reason))

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
            shown += translate("TalkToMe", " (from help text)")
        self.report(text, shown, ok, reason)
        self.send("result", ok=ok, id=msg.get("id"))

    def run_command(self, command, args, utterance_id):
        """Execute one command. Returns (ok, reason, how to show it)."""
        doc = App.ActiveDocument
        doc_name, before = (doc.Name, {o.Name for o in doc.Objects}) if doc else (None, set())
        if command == "ui:mic_off":
            self.action.setChecked(False)      # switching on again is the button's job
            ok, reason = True, ""
        elif command == "ui:train":            # "Zeige mal den Lerndialog"
            self.open_training()
            ok, reason = True, ""
        elif PARAMS.GetBool("DryRun", False):
            ok, reason = True, translate("TalkToMe", "dry run, not executed")
        elif command == "ui:values":
            values = [tuple(v) for v in args.get("values", [])]
            if executor.value_fields() or ttm_context.dialog_value_fields():
                ok, reason = executor.fill_values(values, self.tool_command) > 0, ""
            elif ttm_context.tool_running():
                self.pending_values = values
                ok, reason = True, translate("TalkToMe", "values wait for the first click")
            else:
                ok, reason = False, translate("TalkToMe", "no tool waiting for values")
            command = translate("TalkToMe", "values {}").format(
                ", ".join(executor.quantity(v, "°" if k == "angle" else "mm") for _, v, k in values))
        elif command == "ui:rename":
            label = args.get("label", "")
            if args.get("target"):             # "Benenne den Körper2 in Grundplatte um"
                kind, target = self.named_object(args["target"])
            else:
                kind, target = self.rename_target(utterance_id) or (None, None)
            if kind is None:
                ok, reason = False, (translate("TalkToMe", "no object »{}« in the document").format(args["target"])
                                     if args.get("target") else translate("TalkToMe", "nothing to rename: select an object"))
            elif kind == "dialog":
                field = executor.datum_name_field(target)
                field.setText(executor.constraint_name(label))
                ok, reason, command = True, "", translate("TalkToMe", "dimension name »{}«").format(field.text())
            elif kind == "constraint":
                sketch, index = target
                ok, reason = executor.rename_constraint(sketch, index, label)
                command = translate("TalkToMe", "rename dimension {} to »{}«").format(index + 1, sketch.Constraints[index].Name)
            else:
                ok, reason = executor.rename(target, label)
                command = translate("TalkToMe", "rename {} to »{}«").format(target.Name, target.Label)
        else:
            try:
                ok, reason = executor.execute(command)
            except Exception as e:
                ok, reason = False, str(e)
            if ok:
                self.remember_created(doc_name, before, utterance_id)
                self.tool_command = command if ttm_context.tool_running() else None
        return ok, reason, command


_controller = None


def restart_service():
    if _controller is not None:
        _controller.restart_service()


def stop_service():
    """Stop the speech service and switch the microphone off (before removing the service)."""
    if _controller is not None:
        _controller.shutdown()
        _controller.action.blockSignals(True)
        _controller.action.setChecked(False)
        _controller.action.blockSignals(False)
        _controller.want_listen = False
        _controller.set_state("off")


def open_vocabulary(parent=None):
    if _controller is not None:
        _controller.open_vocabulary(parent)


def open_training(parent=None):
    if _controller is not None:
        _controller.open_training(parent)


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
