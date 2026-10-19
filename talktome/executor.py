# SPDX-License-Identifier: LGPL-2.1-or-later
"""Execute a decided command in FreeCAD (DESIGN.md, section 7).

Returns (ok, reason). Before running, the command is checked again: the context may have
changed since the utterance started.
"""

import FreeCADGui as Gui
from talktome.context import in_task_dialog, task_lists
from talktome.qt import QtCore, QtGui, QtWidgets, translate
from ttm_core.context import CHOOSE

# Task dialogs whose list asks for exactly one thing: choosing confirms the dialog.
AUTO_CONFIRM = {"PartDesignGui__TaskFeaturePick"}       # e.g. the plane for a new sketch


def _task_button(which):
    """The OK or Cancel button of the open task dialog, if visible."""
    std = QtWidgets.QDialogButtonBox.StandardButton
    wanted = std.Ok if which == "ok" else std.Cancel
    for box in Gui.getMainWindow().findChildren(QtWidgets.QDialogButtonBox):
        if box.isVisible() or in_task_dialog(box):
            button = box.button(wanted)
            if button is not None and button.isEnabled():
                return button
    return None


def _press_escape():
    """Escape ends the running tool, e.g. the rectangle tool in the sketcher."""
    target = QtWidgets.QApplication.focusWidget() or Gui.getMainWindow()
    for kind in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
        event = QtGui.QKeyEvent(kind, QtCore.Qt.Key.Key_Escape, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(target, event)


def _confirms(widget):
    while widget is not None:
        if widget.objectName() in AUTO_CONFIRM:
            return True
        widget = widget.parentWidget()
    return False


def choose(text):
    """Select the entry text in a list of the task dialog; confirm dialogs in AUTO_CONFIRM."""
    for widget in task_lists():
        for row in range(widget.count()):
            item = widget.item(row)
            if item.text() == text and not item.isHidden():
                widget.setCurrentItem(item)
                if _confirms(widget):
                    button = _task_button("ok")
                    if button is None:
                        return False, translate("TalkToMe", "selected, but OK is not available")
                    button.click()
                return True, ""
    return False, translate("TalkToMe", "choice no longer offered")


def datum_dialog():
    """The sketcher's open dimension dialog ("Länge eingeben"), if any. Keep this reference while
    using its name field (datum_name_field): PySide drops the field's wrapper with the dialog's."""
    dialog = QtWidgets.QApplication.activeModalWidget()
    if dialog is None or dialog.objectName() != "SketcherGui__InsertDatum":
        return None
    return dialog


def datum_name_field(dialog):
    return dialog.findChild(QtWidgets.QLineEdit, "name")


def selected_constraint():
    """(sketch, index) of the one dimension selected in the sketch being edited, else None."""
    selection = Gui.Selection.getSelectionEx()
    if len(selection) != 1 or selection[0].Object.TypeId != "Sketcher::SketchObject":
        return None
    names = selection[0].SubElementNames
    if len(names) != 1 or not names[0].startswith("Constraint"):
        return None
    return selection[0].Object, int(names[0][len("Constraint"):]) - 1


def constraint_name(label):
    """Dimension names are used in expressions (Sketch.Constraints.Breite): no spaces."""
    return "_".join(label.split())


def rename_constraint(sketch, index, label):
    doc = sketch.Document
    doc.openTransaction("Rename constraint")
    try:
        sketch.renameConstraint(index, constraint_name(label))
    finally:
        doc.commitTransaction()
    return True, ""


def rename(obj, label):
    """Set an object's label, undoable. Returns (ok, reason); FreeCAD may adapt duplicate labels."""
    doc = obj.Document
    doc.openTransaction("Rename")
    try:
        obj.Label = label
    finally:
        doc.commitTransaction()
    return True, "" if obj.Label == label else translate("TalkToMe", "named {}").format(obj.Label)


def created_objects(doc, before):
    """Objects added to doc since before (a set of names), without their own children:
    a new body brings its origin, but the body is what was created."""
    new = [o for o in doc.Objects if o.Name not in before]
    return [o for o in new if not any(parent in new for parent in o.InList)]


def execute(command):
    if command.startswith("workbench:"):
        name = command.split(":", 1)[1]
        if name not in Gui.listWorkbenches():
            return False, translate("TalkToMe", "unknown workbench")
        Gui.activateWorkbench(name)
        return True, ""

    if command.startswith(CHOOSE):
        return choose(command[len(CHOOSE):])

    if command in ("ui:ok", "ui:cancel"):
        button = _task_button("ok" if command == "ui:ok" else "cancel")
        if button is not None:
            button.click()
            return True, ""
        if command == "ui:cancel":
            _press_escape()
            return True, ""
        return False, translate("TalkToMe", "no dialog to confirm")

    cmd = Gui.Command.get(command)
    if cmd is None:
        return False, translate("TalkToMe", "unknown command")
    if not cmd.isActive():
        return False, translate("TalkToMe", "not available right now")
    Gui.runCommand(command, 0)
    return True, ""
