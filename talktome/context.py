# SPDX-License-Identifier: LGPL-2.1-or-later
"""Collect the raw FreeCAD context and turn it into command candidates (DESIGN.md, section 6)."""

import json
import os

import FreeCAD as App
import FreeCADGui as Gui

from talktome.qt import QtCore, QtWidgets
from ttm_core import langpack
from ttm_core.context import from_snapshot
from ttm_core.training import vocabulary

def user_dir():
    """The user's Talk to me folder: own vocabulary, learned forms, changes to language packs."""
    return os.path.join(App.getUserAppDataDir(), "TalkToMe")


langpack.configure(user_dir())


def custom_path(language):
    """The user's own vocabulary file, also where training stores what it learned."""
    return os.path.join(user_dir(), "custom.{}.json".format(language))


def _read(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        App.Console.PrintWarning("Talk to me: cannot read {}: {}\n".format(path, e))
        return {}


def read_custom(language):
    return _read(custom_path(language))


def save_custom(language, data):
    path = custom_path(language)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_vocabulary(language):
    """(vocab, heard, patterns): phrases of the addon's package, overridden by the user's own
    file; the forms and sentence patterns learned in training ({command: [texts]})."""
    return vocabulary(langpack.pack(language).vocab, read_custom(language))


def _task_view(widget):
    while widget is not None:
        if widget.metaObject().className() == "Gui::TaskView::TaskView":
            return widget
        widget = widget.parentWidget()
    return None


def in_task_dialog(widget):
    """Whether widget is shown in the task view. FreeCAD fades a new task dialog in after
    some 300 ms, so isVisible() is still False right after the command that opened it."""
    view = _task_view(widget)
    return view is not None and widget.isVisibleTo(view)


def task_lists():
    """Lists of the open task dialog, e.g. the planes offered for a new sketch."""
    if not Gui.Control.activeDialog():
        return []
    mw = Gui.getMainWindow()
    return [w for w in mw.findChildren(QtWidgets.QListWidget) if in_task_dialog(w)]


def tool_running():
    """Whether an interactive sketcher tool runs (rectangle, line, ...): its task widget shows."""
    if not Gui.Control.activeDialog():
        return False
    mw = Gui.getMainWindow()
    return any(w.metaObject().className() == "SketcherGui::TaskSketcherTool" and in_task_dialog(w)
               for w in mw.findChildren(QtWidgets.QWidget))


def dialog_value_fields():
    """Number fields of an open PartDesign task dialog (Pad: length, taper; Fillet: radius; ...).
    Other task panels are left out: the sketcher's has a grid size, for instance."""
    if not Gui.Control.activeDialog():
        return []
    mw = Gui.getMainWindow()
    return [w for w in mw.findChildren(QtWidgets.QAbstractSpinBox)
            if w.metaObject().className().endswith("QuantitySpinBox") and w.isEnabled()
            and in_task_dialog(w) and _in_partdesign_task(w)]


def _in_partdesign_task(widget):
    while widget is not None:
        if widget.metaObject().className().startswith("PartDesignGui::"):
            return True
        widget = widget.parentWidget()
    return False


def values_expected():
    """Whether spoken numbers are values now: a sketcher tool runs or a PartDesign dialog asks."""
    return tool_running() or bool(dialog_value_fields())


def _choices():
    texts = []
    for widget in task_lists():
        for row in range(widget.count()):
            item = widget.item(row)
            if not item.isHidden() and item.flags() & QtCore.Qt.ItemFlag.ItemIsEnabled and item.text().strip():
                texts.append(item.text())
    return texts


def _text(value):
    if hasattr(value, "data"):
        value = value.data()
    return value.decode() if isinstance(value, bytes) else str(value or "")


def _command_name(action):
    """The command of a group button's entry: in the property "CommandName" (older FreeCAD),
    in the action's data or object name (FreeCAD 1.1). Only names of real commands count."""
    for value in (action.property("CommandName"), action.data(), action.objectName()):
        name = _text(value)
        if name and Gui.Command.get(name) is not None:
            return name
    return ""


def _describe(cmd_id, labels, english, active, descriptions):
    """Add the translated texts, the English name and the translated help text of a command.

    Returns its group children, if any.
    """
    cmd = Gui.Command.get(cmd_id)
    if cmd is None:
        return []
    texts, children = [], []
    try:
        actions = cmd.getAction()
    except Exception:
        actions = []
    for action in actions:
        name = _command_name(action)
        if name and name != cmd_id:
            children.append(name)
            labels.setdefault(name, []).append(action.text())
            descriptions.setdefault(name, action.statusTip())
        else:
            texts.append(action.text())
            descriptions.setdefault(cmd_id, action.statusTip())
    try:
        english.setdefault(cmd_id, []).append(cmd.getInfo().get("menuText", ""))
    except Exception:
        pass
    labels.setdefault(cmd_id, []).extend(texts)
    try:
        active[cmd_id] = bool(cmd.isActive())
    except Exception:
        active[cmd_id] = True
    return children


def collect(vocab, language="de", heard=None):
    """Candidates of the current context, as plain data for the speech service."""
    return from_snapshot(snapshot(language), vocab, heard, language)


def snapshot(language="de"):
    """The raw context: what FreeCAD shows now, before the vocabulary is added. Stored as a
    file, it is a context of the corpus (DESIGN.md 16.5, tools/record_context.py)."""
    wb = Gui.activeWorkbench()
    toolbars = {name: list(items) for name, items in wb.getToolbarItems().items()}
    labels, english, active, descriptions = {}, {}, {}, {}
    for name in list(toolbars):
        expanded = []
        for cmd_id in toolbars[name]:
            children = _describe(cmd_id, labels, english, active, descriptions)
            if children:                       # a group button: offer its entries, not the group
                for child in children:
                    _describe(child, labels, english, active, descriptions)
                expanded.extend(children)
            else:
                expanded.append(cmd_id)
        toolbars[name] = expanded

    edit_prefix = None
    doc = Gui.ActiveDocument
    in_edit = doc.getInEdit() if doc is not None else None
    if in_edit is not None:
        edit_prefix = in_edit.Object.TypeId.split("::")[0] + "_"

    workbenches = {name: [] for name in Gui.listWorkbenches()}
    for name, w in Gui.listWorkbenches().items():
        english["workbench:" + name] = [getattr(w, "MenuText", "")]
    try:                                       # translated workbench names
        for action in Gui.Command.get("Std_Workbench").getAction():
            if action.objectName() in workbenches:
                workbenches[action.objectName()].append(action.text())
    except Exception:
        pass

    if language.startswith("en"):              # English names are the user's own words then
        for cmd_id, texts in english.items():
            target = labels if not cmd_id.startswith("workbench:") else workbenches
            key = cmd_id if target is labels else cmd_id.split(":", 1)[1]
            target.setdefault(key, []).extend(texts)
        english = {}

    dialog_open = bool(Gui.Control.activeDialog())
    return {"toolbar_items": toolbars, "labels": labels, "active": active, "edit_prefix": edit_prefix,
            "dialog_open": dialog_open, "choices": _choices() if dialog_open else None,
            "workbenches": workbenches, "current_workbench": wb.name(),
            "descriptions": descriptions, "foreign_labels": english}
