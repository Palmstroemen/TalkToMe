# SPDX-License-Identifier: LGPL-2.1-or-later
"""Training page: teach Talk to me how the speech recognition hears you (DESIGN.md 8.7).

From top to bottom:
1. Sentences that were not understood, with the command assigned to them so far.
2. Say it again (optional): more recordings of the same sentence teach more forms.
3. Which command was meant: pick from the list (or type the sentence), then Assign or
   double-click. Assigning stores right away; Forget takes it back.

While recording, the service only transcribes, nothing is executed.
"""

import time

from talktome import context as ttm_context
from talktome.qt import QtCore, QtWidgets
from ttm_core.decision import decide
from ttm_core.params import make_template, parse
from ttm_core.training import classify, learn, unlearn

RECORDINGS = 3
ROLE = QtCore.Qt.ItemDataRole.UserRole

# Commands with a free-text parameter, recognized by sentence patterns, not by phrases. Training
# them learns a pattern: the heard sentence with the parameter cut out.
PARAMETER_COMMANDS = {"ui:rename": "Rename"}


def describe(candidate):
    """A command as shown in the list: FreeCAD's label and its ID."""
    label = candidate.get("label") or (candidate.get("phrases") or candidate.get("foreign") or [candidate["id"]])[0]
    return "{}   ({})".format(label, candidate["id"])


def hint(text):
    label = QtWidgets.QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color: gray;")
    return label


class TrainingDialog(QtWidgets.QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Talk to me – Training")
        self.setModal(False)
        self.candidates = self.situation(controller.last_candidates)
        self.recordings = []            # texts heard while recording
        self.recording = False

        layout = QtWidgets.QVBoxLayout(self)

        # 1. not understood sentences
        layout.addWidget(QtWidgets.QLabel("<b>Sentences I didn't understand</b>"))
        layout.addWidget(hint("Select one and show me below what you meant. "
                              "Next time I will understand it."))
        self.misses = QtWidgets.QTreeWidget()
        self.misses.setColumnCount(3)
        self.misses.setHeaderLabels(["Time", "Heard", "Meant"])
        self.misses.setRootIsDecorated(False)
        self.misses.setMaximumHeight(140)
        self.misses.currentItemChanged.connect(self.on_miss)
        layout.addWidget(self.misses)
        self.fill_misses()

        # 2. say it again
        layout.addWidget(QtWidgets.QLabel("<b>Say it again</b> (optional)"))
        layout.addWidget(hint("Each recording teaches me another way the speech recognition hears you. "
                              "You can also start here with a new sentence. Nothing is executed meanwhile."))
        row = QtWidgets.QHBoxLayout()
        self.record = QtWidgets.QPushButton("Say it {} times".format(RECORDINGS))
        self.record.setCheckable(True)
        self.record.toggled.connect(self.on_record)
        row.addWidget(self.record)
        row.addStretch()
        layout.addLayout(row)
        self.results = QtWidgets.QListWidget()
        self.results.setMaximumHeight(80)
        layout.addWidget(self.results)

        # 3. what was meant
        layout.addWidget(QtWidgets.QLabel("<b>Which command did you mean?</b>"))
        layout.addWidget(hint("Pick it and press Assign, or double-click it. The likely ones are on top. "
                              "You may also type the sentence you said to find it."))
        row = QtWidgets.QHBoxLayout()
        self.typed = QtWidgets.QLineEdit()
        self.typed.setPlaceholderText("type the sentence, e.g. »Skizze in der XY-Ebene«")
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
        self.commands.currentItemChanged.connect(self.on_target)
        self.commands.itemDoubleClicked.connect(self.assign)
        layout.addWidget(self.commands)

        self.name_row = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(self.name_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QtWidgets.QLabel("Which part is the name?"))
        self.name = QtWidgets.QLineEdit()
        self.name.setToolTip("The words of the sentence that were the name, e.g. »Bodenplatte«. "
                             "I learn the rest as a sentence pattern.")
        self.name.textChanged.connect(self.update_buttons)
        row.addWidget(self.name)
        self.name_row.setVisible(False)
        layout.addWidget(self.name_row)

        row = QtWidgets.QHBoxLayout()
        self.assign_button = QtWidgets.QPushButton("Assign")
        self.assign_button.clicked.connect(self.assign)
        self.forget_button = QtWidgets.QPushButton("Forget")
        self.forget_button.setToolTip("Take back the assignment of the selected sentence")
        self.forget_button.clicked.connect(self.forget)
        close = QtWidgets.QPushButton("Close")
        close.clicked.connect(self.close)
        row.addWidget(self.assign_button)
        row.addWidget(self.forget_button)
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)

        self.resize(600, 720)
        self.fill_commands()
        if self.misses.topLevelItemCount():
            self.misses.setCurrentItem(self.misses.topLevelItem(0))

    def situation(self, candidates):
        """The commands of a moment, plus those with a parameter (they are no candidates)."""
        candidates = list(candidates or [])
        vocab = self.controller.vocab
        for command, label in PARAMETER_COMMANDS.items():
            if command not in [c["id"] for c in candidates]:
                candidates.append({"id": command, "label": (vocab.get(command) or [label])[0],
                                   "phrases": [], "active": True})
        return candidates

    # --- 1. not understood sentences ---------------------------------------------------------

    def fill_misses(self):
        """Rebuild the table, keeping the selection (without reacting to it as a new choice)."""
        current = self.miss()
        self.misses.blockSignals(True)
        self.misses.clear()
        for miss in reversed(self.controller.misses):
            assigned = miss.get("assigned")
            item = QtWidgets.QTreeWidgetItem([
                time.strftime("%H:%M:%S", time.localtime(miss["time"])),
                "»{}«".format(miss["text"]),
                "→ {}  ✓".format(assigned["label"]) if assigned else ""])
            item.setData(0, ROLE, miss["id"])  # not the dict: Qt would store a copy of it
            self.misses.addTopLevelItem(item)
            if miss is current:
                self.misses.setCurrentItem(item)
        self.misses.blockSignals(False)
        for column in range(3):
            self.misses.resizeColumnToContents(column)

    def miss(self):
        """The selected sentence: the controller's own record, so changes are kept."""
        item = self.misses.currentItem()
        if item is None:
            return None
        number = item.data(0, ROLE)
        return next((m for m in self.controller.misses if m["id"] == number), None)

    def on_miss(self, item, *args):
        """A sentence brings its own situation: the commands of that moment (a dialog may have
        been open then), its likely commands first."""
        self.recordings = []
        self.results.clear()
        self.name.clear()
        miss = self.miss()
        if miss is None:
            return
        self.candidates = self.situation(miss["candidates"]) if miss["candidates"] else self.candidates
        likely = [cmd for cmd, _ in miss.get("alternatives") or []]
        assigned = miss.get("assigned")
        self.fill_commands(first=([assigned["command"]] if assigned else []) + likely)
        if self.commands.count():
            self.commands.setCurrentRow(0)

    # --- 2. recordings ------------------------------------------------------------------------

    def on_record(self, on):
        self.recording = on
        self.record.setText("Stop" if on else "Say it {} times".format(RECORDINGS))
        if on:
            self.recordings = []
            self.results.clear()
            self.controller.start_training(self.candidates)
        else:
            self.controller.stop_training()
        self.update_buttons()

    def add_recording(self, text):
        """Called by the controller for each transcript while recording."""
        if not self.recording:
            return
        self.recordings.append(text)
        self.results.addItem("»{}«".format(text) if text.strip() else "– nothing recognized")
        remaining = RECORDINGS - len(self.recordings)
        if remaining > 0:
            self.controller.send("say", kind="train_again", n=remaining)
        else:
            self.record.setChecked(False)
        self.update_buttons()

    # --- 3. what was meant -------------------------------------------------------------------

    def target(self):
        item = self.commands.currentItem()
        return item.data(ROLE) if item else None

    def fill_commands(self, *args, first=()):
        """The commands of the situation, the given ones first, filtered by the filter text."""
        current = self.target()
        first = list(dict.fromkeys(first))
        words = self.filter.text().lower().split()
        ordered = sorted((c for c in self.candidates if c["id"] in first), key=lambda c: first.index(c["id"]))
        ordered += [c for c in self.candidates if c["id"] not in first]
        self.commands.clear()
        for c in ordered:
            label = describe(c)
            if all(w in label.lower() for w in words):
                item = QtWidgets.QListWidgetItem(label)
                item.setData(ROLE, c["id"])
                self.commands.addItem(item)
                if c["id"] == current:
                    self.commands.setCurrentItem(item)
        self.update_buttons()

    def on_typed(self):
        text = self.typed.text().strip()
        if not text:
            return
        everything_active = [dict(c, active=True) for c in self.candidates]
        d = decide(text, everything_active, self.controller.language)
        if d.command and d.kind != "ignore":
            self.fill_commands(first=[cmd for cmd, _ in d.alternatives])
            self.commands.setCurrentRow(0)
        else:
            self.controller.status("no command found for »{}«, pick one from the list".format(text))
        self.update_buttons()

    def on_target(self, *args):
        """A command with a parameter asks which part of the sentence the parameter is."""
        is_parameter = self.target() in PARAMETER_COMMANDS
        self.name_row.setVisible(is_parameter)
        if is_parameter and not self.name.text():
            heard = self.heard_texts()
            words = heard[0].rstrip(".!?").split() if heard else []
            self.name.setText(words[-1] if words else "")      # a guess: names come last mostly
        self.update_buttons()

    def heard_texts(self):
        """The selected sentence (if not assigned yet) and the recordings, each once."""
        miss = self.miss()
        heard = ([miss["text"]] if miss is not None and not miss.get("assigned") else []) + self.recordings
        unique = {}
        for text in heard:
            unique.setdefault(text.lower(), text)
        return list(unique.values())

    def update_buttons(self, *args):
        miss = self.miss()
        open_miss = miss is not None and not miss.get("assigned")
        something = open_miss or bool(self.recordings) or bool(self.typed.text().strip())
        name_needed = self.target() in PARAMETER_COMMANDS and not self.name.text().strip()
        self.assign_button.setEnabled(self.target() is not None and something and not self.recording
                                      and not name_needed)
        self.forget_button.setEnabled(miss is not None and bool(miss.get("assigned")) and not self.recording)

    def assign(self, *args):
        """Store what was heard for the selected command, right away."""
        target = self.target()
        if target is None or self.recording:
            return
        if target in PARAMETER_COMMANDS:
            self.assign_pattern(target)
            return
        language = self.controller.language
        miss = self.miss()
        heard = self.heard_texts()
        verdicts = [(text, classify(text, target, self.candidates, language)) for text in heard]
        learned = [text for text, verdict in verdicts if verdict == "learn"]
        conflicts = [text for text, verdict in verdicts if verdict == "conflict"]
        typed = self.typed.text().strip() or None
        if typed and classify(typed, target, self.candidates, language) != "learn":
            typed = None                       # already understood (or another command's words)

        data = ttm_context.read_custom(language)
        learn(data, target, heard=learned, typed=typed)
        ttm_context.save_custom(language, data)
        self.controller.reload_vocabulary()

        label = next((c.get("label") or c["id"] for c in self.candidates if c["id"] == target), target)
        if miss is not None:
            miss["assigned"] = {"command": target, "label": label, "forms": learned}
        self.results.clear()
        for text, verdict in verdicts:
            mark = {"learn": "+ learned", "ok": "✓ understood already",
                    "conflict": "⚠ means another command, not stored", "empty": "– nothing recognized"}[verdict]
            self.results.addItem("{}  »{}«".format(mark, text))
        self.recordings = []
        self.typed.clear()
        self.fill_misses()
        if learned:
            self.controller.send("say", kind="train_done")
        self.controller.status("learned {} form(s) for {}{}".format(
            len(learned), label, ", {} not stored (another command)".format(len(conflicts)) if conflicts else ""))
        self.update_buttons()

    def assign_pattern(self, target):
        """Learn sentence patterns: each heard sentence with the name cut out."""
        language = self.controller.language
        miss = self.miss()
        name = self.name.text().strip()
        templates, marks = [], []
        for text in self.heard_texts():
            if parse(text, language, self.controller.patterns) is not None:
                marks.append("✓ understood already  »{}«".format(text))
                continue
            template = make_template(text, name, language)
            if template is None:
                marks.append("⚠ »{}« not found in »{}«".format(name, text))
            else:
                templates.append(template)
                marks.append("+ learned  »{}«".format(template.replace("{label}", "…")))

        data = ttm_context.read_custom(language)
        learn(data, target, patterns=templates)
        ttm_context.save_custom(language, data)
        self.controller.reload_vocabulary()

        label = next((c.get("label") or c["id"] for c in self.candidates if c["id"] == target), target)
        if miss is not None:
            miss["assigned"] = {"command": target, "label": label, "forms": [], "patterns": templates}
        self.results.clear()
        for mark in marks:
            self.results.addItem(mark)
        self.recordings = []
        self.name.clear()
        self.fill_misses()
        self.controller.status("learned {} sentence pattern(s) for {}".format(len(templates), label))
        self.update_buttons()

    def forget(self):
        miss = self.miss()
        if miss is None or not miss.get("assigned"):
            return
        assigned = miss.pop("assigned")
        language = self.controller.language
        data = ttm_context.read_custom(language)
        ttm_context.save_custom(language, unlearn(data, assigned["command"], assigned["forms"] + [miss["text"]],
                                                  patterns=assigned.get("patterns", [])))
        self.controller.reload_vocabulary()
        self.controller.status("forgot »{}« for {}".format(miss["text"], assigned["label"]))
        self.fill_misses()
        self.update_buttons()

    def closeEvent(self, event):
        if self.recording:
            self.record.setChecked(False)
        self.controller.trainer = None
        super().closeEvent(event)
