# SPDX-License-Identifier: LGPL-2.1-or-later
"""Vocabulary editor: everything that names a command, by command (DESIGN.md 8.9).

The language pack's phrases are shown read-only; the user's own phrases and what training
learned (heard forms, sentence patterns) can be added, deleted, or moved to another command.
Changes are saved right away to the user's vocabulary file.
"""

from talktome import context as ttm_context
from talktome.qt import QtCore, QtWidgets
from ttm_core import langpack
from ttm_core.training import add_phrase, entries, move_entry, remove_entry

COMMAND, KIND, TEXT = (QtCore.Qt.ItemDataRole.UserRole + i for i in range(3))
KIND_NAMES = {
    "pack": "language pack",
    "phrase": "my phrase",
    "heard": "heard (learned)",
    "pattern": "sentence pattern (learned)",
}


def shown(kind, text):
    return text.replace("{label}", "…") if kind == "pattern" else text


class VocabularyEditor(QtWidgets.QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Talk to me – Vocabulary")
        self.setModal(False)

        layout = QtWidgets.QVBoxLayout(self)
        note = QtWidgets.QLabel("What I understand for each command. Phrases of the language pack can't be "
                                "changed here; your own phrases and what I learned in training can be deleted "
                                "or moved to the right command.")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        layout.addWidget(note)

        self.filter = QtWidgets.QLineEdit()
        self.filter.setPlaceholderText("Filter commands and phrases")
        self.filter.textChanged.connect(self.fill)
        layout.addWidget(self.filter)
        self.only_mine = QtWidgets.QCheckBox("Only my phrases and learned forms")
        self.only_mine.toggled.connect(self.fill)
        layout.addWidget(self.only_mine)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Command / phrase", "Source"])
        self.tree.currentItemChanged.connect(self.update_buttons)
        layout.addWidget(self.tree)

        row = QtWidgets.QHBoxLayout()
        self.add_button = QtWidgets.QPushButton("Add phrase…")
        self.add_button.clicked.connect(self.add)
        self.delete_button = QtWidgets.QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete)
        self.move_button = QtWidgets.QPushButton("Move to…")
        self.move_button.setToolTip("A form learned for the wrong command goes to the right one")
        self.move_button.clicked.connect(self.move)
        close = QtWidgets.QPushButton("Close")
        close.clicked.connect(self.close)
        for button in (self.add_button, self.delete_button, self.move_button):
            row.addWidget(button)
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)

        self.resize(620, 640)
        self.fill()

    # --- data ----------------------------------------------------------------------------

    def language(self):
        return self.controller.language

    def custom(self):
        return ttm_context.read_custom(self.language())

    def save(self, data):
        ttm_context.save_custom(self.language(), data)
        self.controller.reload_vocabulary()
        self.fill()

    def labels(self):
        """Display names of the commands: FreeCAD's labels from the current context."""
        from talktome.training import PARAMETER_COMMANDS
        names = {command: (self.controller.vocab.get(command) or [label])[0]
                 for command, label in PARAMETER_COMMANDS.items()}
        for c in self.controller.last_candidates or []:
            names[c["id"]] = c.get("label") or c["id"]
        return names

    def command_name(self, command, names):
        name = names.get(command)
        return "{}   ({})".format(name, command) if name and name != command else command

    # --- tree ------------------------------------------------------------------------------

    def fill(self, *args):
        current = self.selected()
        names = self.labels()
        words = self.filter.text().lower().split()
        groups = {}
        for command, kind, text in entries(langpack.pack(self.language()).vocab, self.custom()):
            if self.only_mine.isChecked() and kind == "pack":
                continue
            title = self.command_name(command, names)
            if words and not all(w in (title + " " + text).lower() for w in words):
                continue
            groups.setdefault((command, title), []).append((kind, text))
        self.tree.clear()
        for (command, title), items in sorted(groups.items(), key=lambda g: g[0][1].lower()):
            parent = QtWidgets.QTreeWidgetItem([title, ""])
            parent.setData(0, COMMAND, command)
            self.tree.addTopLevelItem(parent)
            for kind, text in items:
                child = QtWidgets.QTreeWidgetItem([shown(kind, text), KIND_NAMES[kind]])
                for role, value in ((COMMAND, command), (KIND, kind), (TEXT, text)):
                    child.setData(0, role, value)
                if kind == "pack":
                    child.setForeground(0, self.palette().brush(self.palette().ColorGroup.Disabled,
                                                                self.palette().ColorRole.Text))
                parent.addChild(child)
                if current == (command, kind, text):
                    self.tree.setCurrentItem(child)
            parent.setExpanded(bool(words) or self.only_mine.isChecked() or len(groups) < 8)
        self.tree.resizeColumnToContents(0)
        self.update_buttons()

    def selected(self):
        """(command, kind, text) of the selected entry; kind and text None for a command row."""
        item = self.tree.currentItem()
        if item is None:
            return None
        return item.data(0, COMMAND), item.data(0, KIND), item.data(0, TEXT)

    def update_buttons(self, *args):
        selected = self.selected()
        editable = selected is not None and selected[1] not in (None, "pack")
        self.add_button.setEnabled(selected is not None)
        self.delete_button.setEnabled(editable)
        self.move_button.setEnabled(editable)

    # --- actions ---------------------------------------------------------------------------

    def add(self):
        command = self.selected()[0]
        text, ok = QtWidgets.QInputDialog.getText(
            self, "Add phrase", "Another way to say {}:".format(self.command_name(command, self.labels())))
        if ok and text.strip():
            self.save(add_phrase(self.custom(), command, text.strip()))

    def delete(self):
        command, kind, text = self.selected()
        self.save(remove_entry(self.custom(), command, kind, text))

    def move(self):
        command, kind, text = self.selected()
        names = self.labels()
        choices = sorted((self.command_name(c, names), c) for c in names if c != command)
        title, ok = QtWidgets.QInputDialog.getItem(
            self, "Move to", "»{}« means:".format(shown(kind, text)), [t for t, _ in choices], 0, False)
        if ok:
            target = dict(choices)[title]
            self.save(move_entry(self.custom(), kind, text, command, target))

    def closeEvent(self, event):
        self.controller.editor = None
        super().closeEvent(event)
