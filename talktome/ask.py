# SPDX-License-Identifier: LGPL-2.1-or-later
"""Question menu next to the mouse pointer when an utterance was not clear (DESIGN.md 8.8).

It doesn't take focus or grab the mouse, so a sketcher tool in progress goes on; it disappears
after a few seconds. Entries are numbered and can be picked by voice ("die zweite").
"""

from talktome.qt import QtCore, QtGui, QtWidgets, translate

SHOW_MS = 8000


class AskPopup(QtWidgets.QFrame):
    def __init__(self, parent, text, entries, on_pick, on_train):
        """entries: [(label, active)]; on_pick(index) and on_train() are called on a choice."""
        flags = (QtCore.Qt.WindowType.Tool | QtCore.Qt.WindowType.FramelessWindowHint
                 | QtCore.Qt.WindowType.WindowStaysOnTopHint | QtCore.Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(parent, flags)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFrameShape(QtWidgets.QFrame.Shape.Box)
        self.on_pick, self.on_train = on_pick, on_train

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)
        heard = QtWidgets.QLabel(translate("TalkToMe", "»{}« – did you mean:").format(text))
        heard.setStyleSheet("color: gray;")
        layout.addWidget(heard)
        for i, (label, active) in enumerate(entries):
            button = QtWidgets.QPushButton("{}   {}{}".format(i + 1, label, "" if active else translate("TalkToMe", "   (not available now)")))
            button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
            button.setStyleSheet("text-align: left; padding: 3px 8px;")
            button.setEnabled(active)
            button.clicked.connect(lambda checked=False, i=i: self.pick(i))
            layout.addWidget(button)
        train = QtWidgets.QPushButton(translate("TalkToMe", "None of these – train…"))
        train.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        train.setStyleSheet("text-align: left; padding: 3px 8px; color: gray;")
        train.clicked.connect(self.train)
        layout.addWidget(train)

        self.adjustSize()
        pos = QtGui.QCursor.pos() + QtCore.QPoint(16, 16)
        screen = QtWidgets.QApplication.screenAt(pos)
        if screen is not None:                 # keep it on the screen
            area = screen.availableGeometry()
            pos.setX(min(pos.x(), area.right() - self.width()))
            pos.setY(min(pos.y(), area.bottom() - self.height()))
        self.move(pos)
        QtCore.QTimer.singleShot(SHOW_MS, self.close)

    def pick(self, index):
        self.close()
        self.on_pick(index)

    def train(self):
        self.close()
        self.on_train()
