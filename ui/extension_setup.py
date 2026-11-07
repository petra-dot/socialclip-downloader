"""The browser-extension setup dialog.

A guide the app can actually act on: it shows what is already in place, the
steps for the browser this machine really has, and the two buttons that do the
work (register the host, hand Firefox its signed add-on).
"""

import os
import subprocess
import sys

from PyQt5 import QtCore, QtWidgets

from core.version import __version__
from ui.style import (
    RADIUS,
    make_caption,
    make_chip,
    make_heading,
    make_title,
    mono_font,
    primary_button_style,
    space,
    token,
)
from utils.ui_helpers import reveal_in_folder

ORDER = ("Chrome", "Edge", "Brave", "Firefox")


def _segment_style() -> str:
    return (
        "QPushButton { padding: 5px 14px; border: 1px solid %(border)s;"
        " border-radius: %(r)dpx; color: %(text)s; background: transparent; }"
        "QPushButton:hover:!checked { border-color: %(accent)s; }"
        "QPushButton:checked { background: %(subtle)s; border-color: %(accent)s;"
        " color: %(accent)s; font-weight: 600; }"
    ) % {
        "border": token("border"),
        "r": RADIUS["control"],
        "text": token("text"),
        "accent": token("accent"),
        "subtle": token("accent_subtle"),
    }


def _path_style() -> str:
    return (
        "QLineEdit { background: %(base)s; color: %(text)s;"
        " border: 1px solid %(border)s; border-radius: %(r)dpx; padding: 4px 6px; }"
    ) % {
        "base": token("base"),
        "text": token("text"),
        "border": token("border"),
        "r": RADIUS["control"],
    }


class ExtensionSetupDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        from core.extension import installed_browsers

        self.setWindowTitle("Browser extension setup")
        self.setMinimumWidth(660)
        self._folders = None
        self._browsers = installed_browsers()
        self._prepare_files()
        self._build()
        self.adjustSize()

    # ------------------------------------------------------------------ setup

    def _prepare_files(self):
        from core.extension import ensure_installed

        try:
            self._folders = ensure_installed()
        except OSError:
            self._folders = None

    def _chromium_folder(self) -> str:
        return (self._folders or {}).get("chromium", "")

    def _firefox_folder(self) -> str:
        return (self._folders or {}).get("firefox", "")

    # ------------------------------------------------------------------ build

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(space("xl"), space("xl"), space("xl"), space("xl"))
        layout.setSpacing(space("lg"))

        layout.addWidget(make_title(QtWidgets.QLabel("Browser extension")))
        layout.addWidget(make_caption(QtWidgets.QLabel(
            "Right-click any video link and send it straight to SocialClip, "
            "without switching windows."
        )))

        layout.addLayout(self._status_row())
        self._register_strip(layout)
        layout.addSpacing(space("sm"))
        layout.addLayout(self._browser_switcher())
        layout.addWidget(self._stack, 1)
        layout.addWidget(self._footer())

    def _status_row(self):
        from core.native_install import host_registered

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(space("sm"))
        ready = bool(self._folders)
        row.addWidget(make_chip(
            "Extension files ready" if ready else "Extension files missing",
            "ok" if ready else "error",
        ))
        registered = host_registered()
        row.addWidget(make_chip(
            "Host registered" if registered else "Host not registered",
            "ok" if registered else "warn",
        ))
        if self._browsers:
            count = len(self._browsers)
            row.addWidget(make_chip(
                "%d browser found" % count if count == 1 else "%d browsers found" % count,
                "accent",
            ))
        row.addStretch(1)
        return row

    def _register_strip(self, layout):
        from core.native_install import host_registered

        if host_registered():
            return
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(space("md"))
        note = QtWidgets.QLabel(
            "A browser cannot reach the app until the host is registered for it."
        )
        note.setWordWrap(True)
        row.addWidget(note, 1)
        button = QtWidgets.QPushButton("Register now")
        button.setStyleSheet(primary_button_style())
        button.clicked.connect(self._register_host)
        row.addWidget(button)
        layout.addLayout(row)

    def _browser_switcher(self):
        order = [name for name in ORDER if name in self._browsers]
        order += [name for name in ORDER if name not in self._browsers]

        self._stack = QtWidgets.QStackedWidget()
        self._group = QtWidgets.QButtonGroup(self)
        self._group.setExclusive(True)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(space("sm"))
        for index, name in enumerate(order):
            button = QtWidgets.QPushButton(name)
            button.setCheckable(True)
            button.setStyleSheet(_segment_style())
            button.setAccessibleName("%s setup steps" % name)
            self._group.addButton(button, index)
            row.addWidget(button)
            self._stack.addWidget(self._page(name))
        row.addStretch(1)
        self._group.button(0).setChecked(True)
        self._group.buttonClicked[int].connect(self._stack.setCurrentIndex)
        return row

    def _page(self, name):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, space("sm"), 0, 0)
        layout.setSpacing(space("md"))

        if name not in self._browsers:
            layout.addWidget(make_caption(QtWidgets.QLabel(
                "%s was not found on this machine. The steps apply once it is "
                "installed." % name
            )))

        if name == "Firefox":
            self._firefox_content(layout)
        else:
            self._chromium_content(layout, name)
        layout.addStretch(1)
        return page

    def _chromium_content(self, layout, name):
        from core.extension import EXTENSION_PAGES

        layout.addLayout(self._step(
            1, "Open the extensions page",
            ("Open " + EXTENSION_PAGES[name], lambda n=name: self._open_page(n)),
        ))
        layout.addLayout(self._step(2, "Turn on Developer mode"))
        layout.addLayout(self._step(
            3, "Load unpacked and pick this folder", ("Open folder", self._open_folder)
        ))
        layout.addLayout(self._path_row(self._chromium_folder()))
        layout.addLayout(self._step(4, "Restart %s" % name))
        layout.addLayout(self._step(
            5, "Right-click a video link and choose Add to SocialClip Queue"
        ))

    def _firefox_content(self, layout):
        button = QtWidgets.QPushButton("Install for Firefox")
        button.setStyleSheet(primary_button_style())
        button.setMaximumWidth(220)
        button.clicked.connect(self._install_firefox)
        layout.addWidget(button, 0, QtCore.Qt.AlignLeft)
        layout.addWidget(make_caption(QtWidgets.QLabel(
            "Downloads the signed add-on for %s and hands it to Firefox, which "
            "asks you to add it. That install is permanent." % __version__
        )))
        layout.addSpacing(space("sm"))
        layout.addWidget(make_heading(QtWidgets.QLabel("Or load it temporarily")))
        layout.addLayout(self._step(
            1, "Open the debugging page", ("Open", lambda: self._open_page("Firefox"))
        ))
        layout.addLayout(self._step(
            2, "Choose Load Temporary Add-on and pick this manifest"
        ))
        layout.addLayout(self._path_row(
            os.path.join(self._firefox_folder(), "manifest.json")
        ))
        layout.addWidget(make_caption(QtWidgets.QLabel(
            "A temporary add-on disappears when Firefox restarts."
        )))

    def _step(self, number, text, action=None):
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(space("md"))
        numeral = QtWidgets.QLabel(str(number))
        numeral.setFixedWidth(16)
        numeral.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignTop)
        font = numeral.font()
        font.setBold(True)
        numeral.setFont(font)
        numeral.setStyleSheet("color: %s;" % token("accent"))
        row.addWidget(numeral)
        label = QtWidgets.QLabel(text)
        label.setWordWrap(True)
        row.addWidget(label, 1)
        if action:
            label_text, slot = action
            button = QtWidgets.QPushButton(label_text)
            button.clicked.connect(slot)
            row.addWidget(button)
        return row

    def _path_row(self, path):
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(space("md"))
        row.addSpacing(24)
        field = QtWidgets.QLineEdit(path)
        field.setReadOnly(True)
        field.setFont(mono_font())
        field.setStyleSheet(_path_style())
        field.setCursorPosition(0)
        field.setAccessibleName("Extension folder")
        row.addWidget(field, 1)
        copy = QtWidgets.QPushButton("Copy path")
        copy.clicked.connect(lambda: self._copy(path))
        row.addWidget(copy)
        return row

    def _footer(self):
        buttons = QtWidgets.QDialogButtonBox()
        copy_all = buttons.addButton(
            "Copy the steps", QtWidgets.QDialogButtonBox.ActionRole
        )
        copy_all.clicked.connect(self._copy_steps)
        folder = buttons.addButton(
            "Open extension folder", QtWidgets.QDialogButtonBox.ActionRole
        )
        folder.clicked.connect(self._open_folder)
        close = buttons.addButton(QtWidgets.QDialogButtonBox.Close)
        close.setDefault(True)
        close.clicked.connect(self.reject)
        return buttons

    # ---------------------------------------------------------------- actions

    def _copy(self, text):
        QtWidgets.QApplication.clipboard().setText(text)

    def _copy_steps(self):
        lines = ["SocialClip browser extension", ""]
        for name in ORDER:
            lines.append("%s" % name)
            if name == "Firefox":
                lines.append(
                    "  1. Install for Firefox in the app (permanent), or open "
                    "about:debugging and Load Temporary Add-on."
                )
                lines.append("  2. Pick: %s"
                             % os.path.join(self._firefox_folder(), "manifest.json"))
            else:
                from core.extension import EXTENSION_PAGES

                lines.append("  1. Open %s" % EXTENSION_PAGES[name])
                lines.append("  2. Turn on Developer mode")
                lines.append("  3. Load unpacked and pick: %s" % self._chromium_folder())
                lines.append("  4. Restart %s" % name)
            lines.append("")
        self._copy("\n".join(lines))

    def _open_folder(self):
        folder = self._chromium_folder()
        if folder:
            reveal_in_folder(folder)

    def _open_page(self, name):
        from core.extension import EXTENSION_PAGES

        exe = self._browsers.get(name)
        page = EXTENSION_PAGES[name]
        if not exe:
            self._copy(page)
            QtWidgets.QMessageBox.information(
                self, name, "%s is not installed here.\n\n%s is on your clipboard."
                % (name, page),
            )
            return
        try:
            subprocess.Popen([exe, page])
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, name, str(exc))

    def _register_host(self):
        from core.extension import CHROMIUM_EXTENSION_ID
        from core.native_install import install

        frozen = bool(getattr(sys, "frozen", False))
        target = sys.executable if frozen else os.path.abspath(sys.argv[0])
        try:
            install(target, CHROMIUM_EXTENSION_ID, frozen=frozen)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Not registered", str(exc))
            return
        QtWidgets.QMessageBox.information(
            self,
            "Host registered",
            "Restart the browsers you already have open so they pick it up.",
        )

    def _install_firefox(self):
        from core.extension import fetch_firefox_xpi
        from utils.ui_helpers import open_file

        try:
            path = fetch_firefox_xpi(__version__)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self,
                "Firefox add-on",
                "Could not fetch the signed add-on for %s.\n\n%s\n\n"
                "Every release attaches it, so check your connection and try "
                "the Release page." % (__version__, exc),
            )
            return
        if open_file(path):
            QtWidgets.QMessageBox.information(
                self, "Firefox add-on", "Firefox should now ask to add SocialClip."
            )
        else:
            QtWidgets.QMessageBox.information(
                self, "Firefox add-on", "Saved to:\n%s\n\nOpen it in Firefox." % path
            )
