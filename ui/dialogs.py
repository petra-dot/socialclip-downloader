import os

from PyQt5 import QtCore, QtGui, QtWidgets

from core.doctor import run_checks
from sites.collections import collection_note
from ui.style import primary_button_style
from utils.file_utils import default_download_folder
from utils.ui_helpers import reveal_in_folder


def _ffmpeg_line(report):
    ffmpeg = report.get("ffmpeg", {})
    if ffmpeg.get("found"):
        version = ffmpeg.get("version") or "version unknown"
        return "ffmpeg: found\n  %s\n  %s" % (ffmpeg.get("path"), version)
    return "ffmpeg: NOT found. Merging/conversion will fail."


def _js_runtime_line(report):
    js = report.get("js_runtime", {})
    if js.get("found"):
        return "JavaScript runtime: %s (%s)" % (js.get("name"), js.get("path"))
    return (
        "JavaScript runtime: NONE found. YouTube downloads will fail with "
        "HTTP 403. Install Deno (winget install DenoLand.Deno) or Node.js."
    )


def _ytdlp_line(report):
    ytdlp = report.get("ytdlp", {})
    version = ytdlp.get("version")
    if not version:
        return "yt-dlp: version unknown"
    age = ytdlp.get("age_days")
    age_text = "%d days old" % age if isinstance(age, int) else "age unknown"
    line = "yt-dlp: %s (%s)" % (version, age_text)
    if ytdlp.get("stale"):
        line += "  STALE - update with: pip install -U yt-dlp"
    return line


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
    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle("Welcome to SocialClip Downloader")
    box.setIcon(QtWidgets.QMessageBox.Information)
    box.setText(text)
    box.setStandardButtons(QtWidgets.QMessageBox.Ok)
    ok_btn = box.button(QtWidgets.QMessageBox.Ok)
    ok_btn.setStyleSheet(primary_button_style())
    ok_btn.setDefault(True)
    box.exec_()


def doctor_lines(report, components=None) -> list:
    """Human-readable Doctor/Health text. Pure, so it is testable."""
    lines = ["Health report (schema %s)" % report.get("schema_version", "1.2"), ""]
    if components:
        lines.append("components:")
        for component in components:
            version = " %s" % component.version if component.version else ""
            detail = " (%s)" % component.detail if component.detail else ""
            lines.append(
                "  %-20s %-8s%s%s"
                % (component.label, component.state, version, detail)
            )
        lines.append("")

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

    lines.append("")
    lines.append(_js_runtime_line(report))
    lines.append(_ytdlp_line(report))
    return lines


def health_summary(components) -> tuple:
    """(headline, tone) for the component list. Pure.

    tone is "ok" when nothing needs attention, "bad" when something is
    "broken", otherwise "warn".
    """
    needing = [c for c in components or [] if c.state in ("missing", "stale", "broken")]
    if not needing:
        return "Everything is working", "ok"
    count = len(needing)
    headline = "%d thing%s need attention" % (count, "" if count == 1 else "s")
    tone = "bad" if any(c.state == "broken" for c in needing) else "warn"
    return headline, tone


def state_chip(state) -> tuple:
    """(text, tone) for one component state. Pure; unknown states are shown."""
    return {
        "ok": ("OK", "ok"),
        "missing": ("MISSING", "bad"),
        "stale": ("STALE", "warn"),
        "broken": ("BROKEN", "bad"),
        "unknown": ("UNKNOWN", "unknown"),
    }.get((state or "").lower(), ((state or "?").upper(), "unknown"))


def show_doctor(parent=None, on_repair=None):
    """Health view: a status dashboard with inline repair. Never blocks."""
    from core.paths import data_dir
    from ui import style
    from workers.maintenance_worker import DoctorCheckWorker

    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Health")
    dialog.resize(640, 480)
    layout = QtWidgets.QVBoxLayout(dialog)

    headline = QtWidgets.QLabel("")
    headline.setAccessibleName("Health summary")
    heading_font = headline.font()
    heading_font.setBold(True)
    base = QtWidgets.QApplication.font().pointSizeF()
    if base and base > 0:
        heading_font.setPointSizeF(base + 3.0)
    headline.setFont(heading_font)
    layout.addWidget(headline)

    subtitle = QtWidgets.QLabel("Checking…")
    subtitle.setAccessibleName("Health check status")
    layout.addWidget(subtitle)

    rows_container = QtWidgets.QWidget()
    rows = QtWidgets.QVBoxLayout(rows_container)
    rows.setContentsMargins(0, 8, 0, 8)
    layout.addWidget(rows_container)

    details_toggle = QtWidgets.QToolButton()
    details_toggle.setText("Details")
    details_toggle.setCheckable(True)
    details_toggle.setArrowType(QtCore.Qt.RightArrow)
    details_toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
    details_toggle.setAccessibleName("Show health report details")
    details_row = QtWidgets.QHBoxLayout()
    details_row.addWidget(details_toggle)
    details_row.addStretch(1)
    layout.addLayout(details_row)

    details_view = QtWidgets.QTextEdit()
    details_view.setReadOnly(True)
    details_view.setAccessibleName("Health report details")
    details_view.setFont(
        QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
    )
    details_view.setVisible(False)
    layout.addWidget(details_view)

    footer = QtWidgets.QHBoxLayout()
    repair_all = QtWidgets.QPushButton("")
    repair_all.setAccessibleName("Repair all components")
    repair_all.setVisible(False)
    footer.addWidget(repair_all)
    footer.addStretch(1)
    open_btn = QtWidgets.QPushButton("Open data folder")
    close_btn = QtWidgets.QPushButton("Close")
    close_btn.setStyleSheet(style.primary_button_style())
    close_btn.setDefault(True)
    footer.addWidget(open_btn)
    footer.addWidget(close_btn)
    layout.addLayout(footer)

    repair_keys = []

    def _repair(keys):
        if on_repair is None or not keys:
            return
        dialog.accept()
        on_repair(keys)

    def _toggle_details(checked):
        details_view.setVisible(checked)
        details_toggle.setArrowType(
            QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
        )

    def _clear_rows():
        while rows.count():
            item = rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_row(component):
        row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        chip_text, tone = state_chip(component.state)
        from ui.style import make_chip
        chip = make_chip(chip_text, tone).label
        chip.setAccessibleName("%s: %s" % (component.label, chip_text))
        row_layout.addWidget(chip)
        name = QtWidgets.QLabel(component.label)
        name.setMinimumWidth(150)
        name.setStyleSheet("font-weight: bold;")
        row_layout.addWidget(name)
        value = QtWidgets.QLabel(component.version or component.detail or "")
        value.setStyleSheet("color: %s;" % style.state_color("muted"))
        row_layout.addWidget(value, 1)
        if component.action in ("install", "update"):
            repair = QtWidgets.QPushButton("Repair")
            repair.setAccessibleName("Repair %s" % component.label)
            repair.clicked.connect(
                lambda _checked=False, key=component.key: _repair([key])
            )
            row_layout.addWidget(repair)
        rows.addWidget(row)

    def _on_done(payload):
        components, report = payload
        headline_text, tone = health_summary(components)
        headline.setText(headline_text)
        head_color = style.state_color(tone)
        if head_color:
            headline.setStyleSheet("color: %s;" % head_color)
        subtitle.setText("Checked just now")
        _clear_rows()
        for component in components:
            _add_row(component)
        details_view.setPlainText("\n".join(doctor_lines(report, components)))
        keys = [
            c.key for c in components if c.action in ("install", "update")
        ]
        repair_keys[:] = keys
        if len(keys) > 1:
            repair_all.setText("Repair all (%d)" % len(keys))
            repair_all.setVisible(True)

    def _on_error(message):
        subtitle.setText(message or "The check failed.")
        subtitle.setStyleSheet("color: %s;" % style.state_color("muted"))

    details_toggle.toggled.connect(_toggle_details)
    open_btn.clicked.connect(lambda: reveal_in_folder(data_dir()))
    close_btn.clicked.connect(dialog.reject)
    repair_all.clicked.connect(lambda: _repair(repair_keys))

    worker = DoctorCheckWorker()
    worker.done_signal.connect(_on_done)
    worker.error_signal.connect(_on_error)
    dialog._doctor_worker = worker
    worker.start()
    dialog.exec_()


def show_update_ready(parent, version: str) -> bool:
    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle("Update ready")
    box.setText(
        "SocialClip Downloader %s was downloaded and verified.\n\n"
        "Install it now and restart?" % (version or "")
    )
    install = box.addButton("Install and restart", QtWidgets.QMessageBox.AcceptRole)
    install.setStyleSheet(primary_button_style())
    install.setDefault(True)
    box.addButton("Later", QtWidgets.QMessageBox.RejectRole)
    box.exec_()
    return box.clickedButton() is install


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
        add_label = QtWidgets.QLabel("Add first")
        row.addWidget(add_label)
        self.count_spin = QtWidgets.QSpinBox()
        self.count_spin.setRange(1, self._max)
        self.count_spin.setValue(self._default)
        add_label.setBuddy(self.count_spin)
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
        ok_btn = buttons.button(QtWidgets.QDialogButtonBox.Ok)
        ok_btn.setStyleSheet(primary_button_style())
        ok_btn.setDefault(True)
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
    presets_label = QtWidgets.QLabel("Your presets:")
    layout.addWidget(presets_label)
    listing = QtWidgets.QListWidget()
    for preset in store.user():
        listing.addItem(preset.name)
    presets_label.setBuddy(listing)
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
        from core.paths import data_dir
        from sites.cookies import BROWSERS, cookie_status

        self.setWindowTitle("Cookies")
        self.resize(520, 360)
        layout = QtWidgets.QVBoxLayout(self)

        row = QtWidgets.QHBoxLayout()
        browser_label = QtWidgets.QLabel("Use cookies from:")
        row.addWidget(browser_label)
        self.browser_combo = QtWidgets.QComboBox()
        self.browser_combo.setAccessibleName("Cookies browser")
        self.browser_combo.addItem("No cookies", "")
        for browser in BROWSERS:
            self.browser_combo.addItem(browser.capitalize(), browser)
        saved = QtCore.QSettings().value("cookies/browser", "") or ""
        index = self.browser_combo.findData(saved)
        self.browser_combo.setCurrentIndex(index if index >= 0 else 0)
        browser_label.setBuddy(self.browser_combo)
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
        ok_btn = buttons.button(QtWidgets.QDialogButtonBox.Ok)
        ok_btn.setStyleSheet(primary_button_style())
        ok_btn.setDefault(True)
        open_btn = buttons.addButton(
            "Open cookie folder", QtWidgets.QDialogButtonBox.ActionRole
        )
        open_btn.clicked.connect(lambda: reveal_in_folder(data_dir()))
        layout.addWidget(buttons)

    def chosen_browser(self) -> str:
        return self.browser_combo.currentData()


class EditJobDialog(QtWidgets.QDialog):
    """Edit one pending queue job's options. Prefilled from its options dict."""

    def __init__(self, parent, job):
        super().__init__(parent)
        from utils.file_utils import OUTPUT_FORMATS, RESOLUTIONS, output_index_for

        opts = job.options or {}
        self.setWindowTitle("Edit job options")
        self.resize(520, 280)
        layout = QtWidgets.QVBoxLayout(self)

        fmt_row = QtWidgets.QHBoxLayout()
        edit_output_label = QtWidgets.QLabel("Output:")
        fmt_row.addWidget(edit_output_label)
        self.output_combo = QtWidgets.QComboBox()
        self.output_combo.setAccessibleName("Edit job output format")
        self.output_combo.addItems(OUTPUT_FORMATS)
        index = output_index_for(opts.get("output_type", "MP4"))
        self.output_combo.setCurrentIndex(index if index >= 0 else 0)
        edit_output_label.setBuddy(self.output_combo)
        fmt_row.addWidget(self.output_combo)
        edit_res_label = QtWidgets.QLabel("Resolution:")
        fmt_row.addWidget(edit_res_label)
        self.resolution_combo = QtWidgets.QComboBox()
        self.resolution_combo.setAccessibleName("Edit job target resolution")
        self.resolution_combo.addItems(RESOLUTIONS)
        self.resolution_combo.setCurrentText(str(opts.get("target_resolution", 1080)))
        edit_res_label.setBuddy(self.resolution_combo)
        fmt_row.addWidget(self.resolution_combo)
        fmt_row.addStretch(1)
        layout.addLayout(fmt_row)

        folder_row = QtWidgets.QHBoxLayout()
        folder_label = QtWidgets.QLabel("Folder:")
        folder_row.addWidget(folder_label)
        self.folder_input = QtWidgets.QLineEdit(
            os.path.dirname(opts.get("outtmpl", "") or "")
        )
        self.folder_input.setAccessibleName("Edit job download folder")
        folder_label.setBuddy(self.folder_input)
        folder_row.addWidget(self.folder_input)
        browse = QtWidgets.QPushButton("Browse")
        browse.clicked.connect(self._browse)
        folder_row.addWidget(browse)
        layout.addLayout(folder_row)

        sub_row = QtWidgets.QHBoxLayout()
        edit_sub_label = QtWidgets.QLabel("Subtitles:")
        sub_row.addWidget(edit_sub_label)
        self.subtitle_combo = QtWidgets.QComboBox()
        self.subtitle_combo.setAccessibleName("Edit job subtitle delivery")
        from core.subtitles import DELIVERY_CHOICES
        for value, label in DELIVERY_CHOICES:
            self.subtitle_combo.addItem(label, value)
        saved = opts.get("subtitles", "off")
        sub_index = self.subtitle_combo.findData(saved)
        self.subtitle_combo.setCurrentIndex(sub_index if sub_index >= 0 else 0)
        edit_sub_label.setBuddy(self.subtitle_combo)
        sub_row.addWidget(self.subtitle_combo)
        sub_row.addStretch(1)
        layout.addLayout(sub_row)

        cookie_row = QtWidgets.QHBoxLayout()
        edit_cookie_label = QtWidgets.QLabel("Cookies file:")
        cookie_row.addWidget(edit_cookie_label)
        self.cookies_input = QtWidgets.QLineEdit(opts.get("cookies_file", "") or "")
        self.cookies_input.setAccessibleName("Edit job cookies file path")
        self.cookies_input.setPlaceholderText("Optional: path to cookies.txt for auth")
        edit_cookie_label.setBuddy(self.cookies_input)
        cookie_row.addWidget(self.cookies_input)
        layout.addLayout(cookie_row)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_btn = buttons.button(QtWidgets.QDialogButtonBox.Ok)
        ok_btn.setStyleSheet(primary_button_style())
        ok_btn.setDefault(True)
        layout.addWidget(buttons)

    def _browse(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose folder", self.folder_input.text()
        )
        if folder:
            self.folder_input.setText(folder)

    def chosen(self) -> dict:
        return {
            "save_dir": self.folder_input.text().strip(),
            "output_text": self.output_combo.currentText(),
            "resolution": self.resolution_combo.currentText(),
            "cookies_path": self.cookies_input.text().strip(),
            "subtitles": self.subtitle_combo.currentData(),
        }
