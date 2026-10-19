# SPDX-License-Identifier: LGPL-2.1-or-later
"""Settings page: Edit → Preferences → Talk to me (DESIGN.md 13).

Settings are FreeCAD parameters (BaseApp/Preferences/Mod/TalkToMe); word lists are saved as the
user's changes to the language pack. Changes that the speech service reads at its start
(language, model, microphone, voice, lists, ...) restart a running service.
"""

import os

from talktome import context as ttm_context
from talktome.qt import QT_TRANSLATE_NOOP, QtCore, QtGui, QtWidgets, translate
from ttm_core import langpack

import FreeCAD as App

PARAMS = App.ParamGet("User parameter:BaseApp/Preferences/Mod/TalkToMe")

MODELS = [
    ("", QT_TRANSLATE_NOOP("TalkToMe", "Automatic (by hardware)")),
    ("tiny", QT_TRANSLATE_NOOP("TalkToMe", "tiny – fastest, least accurate (~75 MB)")),
    ("base", QT_TRANSLATE_NOOP("TalkToMe", "base – good choice on a CPU (~150 MB)")),
    ("small", QT_TRANSLATE_NOOP("TalkToMe", "small – more accurate, quick with a GPU (~500 MB)")),
    ("medium", QT_TRANSLATE_NOOP("TalkToMe", "medium – most accurate, needs a GPU (~1.5 GB)")),
]
DEVICES = [("auto", QT_TRANSLATE_NOOP("TalkToMe", "Automatic")), ("cpu", QT_TRANSLATE_NOOP("TalkToMe", "CPU")), ("cuda", QT_TRANSLATE_NOOP("TalkToMe", "GPU (CUDA)"))]
SPEECH = [
    ("off", QT_TRANSLATE_NOOP("TalkToMe", "Off – tones only")),
    ("important", QT_TRANSLATE_NOOP("TalkToMe", "Important moments – not understood, questions, training")),
    ("chatty", QT_TRANSLATE_NOOP("TalkToMe", "Chatty – also confirmations (\"Mache ich.\")")),
]
LISTS = {
    "filler_words": QT_TRANSLATE_NOOP("TalkToMe", "Filler words – said around commands; a sentence of only these is ignored"),
    "stop_words": QT_TRANSLATE_NOOP("TalkToMe", "Further stop words – without meaning for finding a command"),
    "parameter_words": QT_TRANSLATE_NOOP("TalkToMe", "Number and unit words – parameters, left out when comparing"),
    "clause_words": QT_TRANSLATE_NOOP("TalkToMe", "Clause words – split a sentence into steps (\"und\", \"dann\")"),
    "particles": QT_TRANSLATE_NOOP("TalkToMe", "Verb particles – end of separable verbs (\"zieht … ab\")"),
}

# Read by the service at its start: a change restarts a running service.
RESTART = ("Language", "Microphone", "Volume", "Model", "Device", "Speech", "Voice", "ServicePython", "ExtraArgs")


def hint(text):
    label = QtWidgets.QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color: gray;")
    return label


def combo(items):
    box = QtWidgets.QComboBox()
    for value, text in items:
        box.addItem(translate("TalkToMe", text), value)
    return box


def select(box, value):
    index = box.findData(value)
    if index < 0:                              # a value not offered (e.g. a microphone gone)
        box.addItem(str(value), value)
        index = box.count() - 1
    box.setCurrentIndex(index)


def browse_row(edit, caption, file_filter):
    row = QtWidgets.QHBoxLayout()
    row.addWidget(edit)
    button = QtWidgets.QPushButton(translate("TalkToMe", "Browse…"))

    def choose():
        path, _ = QtWidgets.QFileDialog.getOpenFileName(edit, caption, edit.text(), file_filter)
        if path:
            edit.setText(path)
    button.clicked.connect(choose)
    row.addWidget(button)
    return row


class PreferencesPage:
    def __init__(self, parent=None):
        self.form = QtWidgets.QWidget(parent)
        self.form.setWindowTitle(translate("TalkToMe", "Voice control"))     # the page's name in the group
        self.probe = None
        self.lists = {}                  # list key → words as edited
        self.list_language = None
        tabs = QtWidgets.QTabWidget()
        QtWidgets.QVBoxLayout(self.form).addWidget(tabs)
        tabs.addTab(self.general_tab(), translate("TalkToMe", "General"))
        tabs.addTab(self.recognition_tab(), translate("TalkToMe", "Recognition"))
        tabs.addTab(self.behavior_tab(), translate("TalkToMe", "Behavior"))
        tabs.addTab(self.language_tab(), translate("TalkToMe", "Language"))
        tabs.addTab(self.expert_tab(), translate("TalkToMe", "Expert"))

    # --- tabs ------------------------------------------------------------------------------

    def general_tab(self):
        tab = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(tab)
        self.language = combo([(code, "{} ({})".format(langpack.pack(code).name, code)) for code in langpack.languages()])
        self.language.currentIndexChanged.connect(self.on_language)
        form.addRow(translate("TalkToMe", "Spoken language:"), self.language)
        self.microphone = QtWidgets.QComboBox()
        form.addRow(translate("TalkToMe", "Microphone:"), self.microphone)
        row = QtWidgets.QHBoxLayout()
        self.volume = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        volume_label = QtWidgets.QLabel()
        self.volume.valueChanged.connect(lambda v: volume_label.setText("{} %".format(v)))
        row.addWidget(self.volume)
        row.addWidget(volume_label)
        form.addRow(translate("TalkToMe", "Volume of tones and voice:"), row)
        form.addRow(hint(translate("TalkToMe", "The microphone is switched on and off with the button in the toolbar "
                         "\"Talk to me\". A keyboard shortcut for it: Tools → Customize → Keyboard.")))
        return tab

    def recognition_tab(self):
        tab = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(tab)
        self.model = combo(MODELS)
        form.addRow(translate("TalkToMe", "Speech recognition model:"), self.model)
        self.device = combo(DEVICES)
        form.addRow(translate("TalkToMe", "Run on:"), self.device)
        self.found = hint("")
        form.addRow("", self.found)
        form.addRow(hint(translate("TalkToMe", "Larger models recognize better but take longer. Without a GPU, \"base\" "
                         "answers in about a second. A new model is downloaded on its first use.")))
        return tab

    def behavior_tab(self):
        tab = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(tab)
        self.ask = QtWidgets.QCheckBox(translate("TalkToMe", "Offer the likely commands next to the mouse pointer when not sure"))
        form.addRow(self.ask)
        self.speech = combo(SPEECH)
        form.addRow(translate("TalkToMe", "Speech output:"), self.speech)
        self.voice = QtWidgets.QLineEdit()
        self.voice.setPlaceholderText(translate("TalkToMe", "default voice of the language"))
        form.addRow(translate("TalkToMe", "Voice:"), browse_row(self.voice, translate("TalkToMe", "Piper voice"), "Piper voices (*.onnx)"))
        self.voice_hint = hint("")
        form.addRow("", self.voice_hint)
        self.dry_run = QtWidgets.QCheckBox(translate("TalkToMe", "Only show what was recognized, don't execute (for testing)"))
        form.addRow(self.dry_run)
        return tab

    def language_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.addWidget(hint(translate("TalkToMe", "Word lists of the spoken language. Your changes are kept apart from "
                              "the language pack, in your own folder; \"Reset\" brings back the pack's list.")))
        self.list_key = combo(list(LISTS.items()))
        self.list_key.currentIndexChanged.connect(self.show_list)
        layout.addWidget(self.list_key)
        self.words = QtWidgets.QPlainTextEdit()
        self.words.setPlaceholderText(translate("TalkToMe", "one word per line"))
        self.words.textChanged.connect(self.on_words)
        layout.addWidget(self.words)
        row = QtWidgets.QHBoxLayout()
        reset = QtWidgets.QPushButton(translate("TalkToMe", "Reset this list"))
        reset.clicked.connect(self.reset_list)
        training = QtWidgets.QPushButton(translate("TalkToMe", "Training…"))
        training.clicked.connect(self.open_training)
        vocabulary = QtWidgets.QPushButton(translate("TalkToMe", "Vocabulary…"))
        vocabulary.setToolTip(translate("TalkToMe", "Your phrases and what training learned, by command"))
        vocabulary.clicked.connect(self.open_vocabulary)
        folder = QtWidgets.QPushButton(translate("TalkToMe", "Open my folder"))
        folder.setToolTip(ttm_context.user_dir())
        folder.clicked.connect(self.open_folder)
        row.addWidget(reset)
        row.addStretch()
        row.addWidget(training)
        row.addWidget(vocabulary)
        row.addWidget(folder)
        layout.addLayout(row)
        return tab

    def expert_tab(self):
        tab = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(tab)
        self.python = QtWidgets.QLineEdit()
        self.python.setPlaceholderText(translate("TalkToMe", "service/.venv/bin/python of the addon"))
        form.addRow(translate("TalkToMe", "Python of the speech service:"), browse_row(self.python, "Python", "Python (python*)"))
        self.extra = QtWidgets.QLineEdit()
        form.addRow(translate("TalkToMe", "Extra arguments:"), self.extra)
        form.addRow(hint(translate("TalkToMe", "Extra arguments are passed to the speech service, e.g. \"--beam 3\". "
                         "See: python -m talktome_service --help")))
        return tab

    # --- language lists ---------------------------------------------------------------------

    def current_list_key(self):
        return self.list_key.currentData()

    def on_language(self, *args):
        """Lists belong to a language: switching it drops unsaved edits of the previous one."""
        self.list_language = self.language.currentData()
        self.lists = {}
        self.show_list()

    def show_list(self, *args):
        key = self.current_list_key()
        words = self.lists.get(key)
        if words is None:
            words = sorted(getattr(langpack.pack(self.list_language), key, set()) - (
                langpack.pack(self.list_language).filler_words | langpack.pack(self.list_language).particles
                if key == "stop_words" else set()))
        self.words.blockSignals(True)
        self.words.setPlainText("\n".join(words))
        self.words.blockSignals(False)

    def on_words(self):
        self.lists[self.current_list_key()] = self.words.toPlainText().split()

    def reset_list(self):
        key = self.current_list_key()
        self.lists[key] = langpack.pack_list(self.list_language, key)
        self.show_list()

    def open_training(self):
        import talktome.gui
        talktome.gui.open_training(self.form.window())

    def open_vocabulary(self):
        import talktome.gui
        talktome.gui.open_vocabulary(self.form.window())

    def open_folder(self):
        os.makedirs(ttm_context.user_dir(), exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(ttm_context.user_dir()))

    # --- FreeCAD's interface -----------------------------------------------------------------

    def loadSettings(self):
        import talktome.gui
        if self.probe is None:
            self.probe = talktome.gui.probe_service()
        select(self.language, PARAMS.GetString("Language", "de"))
        self.on_language()

        self.microphone.clear()
        self.microphone.addItem(translate("TalkToMe", "System default"), "")
        for mic in self.probe.get("microphones", []):
            self.microphone.addItem(mic["name"], mic["name"])
        select(self.microphone, PARAMS.GetString("Microphone", ""))
        self.volume.setValue(PARAMS.GetInt("Volume", 40))

        select(self.model, PARAMS.GetString("Model", ""))
        select(self.device, PARAMS.GetString("Device", "auto"))
        if not self.probe:
            self.found.setText(translate("TalkToMe", "The speech service is not installed yet, see README."))
        else:
            n = self.probe.get("cuda_devices", 0)
            self.found.setText(translate("TalkToMe", "Found: {} CUDA GPU(s).").format(n) if n
                               else translate("TalkToMe", "No CUDA GPU found: the CPU is used."))

        self.ask.setChecked(PARAMS.GetBool("AskMenu", True))
        select(self.speech, PARAMS.GetString("Speech", "important"))
        self.voice.setText(PARAMS.GetString("Voice", ""))
        voice = langpack.pack(self.language.currentData()).voice
        self.voice_hint.setText(
            (translate("TalkToMe", "Default: {}. Any Piper voice (name or .onnx file) works; check its license.").format(voice)
             if self.probe.get("speech", True) else translate("TalkToMe", "Speech output needs piper-tts in the service's Python.")))
        self.dry_run.setChecked(PARAMS.GetBool("DryRun", False))

        self.python.setText(PARAMS.GetString("ServicePython", ""))
        self.extra.setText(PARAMS.GetString("ExtraArgs", ""))

    def saveSettings(self):
        before = {key: PARAMS.GetString(key, "") for key in RESTART if key != "Volume"}
        before["Volume"] = PARAMS.GetInt("Volume", 40)

        PARAMS.SetString("Language", self.language.currentData() or "de")
        PARAMS.SetString("Microphone", self.microphone.currentData() or "")
        PARAMS.SetInt("Volume", self.volume.value())
        PARAMS.SetString("Model", self.model.currentData() or "")
        PARAMS.SetString("Device", self.device.currentData() or "auto")
        PARAMS.SetBool("AskMenu", self.ask.isChecked())
        PARAMS.SetString("Speech", self.speech.currentData() or "important")
        PARAMS.SetString("Voice", self.voice.text().strip())
        PARAMS.SetBool("DryRun", self.dry_run.isChecked())
        PARAMS.SetString("ServicePython", self.python.text().strip())
        PARAMS.SetString("ExtraArgs", self.extra.text().strip())

        for key, words in self.lists.items():
            langpack.save_list(self.list_language, key, words)

        after = {key: PARAMS.GetString(key, "") for key in RESTART if key != "Volume"}
        after["Volume"] = PARAMS.GetInt("Volume", 40)
        if after != before or self.lists:
            import talktome.gui
            talktome.gui.restart_service()
        self.lists = {}
