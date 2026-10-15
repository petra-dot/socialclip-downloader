import datetime
import os

from PyQt5 import QtGui, QtWidgets, QtCore

from core.collections import new_entries
from core.presets import PresetStore, default_presets_path
from core.queue import Queue, QueueStore, TERMINAL_STATES, can_remove
from sites.collections import classify_url
from sites.cookies import default_cookie_dir
from ui.dialogs import ExpandConfirmDialog
from ui.platform_icons import icon_for_url
from ui.style import make_heading
from utils.file_utils import (
    default_download_folder,
    restore_or,
    OUTPUT_FORMATS,
    RESOLUTIONS,
    output_index_for,
)
from utils.ui_helpers import looks_like_url
from workers.expand_worker import ExpandWorker
from workers.queue_worker import QueueWorker


def _queue_path() -> str:
    """Queue file shared with the CLI (see cli.py:_queue_path)."""
    override = os.environ.get("SOCIALCLIP_QUEUE")
    if override:
        return override
    return os.path.join(default_cookie_dir(), "queue.json")


def build_job_options(save_dir: str, output_text: str, resolution: str,
                      cookies_path: str, subtitles: str = "off",
                      cookies_from_browser: str = "") -> dict:
    """Build the exact option set download_one accepts (no unknown keys)."""
    output_type = "MP3" if "MP3" in output_text else "MP4"
    return {
        "outtmpl": os.path.join(save_dir, "%(title)s.%(ext)s"),
        "output_type": output_type,
        "convert": output_type == "MP4",
        "target_resolution": int(resolution),
        "cookies_file": cookies_path,
        "subtitles": subtitles,
        "cookies_from_browser": cookies_from_browser,
    }


def state_label(state: str) -> str:
    """'running' -> 'Running', so the Status column reads as prose."""
    return (state or "").capitalize()


def state_kind(state: str) -> str:
    """Map a job state to a UI state color kind."""
    if state == "done":
        return "ok"
    if state == "failed":
        return "error"
    if state == "running":
        return "busy"
    return "muted"


def state_brush(state: str):
    """A foreground brush for a job state, so success and failure scan."""
    from ui.style import state_color
    return QtGui.QBrush(QtGui.QColor(state_color(state_kind(state))))


def job_options_summary(options: dict) -> str:
    """A short, human summary of a job's baked options, e.g. 'MP4 1080p'."""
    opts = options or {}
    fmt = "MP3" if opts.get("output_type") == "MP3" else "MP4"
    parts = [fmt]
    if fmt == "MP4" and opts.get("target_resolution"):
        parts.append("%sp" % opts["target_resolution"])
    subtitles = opts.get("subtitles", "off")
    if subtitles and subtitles != "off":
        parts.append("subs %s" % subtitles)
    return " ".join(parts)


def parse_url_lines(text: str) -> list:
    seen = set()
    urls = []
    for line in (text or "").splitlines():
        url = line.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


class BulkPasteDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add URLs")
        self.resize(520, 320)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("Paste one URL per line:"))
        self.text = QtWidgets.QTextEdit()
        self.text.setPlaceholderText("https://...\nhttps://...")
        layout.addWidget(self.text)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def urls(self):
        return parse_url_lines(self.text.toPlainText())


class QueueTab(QtWidgets.QWidget):
    def __init__(self, cookies_file_ref):
        super().__init__()
        self.cookies_file_ref = cookies_file_ref
        self.queue_worker = None
        self._expand_worker = None
        self._expand_queue = []
        self._row_for_id = {}
        self.settings = QtCore.QSettings()
        self.preset_store = PresetStore(default_presets_path())
        self.preset_store.load()
        self._applying_preset = False
        store = QueueStore(_queue_path())
        store.load()
        self.queue = Queue(store)
        self.init_ui()
        self.refresh_table()

    def init_ui(self):
        queue_layout = QtWidgets.QVBoxLayout(self)
        queue_layout.setContentsMargins(8, 8, 8, 8)
        queue_layout.setSpacing(6)

        urls_heading = QtWidgets.QLabel("Queue")
        make_heading(urls_heading)
        queue_layout.addWidget(urls_heading)

        urls_toolbar = QtWidgets.QHBoxLayout()
        self.add_urls_btn = QtWidgets.QPushButton("Add URLs")
        self.add_urls_btn.clicked.connect(self.on_add_urls)
        urls_toolbar.addWidget(self.add_urls_btn)
        self.paste_urls_btn = QtWidgets.QPushButton("Paste")
        self.paste_urls_btn.clicked.connect(self.on_paste_urls)
        urls_toolbar.addWidget(self.paste_urls_btn)
        self.clear_finished_btn = QtWidgets.QPushButton("Clear finished")
        self.clear_finished_btn.clicked.connect(self.on_clear_finished)
        urls_toolbar.addWidget(self.clear_finished_btn)
        self.retry_failed_btn = QtWidgets.QPushButton("Retry failed")
        self.retry_failed_btn.clicked.connect(self.on_retry_failed)
        urls_toolbar.addWidget(self.retry_failed_btn)
        urls_toolbar.addStretch(1)
        queue_layout.addLayout(urls_toolbar)

        # Inline hint for recoverable mistakes, instead of a modal popup.
        self.hint_label = QtWidgets.QLabel("")
        self.hint_label.setVisible(False)
        self.hint_label.setWordWrap(True)
        queue_layout.addWidget(self.hint_label)

        self.batch_table = QtWidgets.QTableWidget(0, 3)
        self.batch_table.setAccessibleName("Download queue")
        self.batch_table.setHorizontalHeaderLabels(["Video", "Status", "Detail"])
        self.batch_table.horizontalHeader().setStretchLastSection(True)
        self.batch_table.setColumnWidth(0, 340)
        self.batch_table.setColumnWidth(1, 90)
        self.batch_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.batch_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.batch_table.cellClicked.connect(self.on_cell_clicked)
        # Right-click a row to remove a mistakenly added link.
        self.batch_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.batch_table.customContextMenuRequested.connect(self.on_table_context_menu)
        # Keyboard path to the row action: the context menu needs a mouse.
        del_shortcut = QtWidgets.QShortcut(QtCore.Qt.Key_Delete, self.batch_table)
        del_shortcut.setContext(QtCore.Qt.WidgetShortcut)
        del_shortcut.activated.connect(self.on_remove_selected)

        # Guidance shown over the table while the queue is empty.
        self.empty_label = QtWidgets.QLabel(
            "No downloads queued yet.\n\n"
            "Click Add URLs or Paste to queue videos here.",
            self.batch_table.viewport(),
        )
        self.empty_label.setAlignment(QtCore.Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setVisible(False)
        self.batch_table.viewport().installEventFilter(self)
        queue_layout.addWidget(self.batch_table)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        queue_layout.addWidget(self.progress_bar)

        opts_heading = QtWidgets.QLabel("Output")
        make_heading(opts_heading)
        queue_layout.addWidget(opts_heading)

        preset_row = QtWidgets.QHBoxLayout()
        preset_label = QtWidgets.QLabel("Preset:")
        preset_row.addWidget(preset_label)
        self.batch_preset_combo = QtWidgets.QComboBox()
        self.batch_preset_combo.setAccessibleName("Queue preset")
        self.batch_preset_combo.setToolTip(
            "Applies format, resolution, folder, and cookies. "
            "The Queue always converts MP4 to the chosen resolution; "
            "convert and filename options are Download-tab only."
        )
        self.batch_preset_combo.currentIndexChanged.connect(self.on_preset_selected)
        preset_row.addWidget(self.batch_preset_combo)
        preset_label.setBuddy(self.batch_preset_combo)
        preset_row.addStretch(1)
        queue_layout.addLayout(preset_row)

        queue_save_layout = QtWidgets.QHBoxLayout()
        self.batch_save_dir_input = QtWidgets.QLineEdit(
            restore_or(default_download_folder(), self.settings.value("batch/save_dir"))
        )
        self.batch_save_dir_input.setAccessibleName("Queue download folder")
        self.batch_save_dir_input.editingFinished.connect(self._on_batch_save_dir_changed)
        queue_save_layout.addWidget(self.batch_save_dir_input)
        batch_browse_btn = QtWidgets.QPushButton("Browse")
        batch_browse_btn.clicked.connect(self.on_batch_browse)
        queue_save_layout.addWidget(batch_browse_btn)
        queue_layout.addLayout(queue_save_layout)

        queue_opts_layout = QtWidgets.QHBoxLayout()
        self.batch_output_combo = QtWidgets.QComboBox()
        self.batch_output_combo.setAccessibleName("Queue output format")
        self.batch_output_combo.addItems(OUTPUT_FORMATS)
        output_label = QtWidgets.QLabel("Output:")
        queue_opts_layout.addWidget(output_label)
        queue_opts_layout.addWidget(self.batch_output_combo)
        output_label.setBuddy(self.batch_output_combo)
        self.batch_resolution_combo = QtWidgets.QComboBox()
        self.batch_resolution_combo.setAccessibleName("Queue target resolution")
        self.batch_resolution_combo.addItems(RESOLUTIONS)
        self.batch_resolution_combo.setCurrentText("1080")
        resolution_label = QtWidgets.QLabel("Resolution:")
        queue_opts_layout.addWidget(resolution_label)
        queue_opts_layout.addWidget(self.batch_resolution_combo)
        resolution_label.setBuddy(self.batch_resolution_combo)
        self.apply_options_btn = QtWidgets.QPushButton("Apply to pending")
        self.apply_options_btn.setToolTip(
            "Stamp the options above onto every pending item. Options are set "
            "when an item is added, so this updates items already in the queue."
        )
        self.apply_options_btn.clicked.connect(self.on_apply_options)
        queue_opts_layout.addWidget(self.apply_options_btn)
        queue_opts_layout.addStretch(1)
        queue_layout.addLayout(queue_opts_layout)

        cookies_row = QtWidgets.QHBoxLayout()
        cookies_label = QtWidgets.QLabel("Cookies file:")
        cookies_label.setMinimumWidth(130)
        cookies_row.addWidget(cookies_label)
        self.batch_cookies_input = QtWidgets.QLineEdit()
        self.batch_cookies_input.setAccessibleName("Queue cookies file path")
        self.batch_cookies_input.setPlaceholderText("Optional: path to cookies.txt for auth")
        self.batch_cookies_input.setText(
            self.cookies_file_ref.get("path", "") or self.settings.value("batch/cookies", "") or ""
        )
        self.batch_cookies_input.editingFinished.connect(self._on_batch_cookies_changed)
        cookies_row.addWidget(self.batch_cookies_input)
        cookies_label.setBuddy(self.batch_cookies_input)
        browse_cookies_btn = QtWidgets.QPushButton("Browse")
        browse_cookies_btn.clicked.connect(self.on_batch_browse_cookies)
        cookies_row.addWidget(browse_cookies_btn)
        queue_layout.addLayout(cookies_row)

        sub_row = QtWidgets.QHBoxLayout()
        subtitles_label = QtWidgets.QLabel("Subtitles:")
        sub_row.addWidget(subtitles_label)
        self.batch_subtitle_combo = QtWidgets.QComboBox()
        self.batch_subtitle_combo.setAccessibleName("Queue subtitle delivery")
        for value, label in (
            ("off", "Off"), ("sidecar", "Sidecar (.srt)"),
            ("embed", "Embed"), ("both", "Both"),
        ):
            self.batch_subtitle_combo.addItem(label, value)
        sub_row.addWidget(self.batch_subtitle_combo)
        subtitles_label.setBuddy(self.batch_subtitle_combo)
        sub_row.addStretch(1)
        queue_layout.addLayout(sub_row)

        archive_row = QtWidgets.QHBoxLayout()
        self.archive_check = QtWidgets.QCheckBox("Skip already downloaded")
        self.archive_check.setAccessibleName("Queue skip already downloaded")
        self.archive_check.setChecked(
            self.settings.value("queue/archive", False, type=bool)
        )
        self.archive_check.toggled.connect(
            lambda v: self.settings.setValue("queue/archive", bool(v))
        )
        archive_row.addWidget(self.archive_check)
        self.clear_archive_btn = QtWidgets.QPushButton("Clear archive")
        self.clear_archive_btn.setToolTip(
            "Forget which videos have been downloaded, so they can be "
            "downloaded again. Only affects 'Skip already downloaded'."
        )
        self.clear_archive_btn.clicked.connect(self.on_clear_archive)
        archive_row.addWidget(self.clear_archive_btn)
        archive_row.addStretch(1)
        queue_layout.addLayout(archive_row)

        jobs_row = QtWidgets.QHBoxLayout()
        jobs_row.addWidget(QtWidgets.QLabel("Downloads at once:"))
        self.jobs_spin = QtWidgets.QSpinBox()
        self.jobs_spin.setAccessibleName("Queue concurrent downloads")
        self.jobs_spin.setRange(1, 8)
        self.jobs_spin.setValue(int(self.settings.value("queue/jobs", 3)))
        self.jobs_spin.valueChanged.connect(
            lambda v: self.settings.setValue("queue/jobs", int(v))
        )
        jobs_row.addWidget(self.jobs_spin)
        jobs_row.addStretch(1)
        queue_layout.addLayout(jobs_row)

        start_row = QtWidgets.QHBoxLayout()
        self.batch_start_btn = QtWidgets.QPushButton("Start")
        self.batch_start_btn.clicked.connect(self.on_start_queue)
        start_row.addWidget(self.batch_start_btn)
        self.pause_btn = QtWidgets.QPushButton("Pause")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self.on_pause_resume)
        start_row.addWidget(self.pause_btn)
        self.cancel_all_btn = QtWidgets.QPushButton("Cancel all")
        self.cancel_all_btn.setEnabled(False)
        self.cancel_all_btn.clicked.connect(self.on_cancel_all)
        start_row.addWidget(self.cancel_all_btn)
        queue_layout.addLayout(start_row)

        self.batch_console_log = QtWidgets.QTextEdit()
        self.batch_console_log.setReadOnly(True)
        self.batch_console_log.setMinimumHeight(120)
        self.batch_console_log.setAccessibleName("Queue activity log")
        queue_layout.addWidget(self.batch_console_log, 1)

        self._refresh_presets()

    def _refresh_presets(self):
        self._applying_preset = True
        self.batch_preset_combo.clear()
        for preset in self.preset_store.all():
            self.batch_preset_combo.addItem(preset.name, preset.name)
        self.batch_preset_combo.addItem("Custom", None)
        last = self.settings.value("preset/last", "")
        index = self.batch_preset_combo.findData(last) if last else -1
        self.batch_preset_combo.setCurrentIndex(
            index if index >= 0 else self.batch_preset_combo.count() - 1
        )
        self._applying_preset = False
        if index >= 0:
            preset = self.preset_store.get(last)
            if preset:
                self._apply_preset(preset)

    def on_preset_selected(self, _index):
        if self._applying_preset:
            return
        name = self.batch_preset_combo.currentData()
        if not name:
            return
        preset = self.preset_store.get(name)
        if preset:
            self._apply_preset(preset)

    def _apply_preset(self, preset):
        self._applying_preset = True
        index = output_index_for(preset.output)
        if index >= 0:
            self.batch_output_combo.setCurrentIndex(index)
        self.batch_resolution_combo.setCurrentText(preset.resolution)
        self.batch_save_dir_input.setText(preset.save_dir or default_download_folder())
        self.batch_cookies_input.setText(preset.cookies or "")
        self.cookies_file_ref["path"] = preset.cookies or ""
        self._applying_preset = False
        self._on_batch_save_dir_changed()
        self._on_batch_cookies_changed()

    def show_hint(self, text: str):
        self.hint_label.setText(text)
        self.hint_label.setVisible(bool(text))

    def batch_log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.batch_console_log.append(f"[{ts}] {msg}")
        sb = self.batch_console_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_batch_cookies_changed(self):
        path = self.batch_cookies_input.text().strip()
        self.cookies_file_ref["path"] = path
        self.settings.setValue("batch/cookies", path)

    def _on_batch_save_dir_changed(self):
        text = self.batch_save_dir_input.text().strip()
        if text:
            self.settings.setValue("batch/save_dir", text)

    def _batch_get_cookies_path(self):
        return self.cookies_file_ref.get("path", "").strip()

    def on_batch_browse_cookies(self):
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select cookies.txt", "", "Text files (*.txt);;All files (*)"
        )
        if file:
            self.batch_cookies_input.setText(file)
            self._on_batch_cookies_changed()
            self.batch_log(f"Cookies file set: {file}")

    def on_batch_browse(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose folder", self.batch_save_dir_input.text()
        )
        if folder:
            self.batch_save_dir_input.setText(folder)
            self._on_batch_save_dir_changed()

    def _job_options(self):
        save_dir = self.batch_save_dir_input.text().strip() or default_download_folder()
        return build_job_options(
            save_dir,
            self.batch_output_combo.currentText(),
            self.batch_resolution_combo.currentText(),
            self._batch_get_cookies_path(),
            self.batch_subtitle_combo.currentData(),
            self.settings.value("cookies/browser", "") or "",
        )

    def _queued_urls(self):
        return [job.url for job in self.queue.jobs]

    def expand_collection_url(self, url):
        """List a collection URL and offer to enqueue its videos."""
        if self._expand_worker is not None:
            self._expand_queue.append(url)
            return
        if self.queue_worker and self.queue_worker.isRunning():
            self.batch_log("Queue is running; finish or pause it first.")
            return
        self.add_urls_btn.setEnabled(False)
        self.paste_urls_btn.setEnabled(False)
        self.batch_log("Expanding %s ..." % (url,))
        cookies = self._batch_get_cookies_path()
        worker = ExpandWorker(url, cookies_file=cookies)
        worker.done_signal.connect(
            lambda result, u=url: self._on_expanded(u, result)
        )
        worker.error_signal.connect(self._on_expand_error)
        self._expand_worker = worker
        worker.start()

    def _on_expand_error(self, message):
        self._finish_expand()
        self.batch_log("Could not list the collection: %s" % message)

    def _expand_re_enable(self):
        self.add_urls_btn.setEnabled(True)
        self.paste_urls_btn.setEnabled(True)

    def _finish_expand(self):
        self._expand_worker = None
        self._expand_re_enable()
        self._expand_next()

    def _expand_next(self):
        if self._expand_worker is not None:
            return
        if not self._expand_queue:
            return
        if self.queue_worker and self.queue_worker.isRunning():
            self.batch_log("Queue is running; finish or pause it first.")
            return
        self.expand_collection_url(self._expand_queue.pop(0))

    def _on_expanded(self, url, result):
        if result.error:
            self._finish_expand()
            self.batch_log(result.error)
            return
        kept, skipped = new_entries(result.entries, self._queued_urls())
        if not kept:
            self._finish_expand()
            self.batch_log("All %d found videos are already queued." % len(result.entries))
            return
        dialog = ExpandConfirmDialog(result, skipped, self)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            self._finish_expand()
            self.batch_log("Expansion cancelled.")
            return
        chosen = dialog.chosen_limit()
        if chosen > len(result.entries):
            self.batch_log("Fetching %d entries ..." % chosen)
            self._expand_worker = ExpandWorker(
                url, cookies_file=self._batch_get_cookies_path(), limit=chosen,
            )
            self._expand_worker.done_signal.connect(
                lambda more: self._add_expanded(more, chosen)
            )
            self._expand_worker.error_signal.connect(self._on_expand_error)
            self._expand_worker.start()
            return
        self._add_expanded(result, chosen)

    def _add_expanded(self, result, chosen):
        if result.error:
            self.batch_log(result.error)
            self._finish_expand()
            return
        options = self._job_options()
        kept, _ = new_entries(result.entries[:chosen], self._queued_urls())
        for entry in kept:
            self.queue.add(entry.url, options, title=entry.title)
        self.queue.store.save()
        self.refresh_table()
        self._finish_expand()
        self.batch_log("Added %d video(s) to the queue." % len(kept))

    def _add_jobs(self, urls):
        singles = []
        collections = []
        skipped = 0
        for url in urls:
            if not looks_like_url(url):
                skipped += 1
            elif classify_url(url) == "collection":
                collections.append(url)
            else:
                singles.append(url)
        if singles:
            self.queue.add_many(singles, self._job_options())
            self.queue.store.save()
            self.refresh_table()
        if skipped:
            self.batch_log("Skipped %d line(s) that did not look like a URL." % skipped)
        self._expand_queue.extend(collections)
        self._expand_next()

    def on_add_urls(self):
        dialog = BulkPasteDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self._add_jobs(dialog.urls())

    def on_paste_urls(self):
        self._add_jobs(parse_url_lines(QtWidgets.QApplication.clipboard().text()))

    def refresh_table(self):
        self.batch_table.setRowCount(0)
        self._row_for_id = {}
        for job in self.queue.jobs:
            self._insert_job_row(job)
        self._update_empty_state()

    def _update_empty_state(self):
        self.empty_label.setGeometry(self.batch_table.viewport().rect())
        self.empty_label.setVisible(self.batch_table.rowCount() == 0)

    def eventFilter(self, obj, event):
        if obj is self.batch_table.viewport() and event.type() == QtCore.QEvent.Resize:
            self._update_empty_state()
        return super().eventFilter(obj, event)

    def _insert_job_row(self, job):
        row = self.batch_table.rowCount()
        self.batch_table.insertRow(row)
        url_item = QtWidgets.QTableWidgetItem(job.title or job.url)
        url_item.setToolTip(job.url)
        # Platform badge beside the URL so a long queue is scannable at a glance.
        url_item.setIcon(icon_for_url(job.url))
        self.batch_table.setItem(row, 0, url_item)
        status_item = QtWidgets.QTableWidgetItem(state_label(job.state))
        status_item.setForeground(state_brush(job.state))
        if job.state == "pending":
            status_item.setToolTip("Right-click the row to remove it, or click here to cancel")
        self.batch_table.setItem(row, 1, status_item)
        detail = job.message or ""
        if job.state == "pending" and not detail:
            # Options are baked in when an item is added, so show them here;
            # otherwise the only way to see them is the right-click menu.
            detail = job_options_summary(job.options)
        detail_item = QtWidgets.QTableWidgetItem(detail)
        detail_item.setToolTip(
            "Options are set when an item is added. Use 'Apply to pending' or "
            "right-click > Edit options... to change them."
        )
        self.batch_table.setItem(row, 2, detail_item)
        self._row_for_id[job.id] = row

    def _job_at_row(self, row):
        for job in self.queue.jobs:
            if self._row_for_id.get(job.id) == row:
                return job
        return None

    def on_cell_clicked(self, row, column):
        if column != 1:
            return
        job = self._job_at_row(row)
        if job is None or job.state != "pending":
            return
        if not self.queue.cancel_job(job.id):
            return
        self.queue.store.save()
        self._set_row_status(row, "cancelled", "Cancelled.")
        self.batch_log("Cancelled a pending item.")

    def on_table_context_menu(self, pos):
        """Right-click menu: remove a mistakenly added link, or cancel it."""
        index = self.batch_table.indexAt(pos)
        if not index.isValid():
            return
        job = self._job_at_row(index.row())
        if job is None:
            return

        menu = QtWidgets.QMenu(self)
        remove_action = menu.addAction("Remove from queue")
        remove_action.setEnabled(can_remove(job.state))
        cancel_this = menu.addAction("Stop this download")
        cancel_this.setEnabled(job.state == "running")
        cancel_action = menu.addAction("Cancel this item")
        cancel_action.setEnabled(job.state == "pending")
        retry_action = menu.addAction("Retry")
        retry_action.setEnabled(job.state == "failed")
        edit_action = menu.addAction("Edit options...")
        edit_action.setEnabled(job.state == "pending")

        chosen = menu.exec_(self.batch_table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is remove_action:
            self.on_remove_job(job)
        elif chosen is cancel_action:
            self.on_cell_clicked(index.row(), 1)
        elif chosen is cancel_this:
            self._cancel_running_job(job)
        elif chosen is retry_action:
            self.on_retry_job(job)
        elif chosen is edit_action:
            self.on_edit_job(job)

    def _cancel_running_job(self, job):
        if self.queue_worker and self.queue_worker.isRunning():
            self.queue_worker.cancel_job(job.id)
            self.batch_log("Cancelling this download...")

    def on_remove_selected(self):
        """Delete key: remove the highlighted row (keyboard equivalent of the
        right-click 'Remove from queue')."""
        row = self.batch_table.currentRow()
        if row < 0:
            return
        job = self._job_at_row(row)
        if job is not None:
            self.on_remove_job(job)

    def on_remove_job(self, job):
        if not self.queue.remove_job(job.id):
            self.batch_log("That item is running; cancel it first.")
            return
        self.queue.store.save()
        self.refresh_table()
        self.batch_log("Removed an item from the queue.")

    def _set_row_status(self, row, status, detail=""):
        if 0 <= row < self.batch_table.rowCount():
            item = self.batch_table.item(row, 1)
            item.setText(state_label(status))
            item.setForeground(state_brush(status))
            self.batch_table.item(row, 2).setText(detail or "")

    def _on_job(self, job_id, state, job):
        row = self._row_for_id.get(job_id)
        if row is None:
            return
        if state == "done":
            detail = os.path.basename(job.path) if job.path else (job.message or "")
        else:
            detail = job.message or ""
        self._set_row_status(row, state, detail)
        self._update_overall_progress()

    def _update_overall_progress(self):
        total = len(self.queue.jobs)
        if not total:
            self.progress_bar.setValue(0)
            return
        finished = sum(1 for j in self.queue.jobs if j.state in TERMINAL_STATES)
        self.progress_bar.setValue(int(finished / total * 100))

    def _on_progress(self, job_id, p):
        from core.progress import format_progress
        row = self._row_for_id.get(job_id)
        if row is not None:
            self._set_row_status(row, "running", format_progress(p))

    def on_start_queue(self):
        if self.queue_worker and self.queue_worker.isRunning():
            self.batch_log("Queue is already running.")
            return
        has_pending = any(j.state == "pending" for j in self.queue.jobs)
        if not has_pending:
            self.refresh_table()
            self.show_hint("Add at least one URL before starting.")
            return
        self.show_hint("")
        current = self._job_options()
        stale = sum(1 for j in self.queue.jobs
                    if j.state == "pending" and (j.options or {}) != current)
        if stale:
            self.batch_log(
                "%d pending item(s) use different options than the ones above. "
                "Use 'Apply to pending' to update them." % stale
            )
        self.queue.resume()
        self.queue.store.save()
        self.batch_start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setText("Pause")
        self.cancel_all_btn.setEnabled(True)
        self.batch_log("Starting queue...")
        self.queue_worker = QueueWorker(
            self.queue, jobs=self.jobs_spin.value(), archive=self._archive_path()
        )
        self.queue_worker.job_signal.connect(self._on_job)
        self.queue_worker.progress_signal.connect(self._on_progress)
        self.queue_worker.finished_signal.connect(self.on_queue_finished)
        self.queue_worker.start()

    def on_pause_resume(self):
        if not (self.queue_worker and self.queue_worker.isRunning()):
            return
        if self.queue.paused:
            self.queue.resume()
            self.pause_btn.setText("Pause")
            self.batch_log("Resumed. Finishing the current item first.")
        else:
            self.queue.pause()
            self.pause_btn.setText("Resume")
            self.batch_log("Paused. Finishing the current item first.")

    def on_cancel_all(self):
        if self.queue_worker and self.queue_worker.isRunning():
            self.queue_worker.cancel_all()
            self.cancel_all_btn.setEnabled(False)
            self.batch_log("Cancelling all running downloads...")

    def on_clear_archive(self):
        from core.archive import clear_archive, default_archive_path
        if QtWidgets.QMessageBox.question(
            self, "Clear archive",
            "Forget every video recorded as downloaded?\n\n"
            "They can then be downloaded again.",
        ) != QtWidgets.QMessageBox.Yes:
            return
        removed = clear_archive(default_archive_path())
        self.batch_log("Archive cleared." if removed else "Archive is already empty.")

    def _archive_path(self):
        from core.archive import default_archive_path
        return default_archive_path() if self.archive_check.isChecked() else None

    def on_apply_options(self):
        options = self._job_options()
        count = 0
        for job in self.queue.jobs:
            if job.state == "pending" and self.queue.set_options(job.id, options):
                count += 1
        if not count:
            self.batch_log("No pending items to update.")
            return
        self.queue.store.save()
        self.refresh_table()
        self.batch_log("Applied the current options to %d pending item(s)." % count)

    def on_retry_failed(self):
        count = self.queue.retry_failed()
        if not count:
            self.batch_log("No failed jobs to retry.")
            return
        self.queue.store.save()
        self.refresh_table()
        self.batch_log("Retrying %d failed job(s)." % count)

    def on_retry_job(self, job):
        if self.queue.retry_failed(job.id):
            self.queue.store.save()
            self.refresh_table()
            self.batch_log("Retrying one failed job.")

    def on_edit_job(self, job):
        from ui.dialogs import EditJobDialog
        dialog = EditJobDialog(self, job)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return
        fields = dialog.chosen()
        options = build_job_options(
            fields["save_dir"] or default_download_folder(),
            fields["output_text"], fields["resolution"],
            fields["cookies_path"], fields["subtitles"],
            (job.options or {}).get("cookies_from_browser", "") or "",
        )
        if self.queue.set_options(job.id, options):
            self.queue.store.save()
            self.refresh_table()
            self.batch_log("Updated the options for one job.")

    def on_clear_finished(self):
        if self.queue_worker and self.queue_worker.isRunning():
            self.batch_log("Cannot clear while the queue is running.")
            return
        before = len(self.queue.jobs)
        self.queue.jobs[:] = [j for j in self.queue.jobs if j.state not in TERMINAL_STATES]
        self.queue.store.save()
        self.refresh_table()
        self.batch_log(f"Cleared {before - len(self.queue.jobs)} finished item(s).")

    def on_queue_finished(self, msg: str):
        self.batch_log(msg)
        self.batch_start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("Pause")
        self.cancel_all_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.refresh_table()
