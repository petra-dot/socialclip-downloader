"""Shared UI styling: semantic design tokens, light/dark themes.

Widgets read semantic tokens (`token`, `space`) instead of literal hex, so the
whole app retunes from one table. Headings use the application font rather than
a fixed pixel size, so they follow the user's system text scaling.
"""

from PyQt5 import QtCore, QtGui, QtWidgets

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

# Semantic tokens. Widgets read these; no literal hex lives outside this table.
# "warn"/"bad"/"unknown" are the Health view's tone names; they reuse the same
# per-theme table rather than adding a second colour system.
_LIGHT = {
    "window": "#f3f3f3", "base": "#ffffff", "panel": "#ebebeb",
    "border": "#d0d0d0", "divider": "#e6e6e6",
    "text": "#1b1b1b", "text_secondary": "#5a5a5a", "text_muted": "#6b6b6b",
    "accent": "#0d7d75", "accent_hover": "#0b6a63", "accent_pressed": "#095a54",
    "accent_subtle": "#e2f1ef", "on_accent": "#ffffff",
    "ok": "#1a7f37", "error": "#b42318", "busy": "#0b6bcb", "warn": "#9a6700",
    "muted": "#57606a", "bad": "#b42318", "unknown": "#57606a",
    "ok_tint": "#e8f5ec", "error_tint": "#fdecea", "warn_tint": "#fdf3e2",
    "busy_tint": "#e7f0fb", "muted_tint": "#eceef1",
}
_DARK = {
    "window": "#252628", "base": "#1c1d1f", "panel": "#2c2e31",
    "border": "#3c4043", "divider": "#33363a",
    "text": "#e8eaed", "text_secondary": "#c2c8d0", "text_muted": "#9aa4b2",
    "accent": "#3fb0a6", "accent_hover": "#4cc0b6", "accent_pressed": "#2f8f86",
    "accent_subtle": "#123c39", "on_accent": "#0b1f1d",
    "ok": "#3fb950", "error": "#f85149", "busy": "#4c9aff", "warn": "#d29922",
    "muted": "#9aa4b2", "bad": "#f85149", "unknown": "#9aa4b2",
    "ok_tint": "#132b1a", "error_tint": "#331715", "warn_tint": "#2f2713",
    "busy_tint": "#12243a", "muted_tint": "#2a2d31",
}

SPACING = {"xs": 4, "sm": 6, "md": 8, "lg": 12, "xl": 16, "xxl": 24}
RADIUS = {"control": 4, "panel": 6, "chip": 8}

_current_mode = THEME_SYSTEM


def is_dark() -> bool:
    return _current_mode == THEME_DARK


def _table() -> dict:
    return _DARK if is_dark() else _LIGHT


def token(name: str) -> str:
    """The current theme's value for a semantic token name."""
    return _table().get(name, "")


def space(name: str) -> int:
    return SPACING.get(name, SPACING["md"])


def state_color(kind: str) -> str:
    """A hex color for a UI state. Now a thin alias of `token`."""
    return token(kind)


def state_style(kind: str) -> str:
    """A stylesheet snippet that colors a widget by state."""
    color = state_color(kind)
    return "color: %s;" % color if color else ""


def _relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]

    def linear(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG contrast ratio between two #rrggbb colors. Pure."""
    a, b = _relative_luminance(fg), _relative_luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def make_chip(text: str, tone: str = "neutral"):
    """A rounded pill; the child QLabel is exposed as `.label`."""
    color = token(tone) if tone != "neutral" else token("text_secondary")
    border = token(tone) if tone != "neutral" else token("border")
    label = QtWidgets.QLabel(text)
    label.setStyleSheet(
        "border: 1px solid %s; border-radius: %dpx; padding: 1px 8px; color: %s;"
        % (border, RADIUS["chip"], color)
    )
    label.setAlignment(QtCore.Qt.AlignCenter)
    holder = QtWidgets.QWidget()
    row = QtWidgets.QHBoxLayout(holder)
    row.setContentsMargins(4, 0, 4, 0)
    row.addStretch(1)
    row.addWidget(label)
    row.addStretch(1)
    holder.label = label
    return holder


def make_result_panel():
    """The right-hand result panel shared by the Download and Convert tabs.

    Returns (frame, labels) where labels has keys `caption`, `body`, `ready`.
    The caller owns the progress bar, the action buttons, and the state logic.
    """
    frame = QtWidgets.QFrame()
    frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
    frame.setBackgroundRole(QtGui.QPalette.AlternateBase)
    frame.setAutoFillBackground(True)
    frame.setMinimumWidth(240)
    box = QtWidgets.QVBoxLayout(frame)
    box.setContentsMargins(space("lg"), space("md"), space("lg"), space("md"))
    box.setSpacing(space("sm"))

    caption = QtWidgets.QLabel("Result")
    caption.setStyleSheet("color: %s;" % token("text_muted"))
    box.addWidget(caption)
    body = QtWidgets.QLabel("")
    body.setWordWrap(True)
    box.addWidget(body)
    ready = QtWidgets.QLabel("")
    ready.setWordWrap(True)
    ready.setVisible(False)
    box.addWidget(ready)
    box.addStretch(1)
    return frame, {"caption": caption, "body": body, "ready": ready,
                   "layout": box}


def primary_button_style() -> str:
    """Accent-filled primary button, theme-aware."""
    a, h, p = token("accent"), token("accent_hover"), token("accent_pressed")
    on, border, muted = token("on_accent"), token("border"), token("text_muted")
    r = RADIUS["control"]
    return (
        "QPushButton { background: %(a)s; color: %(on)s; border: 1px solid %(a)s;"
        " border-radius: %(r)dpx; padding: 5px 14px; font-weight: 600; }"
        "QPushButton:hover { background: %(h)s; border-color: %(h)s; }"
        "QPushButton:pressed { background: %(p)s; border-color: %(p)s; }"
        "QPushButton:disabled { background: %(b)s; border-color: %(b)s;"
        " color: %(m)s; }"
        % {"a": a, "h": h, "p": p, "on": on, "b": border, "m": muted, "r": r}
    )


def make_title(label):
    """Style a QLabel as a prominent title, scaled from the app font."""
    font = label.font()
    font.setBold(True)
    base = QtWidgets.QApplication.font().pointSizeF()
    if base and base > 0:
        font.setPointSizeF(base + 2.0)
    label.setFont(font)
    return label


def make_caption(label):
    """Style a QLabel as muted secondary caption text."""
    label.setStyleSheet("color: %s;" % token("text_muted"))
    return label


def mono_font():
    """The platform's fixed-width font, for paths and ids."""
    return QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)


def danger_text_style() -> str:
    """Red text for a destructive action on a native button.

    Only the colour is set, so the button keeps the platform's own chrome and
    height and stays aligned with the buttons beside it. A drawn border on a
    native button renders as a crude box and changes its size.
    """
    return "QPushButton { color: %s; } QPushButton:disabled { color: %s; }" % (
        token("error"), token("text_muted"),
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
