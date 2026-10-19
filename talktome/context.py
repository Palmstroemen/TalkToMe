# SPDX-License-Identifier: LGPL-2.1-or-later
"""Collect the raw FreeCAD context and turn it into command candidates (DESIGN.md, section 6)."""

import json
import os

import FreeCAD as App
import FreeCADGui as Gui

from talktome.qt import QtCore, QtWidgets
from ttm_core.context import build_candidates
from ttm_core.training import HEARD

ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def custom_path(language):
    """The user's own vocabulary file, also where training stores what it learned."""
    return os.path.join(App.getUserAppDataDir(), "TalkToMe", "custom.{}.json".format(language))


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
    """(vocab, heard): phrases of the addon's package, overridden by the user's own file, and
    the forms learned in training ({command: [texts]})."""
    vocab = {}
    package = _read(os.path.join(ADDON_DIR, "vocab", "{}.json".format(language)))
    custom = read_custom(language)
    for data in (package, custom):
        for cmd, phrases in data.items():
            if not cmd.startswith("_") and isinstance(phrases, list):
                vocab[cmd] = phrases + [p for p in vocab.get(cmd, []) if p not in phrases]
    heard = custom.get(HEARD, {})
    return vocab, heard if isinstance(heard, dict) else {}


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


def _choices():
    texts = []
    for widget in task_lists():
        for row in range(widget.count()):
            item = widget.item(row)
            if not item.isHidden() and item.flags() & QtCore.Qt.ItemFlag.ItemIsEnabled:
                texts.append(item.text())
    return texts


def _command_name(action):
    """Sub-entries of group buttons carry their command in the property "CommandName"."""
    value = action.property("CommandName")
    if not value:
        return ""
    if hasattr(value, "data"):
        value = value.data()
    return value.decode() if isinstance(value, bytes) else str(value)


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
    return build_candidates(toolbars, labels, active, edit_prefix=edit_prefix,
                            dialog_open=dialog_open, choices=_choices() if dialog_open else None,
                            workbenches=workbenches, current_workbench=wb.name(), vocab=vocab,
                            descriptions=descriptions, foreign_labels=english, heard=heard)
