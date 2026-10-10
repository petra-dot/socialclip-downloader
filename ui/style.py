"""Shared UI styling: scalable headings and light/dark themes.

Headings use the application font rather than a fixed pixel size, so they
follow the user's system text scaling instead of ignoring it.
"""

from PyQt5 import QtWidgets, QtGui

THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEMES = (THEME_SYSTEM, THEME_LIGHT, THEME_DARK)

# "system" uses Qt's default palette, which on Windows is the light one. Call
# it "Default" rather than promising it follows the OS theme.
THEME_LABELS = {
    THEME_SYSTEM: "Default",
    THEME_LIGHT: "Light",
    THEME_DARK: "Dark",
}


def make_heading(label):
    """Style a QLabel as a section heading, scaled from the app font."""
    font = label.font()
    font.setBold(True)
    base = QtWidgets.QApplication.font().pointSizeF()
    if base and base > 0:
        font.setPointSizeF(base + 1.0)
    label.setFont(font)
    return label


def _dark_palette():
    p = QtGui.QPalette()
    window = QtGui.QColor(37, 38, 40)
    base = QtGui.QColor(28, 29, 31)
    text = QtGui.QColor(232, 234, 237)
    disabled = QtGui.QColor(130, 135, 143)
    p.setColor(QtGui.QPalette.Window, window)
    p.setColor(QtGui.QPalette.WindowText, text)
    p.setColor(QtGui.QPalette.Base, base)
    p.setColor(QtGui.QPalette.AlternateBase, window)
    p.setColor(QtGui.QPalette.Text, text)
    p.setColor(QtGui.QPalette.Button, window)
    p.setColor(QtGui.QPalette.ButtonText, text)
    p.setColor(QtGui.QPalette.ToolTipBase, base)
    p.setColor(QtGui.QPalette.ToolTipText, text)
    p.setColor(QtGui.QPalette.Highlight, QtGui.QColor(45, 137, 239))
    p.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(255, 255, 255))
    for role in (QtGui.QPalette.Text, QtGui.QPalette.ButtonText,
                 QtGui.QPalette.WindowText):
        p.setColor(QtGui.QPalette.Disabled, role, disabled)
    return p


def apply_theme(app, mode: str):
    """Apply a palette. `system` and `light` use the platform palette."""
    if mode == THEME_DARK:
        app.setPalette(_dark_palette())
    else:
        app.setPalette(app.style().standardPalette())
