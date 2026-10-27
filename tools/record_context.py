# SPDX-License-Identifier: LGPL-2.1-or-later
"""Record the current FreeCAD context for the corpus (DESIGN.md 16.5).

Run it in FreeCAD as a macro (Macro → Macros… → this file → Execute), in the state the corpus
sentences are spoken in: a workbench, an object in edit, a dialog open, a tool running. It asks
for a name and writes lang/<language>/contexts/<name>.json, the raw context without the
vocabulary: the corpus adds the vocabulary of the pack it tests.

From a script: record_context.record("partdesign", note="new document with a body").
"""

import json
import os
import sys

import FreeCAD as App

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def record(name, language=None, note="", directory=None):
    """Write the context; returns the file's path."""
    from talktome import context
    language = language or context.spoken_language()
    data = {
        "_about": "A raw FreeCAD context for the corpus, recorded with tools/record_context.py.",
        "freecad": ".".join(App.Version()[:3]),
        "language": language,
        "note": note,
        "tool_running": bool(context.values_expected()),
        "context": context.snapshot(language),
    }
    directory = directory or os.path.join(ROOT, "lang", language, "contexts")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
    return path


def _ask():
    from talktome.qt import QtWidgets
    import FreeCADGui as Gui
    name, ok = QtWidgets.QInputDialog.getText(Gui.getMainWindow(), "Record context",
                                              "Name of the context (e.g. partdesign, sketch_plane):")
    if ok and name.strip():
        note, _ = QtWidgets.QInputDialog.getText(Gui.getMainWindow(), "Record context",
                                                 "What is open? (optional)")
        path = record(name.strip(), note=note.strip())
        QtWidgets.QMessageBox.information(Gui.getMainWindow(), "Record context", "Written:\n" + path)


if __name__ == "__main__" and App.GuiUp:
    _ask()
