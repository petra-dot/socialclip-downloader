from PyQt5 import QtCore, QtWidgets

from core.doctor import run_checks
from utils.file_utils import default_download_folder


def _ffmpeg_line(report):
    ffmpeg = report.get("ffmpeg", {})
    if ffmpeg.get("found"):
        version = ffmpeg.get("version") or "version unknown"
        return "ffmpeg: found\n  %s\n  %s" % (ffmpeg.get("path"), version)
    return "ffmpeg: NOT found. Merging/conversion will fail."


def show_welcome(parent=None):
    folder = default_download_folder()
    try:
        # The welcome only needs to know whether ffmpeg exists. Skip the
        # network probe and the `ffmpeg -version` subprocess: on a first run
        # they froze the window for seconds before it opened.
        report = run_checks(
            probe=lambda: (None, "not checked"),
            runner=lambda cmd: None,
        )
    except Exception:
        report = {}

    text = (
        "SocialClip Downloader downloads video and audio from YouTube, "
        "Douyin, Instagram, Twitter/X, TikTok, Bilibili, Facebook and other "
        "yt-dlp-supported sites. All processing happens on your machine.\n\n"
        "Default save folder:\n%s\n\n"
        "%s\n\n"
        "Cookies: some sites (Douyin, Instagram, Twitter/X, TikTok, Bilibili, "
        "Facebook) may require a cookies.txt export next to the app."
        % (folder, _ffmpeg_line(report))
    )
    QtWidgets.QMessageBox.information(parent, "Welcome to SocialClip Downloader", text)


def show_doctor(parent=None):
    try:
        report = run_checks()
    except Exception as exc:
        report = {"schema_version": "1.1", "error": str(exc)}

    lines = ["Doctor report (schema %s)" % report.get("schema_version", "1.1"), ""]

    ffmpeg = report.get("ffmpeg", {})
    lines.append("ffmpeg:")
    if ffmpeg.get("found"):
        lines.append("  path: %s" % ffmpeg.get("path"))
        lines.append("  version: %s" % (ffmpeg.get("version") or "unknown"))
    else:
        lines.append("  not found")

    lines.append("")
    lines.append("cookies:")
    found = [c for c in report.get("cookies", []) if c.get("found")]
    if found:
        for cookie in found:
            lines.append("  %s: %s" % (cookie.get("platform"), cookie.get("path")))
    else:
        lines.append("  none found")

    network = report.get("network", {})
    lines.append("")
    lines.append("network:")
    lines.append("  ok: %s" % network.get("ok"))
    lines.append("  detail: %s" % network.get("detail"))

    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Doctor")
    dialog.resize(560, 400)
    layout = QtWidgets.QVBoxLayout(dialog)
    view = QtWidgets.QTextEdit()
    view.setReadOnly(True)
    view.setPlainText("\n".join(lines))
    layout.addWidget(view)
    buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.exec_()


def show_update_ready(parent, version: str) -> bool:
    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle("Update ready")
    box.setText(
        "SocialClip Downloader %s was downloaded and verified.\n\n"
        "Install it now and restart?" % (version or "")
    )
    install = box.addButton("Install and restart", QtWidgets.QMessageBox.AcceptRole)
    box.addButton("Later", QtWidgets.QMessageBox.RejectRole)
    box.exec_()
    return box.clickedButton() is install


from sites.collections import collection_note


def _platform_label(platform: str) -> str:
    return (platform or "This site").capitalize()


class ExpandConfirmDialog(QtWidgets.QDialog):
    """Confirm how many videos of a found collection to queue."""

    def __init__(self, result, skipped_count=0, parent=None):
        super().__init__(parent)
        self.result = result
        total = result.total if result.total is not None else len(result.entries)
        self._max = max(1, total)
        self._default = min(200, len(result.entries) or self._max)

        self.setWindowTitle("Add collection to queue")
        self.resize(560, 420)
        layout = QtWidgets.QVBoxLayout(self)

        found = result.total if result.total is not None else len(result.entries)
        layout.addWidget(QtWidgets.QLabel(
            "%s: %d video(s) found." % (_platform_label(result.platform), found)
        ))

        note = collection_note(result.platform)
        if note:
            hint = QtWidgets.QLabel(note)
            hint.setWordWrap(True)
            layout.addWidget(hint)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Add first"))
        self.count_spin = QtWidgets.QSpinBox()
        self.count_spin.setRange(1, self._max)
        self.count_spin.setValue(self._default)
        row.addWidget(self.count_spin)
        row.addWidget(QtWidgets.QLabel("of %d" % found))
        row.addStretch(1)
        layout.addLayout(row)

        preview = QtWidgets.QListWidget()
        for entry in result.entries[:20]:
            preview.addItem(entry.title)
        if len(result.entries) > 20:
            preview.addItem("...and %d more" % (len(result.entries) - 20))
        layout.addWidget(preview)

        if skipped_count:
            layout.addWidget(QtWidgets.QLabel(
                "%d already in the queue will be skipped." % skipped_count
            ))

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chosen_limit(self) -> int:
        return self.count_spin.value()


def manage_presets(parent, store) -> bool:
    """Rename or delete user presets. Returns True if anything changed."""
    changed = False
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Manage presets")
    dialog.resize(420, 320)
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.addWidget(QtWidgets.QLabel("Your presets:"))
    listing = QtWidgets.QListWidget()
    for preset in store.user():
        listing.addItem(preset.name)
    layout.addWidget(listing)

    buttons = QtWidgets.QHBoxLayout()
    rename_btn = QtWidgets.QPushButton("Rename")
    delete_btn = QtWidgets.QPushButton("Delete")
    buttons.addWidget(rename_btn)
    buttons.addWidget(delete_btn)
    buttons.addStretch(1)
    close_btn = QtWidgets.QPushButton("Close")
    buttons.addWidget(close_btn)
    layout.addLayout(buttons)

    def selected_name():
        item = listing.currentItem()
        return item.text() if item else ""

    def on_rename():
        nonlocal changed
        old = selected_name()
        if not old:
            return
        new, ok = QtWidgets.QInputDialog.getText(
            dialog, "Rename preset", "New name:", text=old
        )
        if ok and new.strip() and store.rename(old, new.strip()):
            changed = True
            listing.clear()
            for preset in store.user():
                listing.addItem(preset.name)

    def on_delete():
        nonlocal changed
        name = selected_name()
        if not name:
            return
        confirm = QtWidgets.QMessageBox.question(
            dialog, "Delete preset", "Delete '%s'?" % name
        )
        if confirm == QtWidgets.QMessageBox.Yes and store.remove(name):
            changed = True
            listing.clear()
            for preset in store.user():
                listing.addItem(preset.name)

    rename_btn.clicked.connect(on_rename)
    delete_btn.clicked.connect(on_delete)
    close_btn.clicked.connect(dialog.accept)
    dialog.exec_()
    return changed


class CookiesDialog(QtWidgets.QDialog):
    """Choose a browser to source cookies from. Never reads a browser."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from sites.cookies import BROWSERS, app_dir, cookie_status
        from utils.ui_helpers import reveal_in_folder

        self.setWindowTitle("Cookies")
        self.resize(520, 360)
        layout = QtWidgets.QVBoxLayout(self)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Use cookies from:"))
        self.browser_combo = QtWidgets.QComboBox()
        self.browser_combo.setAccessibleName("Cookies browser")
        self.browser_combo.addItem("No cookies", "")
        for browser in BROWSERS:
            self.browser_combo.addItem(browser.capitalize(), browser)
        saved = QtCore.QSettings().value("cookies/browser", "") or ""
        index = self.browser_combo.findData(saved)
        self.browser_combo.setCurrentIndex(index if index >= 0 else 0)
        row.addWidget(self.browser_combo)
        row.addStretch(1)
        layout.addLayout(row)

        layout.addWidget(QtWidgets.QLabel("Cookie files found:"))
        self.status_list = QtWidgets.QListWidget()
        self.status_list.setAccessibleName("Cookie file status")
        for _platform, name, path in cookie_status():
            self.status_list.addItem("%s: %s" % (name, path or "none"))
        layout.addWidget(self.status_list)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        open_btn = buttons.addButton(
            "Open cookie folder", QtWidgets.QDialogButtonBox.ActionRole
        )
        open_btn.clicked.connect(lambda: reveal_in_folder(app_dir()))
        layout.addWidget(buttons)

    def chosen_browser(self) -> str:
        return self.browser_combo.currentData()
