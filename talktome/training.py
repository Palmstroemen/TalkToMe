# SPDX-License-Identifier: LGPL-2.1-or-later
"""Training page: teach Talk to me how the speech recognition hears you (DESIGN.md 8.7).

1. Pick what was meant: a recently not understood utterance, a command from the list, or type
   the sentence.
2. Say it a few times. The service only transcribes meanwhile; each recording shows whether it is
   understood already, will be learned, or would mean another command.
3. Save: learned forms go to the user's vocabulary file.
"""

import time

from talktome import context as ttm_context
from talktome.qt import QtCore, QtWidgets
from ttm_core.decision import decide
from ttm_core.training import classify, learn

RECORDINGS = 3
MARKS = {
    "ok":       ("✓", "understood already"),
    "learn":    ("+", "will be learned"),
    "conflict": ("⚠", "means {other}, not stored"),
    "empty":    ("–", "nothing recognized"),
}


def describe(candidate):
    """A command as shown in the list: its first phrase and its ID."""
    label = candidate.get("label") or (candidate.get("phrases") or candidate.get("foreign") or [candidate["id"]])[0]
    return "{}   ({})".format(label, candidate["id"])


class TrainingDialog(QtWidgets.QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Talk to me – Training")
        self.setModal(False)
        self.candidates = list(controller.last_candidates or [])
        self.recordings = []            # (text, verdict)
        self.recording = False

        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(QtWidgets.QLabel("<b>1. What did you mean?</b>"))
        layout.addWidget(QtWidgets.QLabel("Recently not understood:"))
        self.misses = QtWidgets.QListWidget()
        self.misses.setMaximumHeight(90)
        for miss in reversed(controller.misses):
            item = QtWidgets.QListWidgetItem("{}  »{}«".format(
                time.strftime("%H:%M:%S", time.localtime(miss["time"])), miss["text"]))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, miss)
            self.misses.addItem(item)
        self.misses.currentItemChanged.connect(self.on_miss)
        layout.addWidget(self.misses)

        row = QtWidgets.QHBoxLayout()
        self.typed = QtWidgets.QLineEdit()
        self.typed.setPlaceholderText("or type the sentence you meant, e.g. »Skizze in der XY-Ebene«")
        self.typed.returnPressed.connect(self.on_typed)
        find = QtWidgets.QPushButton("Find")
        find.clicked.connect(self.on_typed)
        row.addWidget(self.typed)
        row.addWidget(find)
        layout.addLayout(row)

        self.filter = QtWidgets.QLineEdit()
        self.filter.setPlaceholderText("Filter commands")
        self.filter.textChanged.connect(self.fill_commands)
        layout.addWidget(self.filter)
        self.commands = QtWidgets.QListWidget()
        self.commands.currentItemChanged.connect(self.update_buttons)
        layout.addWidget(self.commands)

        layout.addWidget(QtWidgets.QLabel("<b>2. Say it {} times</b>".format(RECORDINGS)))
        self.record = QtWidgets.QPushButton("Start recording")
        self.record.setCheckable(True)
        self.record.toggled.connect(self.on_record)
        layout.addWidget(self.record)
        self.results = QtWidgets.QListWidget()
        self.results.setMaximumHeight(110)
        layout.addWidget(self.results)

        buttons = QtWidgets.QDialogButtonBox()
        self.save = buttons.addButton("Save", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        close = buttons.addButton("Close", QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        self.save.clicked.connect(self.on_save)
        close.clicked.connect(self.close)
        layout.addWidget(buttons)

        self.resize(560, 620)
        self.fill_commands()
        if self.misses.count():
            self.misses.setCurrentRow(0)

    # --- step 1: what was meant ----------------------------------------------------------

    def target(self):
        item = self.commands.currentItem()
        return item.data(QtCore.Qt.ItemDataRole.UserRole) if item else None

    def fill_commands(self, *args, first=()):
        """The candidates of the situation, the given ones first, filtered by the filter text."""
        current = self.target()
        words = self.filter.text().lower().split()
        ordered = [c for c in self.candidates if c["id"] in first]
        ordered.sort(key=lambda c: list(first).index(c["id"]))
        ordered += [c for c in self.candidates if c["id"] not in first]
        self.commands.clear()
        for c in ordered:
            label = describe(c)
            if all(w in label.lower() for w in words):
                item = QtWidgets.QListWidgetItem(label)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, c["id"])
                self.commands.addItem(item)
                if c["id"] == current:
                    self.commands.setCurrentItem(item)
        self.update_buttons()

    def select_command(self, command):
        for row in range(self.commands.count()):
            if self.commands.item(row).data(QtCore.Qt.ItemDataRole.UserRole) == command:
                self.commands.setCurrentRow(row)
                return True
        return False

    def on_miss(self, item, *args):
        """A missed utterance brings its own situation: the candidates of that moment (a dialog
        may have been open then), its likely commands first."""
        if item is None:
            return
        miss = item.data(QtCore.Qt.ItemDataRole.UserRole)
        self.candidates = miss["candidates"] or self.candidates
        likely = [cmd for cmd, _ in miss.get("alternatives") or []]
        self.fill_commands(first=likely)
        if likely:
            self.select_command(likely[0])

    def on_typed(self):
        text = self.typed.text().strip()
        if not text:
            return
        everything_active = [dict(c, active=True) for c in self.candidates]
        d = decide(text, everything_active, self.controller.language)
        if d.command and d.kind != "ignore":
            self.fill_commands(first=[cmd for cmd, _ in d.alternatives])
            self.select_command(d.command)
        else:
            self.controller.status("no command found for »{}«, pick one from the list".format(text))

    # --- step 2: recordings ----------------------------------------------------------------

    def on_record(self, on):
        self.recording = on
        self.record.setText("Stop recording" if on else "Start recording")
        if on:
            self.recordings = []
            self.results.clear()
            self.controller.start_training(self.candidates)
        else:
            self.controller.stop_training()
        self.update_buttons()

    def add_recording(self, text):
        """Called by the controller for each transcript while recording."""
        target = self.target()
        if not self.recording or target is None:
            return
        verdict = classify(text, target, self.candidates, self.controller.language)
        mark, note = MARKS[verdict]
        if verdict == "conflict":
            everything_active = [dict(c, active=True) for c in self.candidates]
            note = note.format(other=decide(text, everything_active, self.controller.language).command)
        self.recordings.append((text, verdict))
        self.results.addItem("{}  »{}«  {}".format(mark, text, note))
        if len(self.recordings) >= RECORDINGS:
            self.record.setChecked(False)
        self.update_buttons()

    # --- step 3: save ---------------------------------------------------------------------------

    def update_buttons(self, *args):
        has_target = self.target() is not None
        self.record.setEnabled(has_target or self.recording)
        learned = [t for t, v in self.recordings if v == "learn"]
        self.save.setEnabled(has_target and not self.recording and bool(learned or self.typed.text().strip()))

    def on_save(self):
        target = self.target()
        learned = [t for t, v in self.recordings if v == "learn"]
        language = self.controller.language
        typed = self.typed.text().strip() or None
        if typed and classify(typed, target, self.candidates, language) != "learn":
            typed = None                       # already understood (or another command's words)
        data = ttm_context.read_custom(language)
        learn(data, target, heard=learned, typed=typed)
        ttm_context.save_custom(language, data)
        self.controller.reload_vocabulary()
        self.controller.status("learned {} form(s){} for {}".format(
            len(learned), " and »{}«".format(typed) if typed else "", target))
        self.recordings = []
        self.results.clear()
        self.typed.clear()
        self.update_buttons()

    def closeEvent(self, event):
        if self.recording:
            self.record.setChecked(False)
        self.controller.trainer = None
        super().closeEvent(event)
