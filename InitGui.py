# SPDX-License-Identifier: LGPL-2.1-or-later
"""Talk to me – voice control for FreeCAD."""

def _talktome_init():
    from PySide import QtCore

    # A global toolbar shown in every workbench. FreeCAD creates it from this parameter
    # group; the microphone action is added to it at runtime.
    toolbar = FreeCAD.ParamGet("User parameter:BaseApp/Workbench/Global/Toolbar/TalkToMe")
    toolbar.SetString("Name", "Talk to me")
    toolbar.SetBool("Active", True)

    timer = QtCore.QTimer()
    tries = [0]

    def try_setup():
        import talktome.gui
        tries[0] += 1
        if talktome.gui.setup() or tries[0] > 120:
            timer.stop()

    timer.timeout.connect(try_setup)
    timer.start(500)
    return timer      # keep a reference, or the timer is garbage collected


_talktome_timer = _talktome_init()
