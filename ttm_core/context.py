"""Command candidates of the current FreeCAD context (DESIGN.md, section 6).

The FreeCAD addon collects raw data (toolbars, button texts, edit mode, ...) and this module
turns it into a list of candidates, each with a priority level:

    dialog     an open task dialog: its choices (e.g. the planes for a new sketch), OK / cancel
    edit       commands belonging to the object being edited (e.g. Sketcher_* in a sketch)
    workbench  the other commands of the active workbench
    global     Std_* commands, switching workbenches, cancel, microphone off
"""

import re
from collections import Counter

from ttm_core.languages import STOP_WORDS
from ttm_core.text import normalize
from ttm_core.vocabulary import clean_label, merge_phrases

LEVELS = ("dialog", "edit", "workbench", "global")
SEPARATOR = "Separator"
# The workbench selector carries the names of all workbenches; switching is offered as
# workbench:<name> instead.
EXCLUDED = {"Std_Workbench"}
CHOOSE = "ui:choose:"


def build_candidates(toolbar_items, labels, active, edit_prefix=None, dialog_open=False,
                     workbenches=None, current_workbench=None, vocab=None, descriptions=None,
                     foreign_labels=None, choices=None, heard=None, language=None):
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
    language           for the stop words of the short forms (short_forms)
    """
    heard = heard or {}
    vocab = vocab or {}
    toolbar_commands = [cmd for commands in toolbar_items.values() for cmd in commands if cmd != SEPARATOR]
    short = short_forms([(cmd, (labels.get(cmd) or [""])[0]) for cmd in toolbar_commands], language)
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
                               "short": [short[id_]] if id_ in short else [],
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
    add("ui:train", "global", merge_phrases(vocab.get("ui:train")))
    for wb, names in (workbenches or {}).items():
        if wb != current_workbench:
            wb_id = "workbench:" + wb
            add(wb_id, "global", merge_phrases(vocab.get(wb_id), names), shown=(list(names) or [None])[0])
    return candidates


# Label endings shared by this many labels of a context say nothing about the command:
# "Parallel festlegen", "Kreis um Mittelpunkt", "Parallel Constraint".
MIN_SHARED = 3
NUMBER = re.compile(r"^\d+([.,]\d+)?$")


def short_forms(labels, language=None):
    """{command: short form} for [(command, label)] in toolbar order: the label without an ending
    of one or two words that at least MIN_SHARED labels share ("Parallel festlegen" → "Parallel").
    Where two labels give the same short form, the first one gets it (a group's default entry:
    "Kreis um Mittelpunkt" before "Kreis durch 3 Punkte"); none equals a whole label."""
    stop = STOP_WORDS.get(language, frozenset())
    items = []
    for command, label in labels:
        words = [w for w in clean_label(label or "").split() if normalize(w) and not NUMBER.match(normalize(w))]
        items.append((command, words, tuple(normalize(w) for w in words)))
    endings = Counter(keys[-k:] for _, _, keys in items for k in (1, 2) if len(keys) > k)
    taken = {" ".join(keys) for _, _, keys in items}
    result = {}
    for command, words, keys in items:
        for k in (2, 1):
            if len(keys) > k and endings[keys[-k:]] >= MIN_SHARED:
                rest = keys[:-k]
                key = " ".join(rest)
                if key not in taken and any(w not in stop for w in rest):
                    result[command] = " ".join(words[:-k])
                    taken.add(key)
                break
    return result


SNAPSHOT_KEYS = ("toolbar_items", "labels", "active", "edit_prefix", "dialog_open", "choices",
                 "workbenches", "current_workbench", "descriptions", "foreign_labels")


def from_snapshot(snapshot, vocab=None, heard=None, language=None):
    """Candidates of a raw context (talktome.context.snapshot), with the current vocabulary."""
    raw = {k: snapshot.get(k) for k in SNAPSHOT_KEYS if snapshot.get(k) is not None}
    return build_candidates(raw.pop("toolbar_items", {}), raw.pop("labels", {}), raw.pop("active", {}),
                            vocab=vocab, heard=heard, language=language, **raw)
