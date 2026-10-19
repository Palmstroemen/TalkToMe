# SPDX-License-Identifier: LGPL-2.1-or-later
"""The microphone button as a FreeCAD command.

As a command it can be put into any toolbar and gets a keyboard shortcut in
Tools → Customize → Keyboard (useful for keyboards without a microphone key, or a foot pedal).
The controller in talktome.gui drives the command's QAction: icon, tooltip and check state.
"""

import os

import FreeCADGui as Gui

from talktome.qt import QT_TRANSLATE_NOOP

NAME = "TalkToMe_Microphone"
TRAINING = "TalkToMe_Training"
ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Resources", "icons")
ICON = os.path.join(ICON_DIR, "mic_off.svg")
TRAIN_ICON = os.path.join(ICON_DIR, "train.svg")


class MicrophoneCommand:
    def GetResources(self):
        return {
            "Pixmap": ICON,
            "MenuText": QT_TRANSLATE_NOOP("TalkToMe_Microphone", "Talk to me"),
            "ToolTip": QT_TRANSLATE_NOOP("TalkToMe_Microphone", "Talk to me: switch the microphone on or off"),
            "Checkable": False,      # the key makes the command checkable, the value is its start state
        }

    def IsActive(self):
        return True

    def Activated(self, checked=None):
        pass                  # the controller listens to the action's toggled signal


def action():
    """The command's QAction, once FreeCAD has created it (when adding it to a toolbar)."""
    cmd = Gui.Command.get(NAME)
    actions = cmd.getAction() if cmd is not None else []
    return actions[0] if actions else None


class TrainingCommand:
    def GetResources(self):
        return {
            "Pixmap": TRAIN_ICON,
            "MenuText": QT_TRANSLATE_NOOP("TalkToMe_Training", "Talk to me: Training"),
            "ToolTip": QT_TRANSLATE_NOOP("TalkToMe_Training", "Teach Talk to me how the speech recognition hears you"),
        }

    def IsActive(self):
        return True

    def Activated(self):
        import talktome.gui
        talktome.gui.open_training()


if NAME not in Gui.listCommands():
    Gui.addCommand(NAME, MicrophoneCommand())
if TRAINING not in Gui.listCommands():
    Gui.addCommand(TRAINING, TrainingCommand())
