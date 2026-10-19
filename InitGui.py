# SPDX-License-Identifier: LGPL-2.1-or-later
"""Talk to me – voice control for FreeCAD."""

def _talktome_init():
    from PySide import QtCore

    import talktome.command

    # A global toolbar shown in every workbench, created by FreeCAD from this parameter group.
    # The value names the module that registers the command.
    toolbar = FreeCAD.ParamGet("User parameter:BaseApp/Workbench/Global/Toolbar/TalkToMe")
    toolbar.SetString("Name", "Talk to me")
    toolbar.SetBool("Active", True)
    toolbar.SetString(talktome.command.NAME, "talktome.command")
    toolbar.SetString(talktome.command.TRAINING, "talktome.command")

    # FreeCAD runs this file with exec() inside a function: module-level names vanish
    # afterwards. The main window as parent keeps the timer alive.
    timer = QtCore.QTimer(FreeCADGui.getMainWindow())
    tries = [0]

    def try_setup():
        import talktome.gui
        tries[0] += 1
        if talktome.gui.setup() or tries[0] > 120:
            timer.stop()

    timer.timeout.connect(try_setup)
    timer.start(500)


_talktome_init()
