# SPDX-License-Identifier: LGPL-2.1-or-later
"""Install the speech service from FreeCAD: a dialog that says what is downloaded, creates the
service's Python environment in the user folder and installs its packages (ttm_core/install.py).
"""

import ctypes.util
import os
import shutil
import subprocess
import sys

from talktome import context as ttm_context
from talktome.qt import QT_TRANSLATE_NOOP, QtCore, QtWidgets, translate
from ttm_core import install

WINDOWS = sys.platform.startswith("win")
ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIREMENTS = os.path.join(ADDON_DIR, "service", "requirements.txt")
# Finder starts FreeCAD with a short PATH; Pythons of python.org and Homebrew are not on it.
MAC_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "/Library/Frameworks/Python.framework/Versions/Current/bin")

HINTS = {
    "venv": QT_TRANSLATE_NOOP("TalkToMe", "Python's module for environments is missing. On Debian, Ubuntu and Mint: "
                                          "<code>sudo apt install python3-venv</code>, then install again."),
    "portaudio": QT_TRANSLATE_NOOP("TalkToMe", "The audio library PortAudio is missing. On Debian, Ubuntu and Mint: "
                                               "<code>sudo apt install libportaudio2</code>."),
    "network": QT_TRANSLATE_NOOP("TalkToMe", "No connection to the Python Package Index (pypi.org). Check the "
                                             "internet connection and install again."),
    "disk": QT_TRANSLATE_NOOP("TalkToMe", "Not enough disk space: the speech service needs about 550 MB, "
                                          "its GPU support about 2 GB more."),
    "python_version": QT_TRANSLATE_NOOP("TalkToMe", "The packages are not available for this Python or system. "
                                                    "Tested with Python 3.10."),
}


def venv():
    return install.venv_dir(ttm_context.user_dir())


def installed():
    """The environment in the user folder exists (not one set by hand or in the addon folder)."""
    return os.path.exists(install.venv_python(venv(), WINDOWS))


def clean_environment():
    from talktome.gui import FOREIGN_ENV
    return {k: v for k, v in os.environ.items() if k not in FOREIGN_ENV}


def version_of(program, args):
    """(major, minor) of a Python, or None."""
    try:
        out = subprocess.run([program] + list(args) + ["-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                             env=clean_environment(), capture_output=True, text=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    return install.parse_version(out.stdout)


def system_python():
    """(program, args, version) of the system's Python for the environment, or None."""
    dirs = install.search_path(os.environ.get("PATH", ""), os.environ.get("APPDIR"))
    if sys.platform == "darwin":
        dirs = [d for d in MAC_DIRS if d not in dirs] + dirs
    return install.find_python(dirs, version_of, windows=WINDOWS)


def no_python_hint():
    if WINDOWS:
        return translate("TalkToMe", "Install Python from python.org, then open this dialog again.")
    if sys.platform == "darwin":
        return translate("TalkToMe", "Install Python from python.org or with Homebrew, then open this dialog again.")
    return translate("TalkToMe", "Install it with the package manager of your system, on Debian, Ubuntu and Mint: "
                                 "<code>sudo apt install python3 python3-venv</code>.")


def nvidia_driver():
    """The NVIDIA graphics driver is installed (its CUDA library); macOS has none."""
    if WINDOWS:
        return ctypes.util.find_library("nvcuda") is not None
    return sys.platform.startswith("linux") and ctypes.util.find_library("cuda") is not None


def gpu_installed():
    return bool(install.cuda_library_dirs(venv(), WINDOWS))


def portaudio_missing():
    """On Linux the audio library comes from the system; elsewhere it comes with sounddevice."""
    return sys.platform.startswith("linux") and ctypes.util.find_library("portaudio") is None


class InstallDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("TalkToMe", "Talk to me: install the speech service"))
        self.setMinimumWidth(560)
        self.venv = venv()
        self.have_venv = installed()
        self.base = None if self.have_venv else system_python()
        self.process = None
        self.steps = []
        self.output = ""
        self.succeeded = False                # not "done": that is QDialog.done(), which reject() calls

        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(translate("TalkToMe",
            "Talk to me recognizes speech in a Python environment of its own, apart from FreeCAD's Python. "
            "Installing it downloads:"
            "<ul><li>the Python packages faster-whisper, Piper, sounddevice and numpy from the Python Package "
            "Index (pypi.org): about 550 MB on disk, in <code>{}</code></li>"
            "<li>on the first start of the microphone, the speech recognition model from Hugging Face "
            "(\"base\": about 150 MB) and the voice of the speech output (about 60 MB)</li></ul>"
            "After that, everything runs on this computer: what you say is not sent anywhere.").format(self.venv))
        intro.setWordWrap(True)
        intro.setTextFormat(QtCore.Qt.TextFormat.RichText)
        layout.addWidget(intro)

        self.python_label = QtWidgets.QLabel()
        self.python_label.setWordWrap(True)
        self.python_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.python_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.python_label)

        self.offer_gpu = nvidia_driver() or gpu_installed()
        self.gpu = QtWidgets.QCheckBox(translate("TalkToMe", "Also install the GPU support for the NVIDIA graphics card"))
        self.gpu.setChecked(gpu_installed())        # an update keeps it up to date
        gpu_hint = QtWidgets.QLabel(translate("TalkToMe",
            "Faster recognition and the more accurate models. Downloads NVIDIA's CUDA libraries from pypi.org: "
            "about 1.3 GB more."))
        gpu_hint.setWordWrap(True)
        gpu_hint.setContentsMargins(24, 0, 0, 0)
        for widget in (self.gpu, gpu_hint):
            widget.setVisible(self.offer_gpu)
            layout.addWidget(widget)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(180)
        layout.addWidget(self.log)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.result = QtWidgets.QLabel()
        self.result.setWordWrap(True)
        self.result.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.result.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.result)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        self.install_button = QtWidgets.QPushButton(
            translate("TalkToMe", "Update") if self.have_venv else translate("TalkToMe", "Install"))
        self.install_button.clicked.connect(self.start)
        self.close_button = QtWidgets.QPushButton(translate("TalkToMe", "Close"))
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.install_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self.show_python()

    def show_python(self):
        notes = []
        if self.have_venv:
            notes.append(translate("TalkToMe", "Installed. \"Update\" installs newer packages the addon needs."))
        elif self.base is None:
            notes.append("<b>{}</b> {}".format(
                translate("TalkToMe", "No Python {}.{} or newer found.").format(*install.MIN_PYTHON), no_python_hint()))
            self.install_button.setEnabled(False)
        else:
            program, args, version = self.base
            notes.append(translate("TalkToMe", "Python used: <code>{}</code> ({}.{})").format(
                " ".join([program] + args), *version))
        if portaudio_missing():
            notes.append(translate("TalkToMe", HINTS["portaudio"]))
        self.python_label.setText("<br>".join(notes))

    # --- running the steps -------------------------------------------------------------------

    def start(self):
        self.install_button.setEnabled(False)
        self.result.setText("")
        self.output = ""
        base = self.base[:2] if self.base else None
        self.steps = install.install_steps(base, self.venv, REQUIREMENTS, self.have_venv, WINDOWS,
                                           gpu=self.offer_gpu and self.gpu.isChecked())
        self.gpu.setEnabled(False)
        self.progress.show()
        self.run_next()

    def run_next(self):
        if not self.steps:
            self.finish()
            return
        self.step, program, args = self.steps.pop(0)
        self.output = ""
        self.append("$ {}".format(" ".join([program] + args)))
        env = QtCore.QProcessEnvironment()
        for key, value in clean_environment().items():
            env.insert(key, value)
        self.process = QtCore.QProcess(self)
        self.process.setProcessEnvironment(env)
        self.process.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.on_output)
        self.process.finished.connect(self.on_finished)
        self.process.errorOccurred.connect(self.on_error)
        self.process.start(program, args)

    def on_output(self):
        text = self.process.readAllStandardOutput().data().decode("utf-8", "replace")
        self.output += text
        self.append(text.rstrip("\n"))

    def append(self, text):
        self.log.appendPlainText(text)
        bar = self.log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def on_error(self, error):
        if error == QtCore.QProcess.ProcessError.FailedToStart:
            self.output += self.process.errorString()
            self.fail()

    def on_finished(self, code, status=None):
        if self.process is None:
            return
        self.process = None
        if code != 0:
            self.fail()
            return
        if self.step == "venv":
            self.have_venv = True
        self.run_next()

    def fail(self):
        self.process = None
        self.steps = []
        self.progress.hide()
        if self.step == "venv":                # half an environment: without pip it can't be used
            shutil.rmtree(self.venv, ignore_errors=True)
            self.have_venv = False
        hints = [translate("TalkToMe", HINTS[k]) for k in install.diagnose(self.output)]
        self.result.setText("<b>{}</b> {}".format(
            translate("TalkToMe", "Installation failed."),
            " ".join(hints) or translate("TalkToMe", "The output above says why.")))
        self.install_button.setText(translate("TalkToMe", "Install again"))
        self.install_button.setEnabled(True)
        self.gpu.setEnabled(True)

    def finish(self):
        """Check that the service's Python finds its packages and a microphone."""
        import talktome.gui
        self.append(translate("TalkToMe", "Checking the speech service ..."))
        QtWidgets.QApplication.processEvents()   # show it before the check blocks
        probe = talktome.gui.probe_service(timeout_ms=30000)
        self.progress.hide()
        self.succeeded = bool(probe)
        self.install_button.setText(translate("TalkToMe", "Update"))
        self.install_button.setEnabled(True)
        self.gpu.setEnabled(True)
        self.close_button.setDefault(True)
        if not probe:
            self.result.setText("<b>{}</b>".format(translate("TalkToMe",
                "The packages are installed, but the speech service does not start. The Report view may say why.")))
        elif probe.get("error"):
            hints = [translate("TalkToMe", HINTS[k]) for k in install.diagnose(probe["error"])]
            self.result.setText("<b>{}</b> {}".format(
                translate("TalkToMe", "Installed, but the microphone is not usable yet."),
                " ".join(hints) or probe["error"]))
        else:
            notes = [translate("TalkToMe", "Switch on the microphone with the button in the toolbar \"Talk to me\"; "
                                           "its first start downloads the model.")]
            if probe.get("cuda_libraries"):
                notes.append(translate("TalkToMe", "If it is on already, switch it off and on again to use the GPU. "
                                                   "If the GPU does not work, the CPU is used and the status bar says so."))
            self.result.setText("<b>{}</b> {}".format(translate("TalkToMe", "Installed."), " ".join(notes)))

    def reject(self):
        if self.process is not None:
            self.process.finished.disconnect(self.on_finished)
            self.process.kill()
            self.process.waitForFinished(3000)
            self.process = None
            if self.step == "venv":
                shutil.rmtree(self.venv, ignore_errors=True)
        super().reject()


def run(parent=None):
    """Show the dialog; True if the speech service was installed."""
    dialog = InstallDialog(parent)
    (getattr(dialog, "exec", None) or dialog.exec_)()      # exec_ before PySide6
    return dialog.succeeded


def remove(parent=None):
    """Remove the environment in the user folder after asking; True if removed."""
    import talktome.gui
    answer = QtWidgets.QMessageBox.question(parent, translate("TalkToMe", "Talk to me"), translate("TalkToMe",
        "Remove the speech service ({})?\n\nDownloaded models (~/.cache/huggingface) and voices "
        "(~/.cache/talktome) stay; delete them by hand if you don't need them any more.").format(venv()))
    if answer != QtWidgets.QMessageBox.StandardButton.Yes:
        return False
    talktome.gui.stop_service()
    shutil.rmtree(venv(), ignore_errors=True)
    return True
