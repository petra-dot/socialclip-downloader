"""A small top-right button that shows update state and emits clicks."""

from PyQt5 import QtWidgets, QtCore, QtGui


class UpdateButton(QtWidgets.QToolButton):
    STATES = ("hidden", "available", "downloading", "ready", "error")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoRaise(True)
        self.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.setAccessibleName("Update status")
        self._state = "hidden"
        self.set_state("hidden")

    def state(self) -> str:
        return self._state

    def set_state(self, state: str, version: str = "", detail: str = ""):
        if state not in self.STATES:
            state = "hidden"
        self._state = state
        self.setVisible(state != "hidden")
        if state == "hidden":
            self.setToolTip("")
            self.setText("")
            return
        if state == "available":
            self.setText("Update")
            self.setToolTip("Update %s available" % (version or ""))
        elif state == "downloading":
            self.setText(detail or "Downloading")
            self.setToolTip("Downloading the update. Click to cancel.")
        elif state == "ready":
            self.setText("Restart")
            self.setToolTip("Update %s ready to install" % (version or ""))
        elif state == "error":
            self.setText("Retry")
            self.setToolTip(detail or "Update check failed")
