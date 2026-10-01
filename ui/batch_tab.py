import datetime
import os

from PyQt5 import QtWidgets, QtCore

from core.queue import Queue, QueueStore, TERMINAL_STATES
from sites.cookies import default_cookie_dir
from utils.file_utils import default_download_folder, restore_or, OUTPUT_FORMATS, RESOLUTIONS
from utils.ui_helpers import looks_like_url
from workers.queue_worker import QueueWorker


def _queue_path() -> str:
    """Queue file shared with the CLI (see cli.py:_queue_path)."""
    override = os.environ.get("SOCIALCLIP_QUEUE")
    if override:
        return override
    return os.path.join(default_cookie_dir(), "queue.json")


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
        self._row_for_id = {}
        self._running_id = ""
        self.settings = QtCore.QSettings()
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
        urls_heading.setStyleSheet("font-weight: bold; font-size: 12px;")
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
        urls_toolbar.addStretch(1)
        queue_layout.addLayout(urls_toolbar)

        self.batch_table = QtWidgets.QTableWidget(0, 3)
        self.batch_table.setHorizontalHeaderLabels(["URL", "Status", "Detail"])
        self.batch_table.horizontalHeader().setStretchLastSection(True)
        self.batch_table.setColumnWidth(0, 340)
        self.batch_table.setColumnWidth(1, 90)
        self.batch_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.batch_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        queue_layout.addWidget(self.batch_table)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        queue_layout.addWidget(self.progress_bar)

        opts_heading = QtWidgets.QLabel("Output")
        opts_heading.setStyleSheet("font-weight: bold; font-size: 12px;")
        queue_layout.addWidget(opts_heading)

        queue_save_layout = QtWidgets.QHBoxLayout()
        self.batch_save_dir_input = QtWidgets.QLineEdit(
            restore_or(default_download_folder(), self.settings.value("batch/save_dir"))
        )
        self.batch_save_dir_input.editingFinished.connect(self._on_batch_save_dir_changed)
        queue_save_layout.addWidget(self.batch_save_dir_input)
        batch_browse_btn = QtWidgets.QPushButton("Browse")
        batch_browse_btn.clicked.connect(self.on_batch_browse)
        queue_save_layout.addWidget(batch_browse_btn)
        queue_layout.addLayout(queue_save_layout)

        queue_opts_layout = QtWidgets.QHBoxLayout()
        self.batch_output_combo = QtWidgets.QComboBox()
        self.batch_output_combo.addItems(OUTPUT_FORMATS)
        queue_opts_layout.addWidget(QtWidgets.QLabel("Output:"))
        queue_opts_layout.addWidget(self.batch_output_combo)
        self.batch_resolution_combo = QtWidgets.QComboBox()
        self.batch_resolution_combo.addItems(RESOLUTIONS)
        self.batch_resolution_combo.setCurrentText("1080")
        queue_opts_layout.addWidget(QtWidgets.QLabel("Resolution:"))
        queue_opts_layout.addWidget(self.batch_resolution_combo)
        queue_layout.addLayout(queue_opts_layout)

        cookies_row = QtWidgets.QHBoxLayout()
        cookies_label = QtWidgets.QLabel("Cookies file:")
        cookies_label.setFixedWidth(130)
        cookies_row.addWidget(cookies_label)
        self.batch_cookies_input = QtWidgets.QLineEdit()
        self.batch_cookies_input.setPlaceholderText("Optional: path to cookies.txt for auth")
        self.batch_cookies_input.setText(
            self.cookies_file_ref.get("path", "") or self.settings.value("batch/cookies", "") or ""
        )
        self.batch_cookies_input.editingFinished.connect(self._on_batch_cookies_changed)
        cookies_row.addWidget(self.batch_cookies_input)
        browse_cookies_btn = QtWidgets.QPushButton("Browse...")
        browse_cookies_btn.clicked.connect(self.on_batch_browse_cookies)
        cookies_row.addWidget(browse_cookies_btn)
        queue_layout.addLayout(cookies_row)

        start_row = QtWidgets.QHBoxLayout()
        self.batch_start_btn = QtWidgets.QPushButton("Start")
        self.batch_start_btn.clicked.connect(self.on_start_queue)
        start_row.addWidget(self.batch_start_btn)
        self.pause_btn = QtWidgets.QPushButton("Pause")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self.on_pause_resume)
        start_row.addWidget(self.pause_btn)
        self.cancel_current_btn = QtWidgets.QPushButton("Cancel current")
        self.cancel_current_btn.setEnabled(False)
        self.cancel_current_btn.clicked.connect(self.on_cancel_current)
        start_row.addWidget(self.cancel_current_btn)
        queue_layout.addLayout(start_row)

        self.batch_console_log = QtWidgets.QTextEdit()
        self.batch_console_log.setReadOnly(True)
        self.batch_console_log.setFixedHeight(200)
        queue_layout.addWidget(self.batch_console_log)

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
        output_type = "MP3" if "MP3" in self.batch_output_combo.currentText() else "MP4"
        return {
            "output_dir": save_dir,
            "outtmpl": os.path.join(save_dir, "%(title)s.%(ext)s"),
            "output_type": output_type,
            "convert": output_type == "MP4",
            "target_resolution": int(self.batch_resolution_combo.currentText()),
            "cookies_file": self._batch_get_cookies_path(),
        }

    def _add_jobs(self, urls):
        valid = [u for u in urls if looks_like_url(u)]
        skipped = len(urls) - len(valid)
        if valid:
            self.queue.add_many(valid, self._job_options())
            self.queue.store.save()
            self.refresh_table()
        if skipped:
            self.batch_log(f"Skipped {skipped} line(s) that did not look like a URL.")

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

    def _insert_job_row(self, job):
        row = self.batch_table.rowCount()
        self.batch_table.insertRow(row)
        self.batch_table.setItem(row, 0, QtWidgets.QTableWidgetItem(job.url))
        self.batch_table.setItem(row, 1, QtWidgets.QTableWidgetItem(job.state))
        self.batch_table.setItem(row, 2, QtWidgets.QTableWidgetItem(job.message or ""))
        self._row_for_id[job.id] = row

    def _set_row_status(self, row, status, detail=""):
        if 0 <= row < self.batch_table.rowCount():
            self.batch_table.item(row, 1).setText(status)
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
        if state == "running":
            self._running_id = job_id
            self.progress_bar.setValue(0)
            self.cancel_current_btn.setEnabled(True)
        elif state in TERMINAL_STATES:
            if job_id == self._running_id:
                self._running_id = ""
                self.progress_bar.setValue(0)
                self.cancel_current_btn.setEnabled(False)

    def _on_progress(self, percent):
        self.progress_bar.setValue(int(percent))

    def on_start_queue(self):
        if self.queue_worker and self.queue_worker.isRunning():
            self.batch_log("Queue is already running.")
            return
        self.queue.resume()
        self.queue.store.save()
        has_pending = any(j.state == "pending" for j in self.queue.jobs)
        if not has_pending:
            self.refresh_table()
            QtWidgets.QMessageBox.warning(
                self, "Nothing to do", "Add at least one URL before starting."
            )
            return
        self.batch_start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setText("Pause")
        self.cancel_current_btn.setEnabled(True)
        self.batch_log("Starting queue...")
        self.queue_worker = QueueWorker(self.queue)
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

    def on_cancel_current(self):
        if self.queue_worker and self.queue_worker.isRunning():
            self.queue_worker.cancel_current()
            self.cancel_current_btn.setEnabled(False)
            self.batch_log("Cancelling the current item...")

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
        self.cancel_current_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.refresh_table()
