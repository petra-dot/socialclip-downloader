from PyQt5 import QtWidgets

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
