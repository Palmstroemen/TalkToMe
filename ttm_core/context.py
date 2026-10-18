"""Command candidates of the current FreeCAD context (DESIGN.md, section 6).

The FreeCAD addon collects raw data (toolbars, button texts, edit mode, ...) and this module
turns it into a list of candidates, each with a priority level:

    dialog     an open task dialog: OK / cancel
    edit       commands belonging to the object being edited (e.g. Sketcher_* in a sketch)
    workbench  the other commands of the active workbench
    global     Std_* commands, switching workbenches, cancel
"""

from ttm_core.vocabulary import merge_phrases

LEVELS = ("dialog", "edit", "workbench", "global")
SEPARATOR = "Separator"


def build_candidates(toolbar_items, labels, active, edit_prefix=None, dialog_open=False,
                     workbenches=None, current_workbench=None, vocab=None):
    """
    toolbar_items      {toolbar name: [command ids]} of the active workbench
    labels             {command id: [button texts]}, translated first, English after
    active             {command id: bool}; missing ids count as active
    edit_prefix        command prefix of the object in edit mode, e.g. "Sketcher_"
    dialog_open        whether a task dialog is open
    workbenches        {workbench name: [display names]} for switching workbenches
    current_workbench  name of the active workbench (no switch offered to it)
    vocab              {command id: [phrases]} from vocabulary files; they come first
    """
    vocab = vocab or {}
    candidates, seen = [], set()

    def add(id_, level, phrases, is_active=True):
        if phrases and id_ not in seen:
            seen.add(id_)
            candidates.append({"id": id_, "level": level, "phrases": phrases, "active": is_active})

    if dialog_open:
        add("ui:ok", "dialog", merge_phrases(vocab.get("ui:ok")))
        add("ui:cancel", "dialog", merge_phrases(vocab.get("ui:cancel")))

    for commands in toolbar_items.values():
        for cmd in commands:
            if cmd == SEPARATOR or cmd in seen:
                continue
            if cmd.startswith("Std_"):
                level = "global"
            elif edit_prefix and cmd.startswith(edit_prefix):
                level = "edit"
            else:
                level = "workbench"
            add(cmd, level, merge_phrases(vocab.get(cmd), labels.get(cmd)), active.get(cmd, True))

    add("ui:cancel", "global", merge_phrases(vocab.get("ui:cancel")))
    for wb, names in (workbenches or {}).items():
        if wb != current_workbench:
            wb_id = "workbench:" + wb
            add(wb_id, "global", merge_phrases(vocab.get(wb_id), names))
    return candidates
