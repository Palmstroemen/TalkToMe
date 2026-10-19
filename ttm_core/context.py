"""Command candidates of the current FreeCAD context (DESIGN.md, section 6).

The FreeCAD addon collects raw data (toolbars, button texts, edit mode, ...) and this module
turns it into a list of candidates, each with a priority level:

    dialog     an open task dialog: its choices (e.g. the planes for a new sketch), OK / cancel
    edit       commands belonging to the object being edited (e.g. Sketcher_* in a sketch)
    workbench  the other commands of the active workbench
    global     Std_* commands, switching workbenches, cancel, microphone off
"""

from ttm_core.vocabulary import clean_label, merge_phrases

LEVELS = ("dialog", "edit", "workbench", "global")
SEPARATOR = "Separator"
# The workbench selector carries the names of all workbenches; switching is offered as
# workbench:<name> instead.
EXCLUDED = {"Std_Workbench"}
CHOOSE = "ui:choose:"


def build_candidates(toolbar_items, labels, active, edit_prefix=None, dialog_open=False,
                     workbenches=None, current_workbench=None, vocab=None, descriptions=None,
                     foreign_labels=None, choices=None, heard=None):
    """
    toolbar_items      {toolbar name: [command ids]} of the active workbench
    labels             {command id: [button texts]} in the user's language
    active             {command id: bool}; missing ids count as active
    edit_prefix        command prefix of the object in edit mode, e.g. "Sketcher_"
    dialog_open        whether a task dialog is open
    workbenches        {workbench name: [display names]} for switching workbenches
    current_workbench  name of the active workbench (no switch offered to it)
    vocab              {command id: [phrases]} from vocabulary files; they come first
    descriptions       {command id: help text} in the user's language (status tips)
    foreign_labels     {command id: [texts]} in another language, usually FreeCAD's English
                       names; compared by spelling only, the sound rules are the user's language's
    choices            entries of the lists in the open task dialog; command "ui:choose:<text>"
    heard              {command id: [texts]} learned in training: how the recognizer hears the
                       user; compared like phrases, but no hints for the recognizer
    """
    heard = heard or {}
    vocab = vocab or {}
    descriptions = descriptions or {}
    foreign_labels = foreign_labels or {}
    candidates, seen = [], set()

    def add(id_, level, phrases, is_active=True, shown=None):
        """shown: FreeCAD's own text for the command, to display it (e.g. in the question menu)."""
        own = {p.lower() for p in phrases}
        foreign = [p for p in merge_phrases(foreign_labels.get(id_)) if p.lower() not in own]
        if (phrases or foreign) and id_ not in seen:
            seen.add(id_)
            label = clean_label(shown) if shown else (phrases or foreign)[0]
            candidates.append({"id": id_, "level": level, "label": label, "phrases": phrases, "foreign": foreign,
                               "heard": list(heard.get(id_, [])), "active": is_active,
                               "description": descriptions.get(id_, "")})

    if dialog_open:
        for text in choices or []:
            add(CHOOSE + text, "dialog", merge_phrases(vocab.get(CHOOSE + text), [text]), shown=text)
        add("ui:ok", "dialog", merge_phrases(vocab.get("ui:ok")))
        add("ui:cancel", "dialog", merge_phrases(vocab.get("ui:cancel")))

    for commands in toolbar_items.values():
        for cmd in commands:
            if cmd == SEPARATOR or cmd in EXCLUDED or cmd in seen:
                continue
            if cmd.startswith("Std_"):
                level = "global"
            elif edit_prefix and cmd.startswith(edit_prefix):
                level = "edit"
            else:
                level = "workbench"
            add(cmd, level, merge_phrases(vocab.get(cmd), labels.get(cmd)), active.get(cmd, True),
                shown=(labels.get(cmd) or [None])[0])

    add("ui:cancel", "global", merge_phrases(vocab.get("ui:cancel")))
    add("ui:mic_off", "global", merge_phrases(vocab.get("ui:mic_off")))
    for wb, names in (workbenches or {}).items():
        if wb != current_workbench:
            wb_id = "workbench:" + wb
            add(wb_id, "global", merge_phrases(vocab.get(wb_id), names), shown=(list(names) or [None])[0])
    return candidates
