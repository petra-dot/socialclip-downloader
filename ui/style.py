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


# "warn"/"bad"/"unknown" are the Health view's tone names; they reuse the same
# per-theme table as "error"/"muted" rather than adding a second colour system.
_STATE_LIGHT = {"ok": "#1a7f37", "error": "#b42318",
                "busy": "#0b6bcb", "muted": "#57606a",
                "warn": "#9a6700", "bad": "#b42318", "unknown": "#57606a"}
_STATE_DARK = {"ok": "#3fb950", "error": "#f85149",
               "busy": "#4c9aff", "muted": "#9aa4b2",
               "warn": "#d29922", "bad": "#f85149", "unknown": "#9aa4b2"}

_current_mode = THEME_SYSTEM


def is_dark() -> bool:
    return _current_mode == THEME_DARK


def state_color(kind: str) -> str:
    """A hex color for a UI state.

    Job states use ok / error / busy / muted; the Health view's tones are
    ok / warn / bad / unknown. Both resolve from the same per-theme table.
    """
    table = _STATE_DARK if is_dark() else _STATE_LIGHT
    return table.get(kind, "")


def state_style(kind: str) -> str:
    """A stylesheet snippet that colors a widget by state."""
    color = state_color(kind)
    return "color: %s;" % color if color else ""


def danger_text_style() -> str:
    """Red text for a destructive action on a native button.

    Only the colour is set, so the button keeps the platform's own chrome and
    height and stays aligned with the buttons beside it. A drawn border on a
    native button renders as a crude box and changes its size.
    """
    return "QPushButton { color: %s; } QPushButton:disabled { color: %s; }" % (
        state_color("error"), state_color("muted"),
    )


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
    # 154,164,178 clears 4.5:1 on the #252628 window; 130,135,143 did not.
    disabled = QtGui.QColor(154, 164, 178)
    p.setColor(QtGui.QPalette.Window, window)
    p.setColor(QtGui.QPalette.WindowText, text)
    p.setColor(QtGui.QPalette.Base, base)
    p.setColor(QtGui.QPalette.AlternateBase, window)
    p.setColor(QtGui.QPalette.Text, text)
    p.setColor(QtGui.QPalette.Button, window)
    p.setColor(QtGui.QPalette.ButtonText, text)
    p.setColor(QtGui.QPalette.BrightText, QtGui.QColor(255, 255, 255))
    p.setColor(QtGui.QPalette.ToolTipBase, base)
    p.setColor(QtGui.QPalette.ToolTipText, text)
    p.setColor(QtGui.QPalette.Highlight, QtGui.QColor(45, 137, 239))
    p.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(255, 255, 255))
    p.setColor(QtGui.QPalette.PlaceholderText, QtGui.QColor(150, 155, 163))
    for role in (QtGui.QPalette.Text, QtGui.QPalette.ButtonText,
                 QtGui.QPalette.WindowText):
        p.setColor(QtGui.QPalette.Disabled, role, disabled)
    p.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Base, window)
    p.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Button, window)
    return p


# The platform's default style, captured before we ever switch away from it, so
# "Default"/"Light" can restore the native look after a spell in dark.
_native_style = None


def apply_theme(app, mode: str):
    """Apply a theme.

    The palette is only honored under a non-native style, so dark runs on
    Fusion. Without this, Windows' native style keeps drawing light widget
    backgrounds while the palette paints the text light: unreadable.
    """
    global _native_style, _current_mode
    _current_mode = mode
    if _native_style is None:
        _native_style = app.style().objectName() or None
    if mode == THEME_DARK:
        app.setStyle("Fusion")
        app.setPalette(_dark_palette())
    else:
        if _native_style:
            app.setStyle(_native_style)
        app.setPalette(app.style().standardPalette())
