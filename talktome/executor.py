# SPDX-License-Identifier: LGPL-2.1-or-later
"""Execute a decided command in FreeCAD (DESIGN.md, section 7).

Returns (ok, reason). Before running, the command is checked again: the context may have
changed since the utterance started.
"""

import FreeCADGui as Gui
from talktome.qt import QtCore, QtGui, QtWidgets


def _task_button(which):
    """The OK or Cancel button of the open task dialog, if visible."""
    std = QtWidgets.QDialogButtonBox.StandardButton
    wanted = std.Ok if which == "ok" else std.Cancel
    for box in Gui.getMainWindow().findChildren(QtWidgets.QDialogButtonBox):
        if box.isVisible():
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


def rename(obj, label):
    """Set an object's label, undoable. Returns (ok, reason); FreeCAD may adapt duplicate labels."""
    doc = obj.Document
    doc.openTransaction("Rename")
    try:
        obj.Label = label
    finally:
        doc.commitTransaction()
    return True, "" if obj.Label == label else "named {}".format(obj.Label)


def created_objects(doc, before):
    """Objects added to doc since before (a set of names), without their own children:
    a new body brings its origin, but the body is what was created."""
    new = [o for o in doc.Objects if o.Name not in before]
    return [o for o in new if not any(parent in new for parent in o.InList)]


def execute(command):
    if command.startswith("workbench:"):
        name = command.split(":", 1)[1]
        if name not in Gui.listWorkbenches():
            return False, "unknown workbench"
        Gui.activateWorkbench(name)
        return True, ""

    if command in ("ui:ok", "ui:cancel"):
        button = _task_button("ok" if command == "ui:ok" else "cancel")
        if button is not None:
            button.click()
            return True, ""
        if command == "ui:cancel":
            _press_escape()
            return True, ""
        return False, "no dialog to confirm"

    cmd = Gui.Command.get(command)
    if cmd is None:
        return False, "unknown command"
    if not cmd.isActive():
        return False, "not available right now"
    Gui.runCommand(command, 0)
    return True, ""
