# SPDX-License-Identifier: LGPL-2.1-or-later
"""Execute a decided command in FreeCAD (DESIGN.md, section 7).

Returns (ok, reason). Before running, the command is checked again: the context may have
changed since the utterance started.
"""

import FreeCADGui as Gui
from talktome.context import dialog_value_fields, in_task_dialog, task_lists
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
    """Escape ends the running tool, e.g. the rectangle tool in the sketcher. With the value
    fields of a tool showing, the 3D view gets it twice: the first closes the fields, the second
    ends the tool, as with the keyboard."""
    from talktome.context import tool_running
    view = None
    if tool_running():
        try:
            view = Gui.ActiveDocument.ActiveView.graphicsView()
        except Exception:
            view = None
    target = view or QtWidgets.QApplication.focusWidget() or Gui.getMainWindow()
    for _ in range(2 if view is not None else 1):
        for kind in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
            event = QtGui.QKeyEvent(kind, QtCore.Qt.Key.Key_Escape, QtCore.Qt.KeyboardModifier.NoModifier)
            QtWidgets.QApplication.sendEvent(target, event)
        QtWidgets.QApplication.processEvents()
        if view is not None and not tool_running():
            break


def value_fields():
    """The fields a running tool shows in the 3D view for its values (On-View-Parameters), the one
    with the focus first: it is the value the tool asks for next."""
    fields = [w for w in Gui.getMainWindow().findChildren(QtWidgets.QAbstractSpinBox)
              if w.metaObject().className() == "Gui::QuantitySpinBox" and w.isVisible() and _in_view(w)]
    fields.sort(key=lambda w: not w.hasFocus())
    return fields


def _in_view(widget):
    while widget is not None:
        if widget.metaObject().className() == "Gui::View3DInventor":
            return True
        widget = widget.parentWidget()
    return False


def quantity(value, unit="mm"):
    text = ("{:.6f}".format(value)).rstrip("0").rstrip(".")
    return text.replace(".", QtCore.QLocale().decimalPoint()) + ("°" if unit == "°" else " " + unit)


def _enter(field, value):
    field.setFocus()
    line = field.findChild(QtWidgets.QLineEdit)
    line.selectAll()
    line.setText(quantity(value, field.property("unit") or "mm"))
    for kind in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
        QtWidgets.QApplication.sendEvent(field, QtGui.QKeyEvent(kind, QtCore.Qt.Key.Key_Return,
                                                               QtCore.Qt.KeyboardModifier.NoModifier))
    QtWidgets.QApplication.processEvents()


# Tools whose length field is a diameter (FreeCAD 1.1.4): "Radius 20" means 40 there.
DIAMETER_TOOLS = {"Sketcher_CreateCircle"}


def _slots(fields, values):
    """Values for fields in their order: named ones at their position, the others in the order spoken."""
    slots = [None] * len(fields)
    for position, value in values:
        if position is not None and position < len(slots) and slots[position] is None:
            slots[position] = value
    rest = iter(v for p, v in values if p is None or p >= len(slots))
    return [value if value is not None else next(rest, None) for value in slots]


def fill_values(values, tool=None):
    """Spoken values into the fields of a sketcher tool or a PartDesign dialog:
    [(position or None, value, kind)] (ttm_core.values).

    Lengths go to the fields in mm, angles to those in °; named values to their position in the
    tool's order (width 0, height 1), the others in the order spoken. A radius is doubled for
    tools that ask for a diameter (tool: the command that started the tool, if known). Each value
    is confirmed with Enter, as typed. Returns the number of values entered.
    """
    fields = value_fields()
    enter = _enter                             # sketcher fields in the view: Enter moves the tool on
    if not fields:
        fields = dialog_value_fields()
        enter = _set                           # a dialog: set the value, OK stays with the user
    lengths = [f for f in fields if f.property("unit") != "°"]
    angles = [f for f in fields if f.property("unit") == "°"]
    factor = 2 if tool in DIAMETER_TOOLS else 1
    length_values = [(p, v * factor if k == "radius" else v) for p, v, k in values if k != "angle"]
    angle_values = [(p, v) for p, v, k in values if k == "angle"]
    entered = 0
    for group, group_values in ((lengths, length_values), (angles, angle_values)):
        for field, value in zip(group, _slots(group, group_values)):
            if value is not None:
                enter(field, value)
                entered += 1
    return entered


def _set(field, value):
    """A value field of a task dialog: set its value directly (no text, no locale, no Enter)."""
    field.setProperty("rawValue", float(value))
    QtWidgets.QApplication.processEvents()


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
