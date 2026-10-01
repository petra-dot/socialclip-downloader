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
        report = run_checks()
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
