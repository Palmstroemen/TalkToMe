# SPDX-License-Identifier: LGPL-2.1-or-later
"""Collect the raw FreeCAD context and turn it into command candidates (DESIGN.md, section 6)."""

import json
import os

import FreeCAD as App
import FreeCADGui as Gui

from ttm_core.context import build_candidates

ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_vocabulary(language):
    """Vocabulary package of the addon, overridden by the user's own file."""
    vocab = {}
    paths = [os.path.join(ADDON_DIR, "vocab", "{}.json".format(language)),
             os.path.join(App.getUserAppDataDir(), "TalkToMe", "custom.{}.json".format(language))]
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            App.Console.PrintWarning("Talk to me: cannot read {}: {}\n".format(path, e))
            continue
        for cmd, phrases in data.items():
            if not cmd.startswith("_") and isinstance(phrases, list):
                vocab[cmd] = phrases + [p for p in vocab.get(cmd, []) if p not in phrases]
    return vocab


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


def collect(vocab, language="de"):
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

    return build_candidates(toolbars, labels, active, edit_prefix=edit_prefix,
                            dialog_open=bool(Gui.Control.activeDialog()),
                            workbenches=workbenches, current_workbench=wb.name(), vocab=vocab,
                            descriptions=descriptions, foreign_labels=english)
