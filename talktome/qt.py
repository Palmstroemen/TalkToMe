# SPDX-License-Identifier: LGPL-2.1-or-later
"""Qt modules for all supported FreeCAD versions.

FreeCAD's PySide module wraps PySide2 (Qt5) or PySide6 (Qt6), whichever FreeCAD is built with.
Before FreeCAD 0.20 it has no QtWidgets; its QtGui then contains the widget classes too.
"""

from PySide import QtCore, QtGui

try:
    from PySide import QtWidgets
except ImportError:
    QtWidgets = QtGui

# QAction moved from QtWidgets (Qt5) to QtGui (Qt6).
QAction = getattr(QtWidgets, "QAction", None) or QtGui.QAction
