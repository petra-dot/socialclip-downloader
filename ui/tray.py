"""Tray icon and the close-to-background policy.

Closing the window keeps the app alive in the tray, which is what lets the
browser keep handing it jobs after the user thinks they quit.
"""

from PyQt5 import QtWidgets


def should_hide_on_close(tray_available: bool, quitting: bool,
                         setting: bool) -> bool:
    """True when closing should only hide the window."""
    return bool(tray_available and setting and not quitting)


def make_tray(parent, on_show, on_quit):
    """A tray icon with Show and Quit, or None where the desktop has no tray."""
    if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
        return None
    tray = QtWidgets.QSystemTrayIcon(parent.windowIcon(), parent)
    tray.setToolTip("SocialClip Downloader")
    menu = QtWidgets.QMenu(parent)
    menu.addAction("Show window", on_show)
    menu.addSeparator()
    menu.addAction("Quit", on_quit)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: on_show()
        if reason == QtWidgets.QSystemTrayIcon.Trigger
        else None
    )
    tray.show()
    return tray
