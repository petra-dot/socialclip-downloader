import datetime
import os

from PyQt5 import QtWidgets, QtCore

from utils.file_utils import default_download_folder, restore_or, OUTPUT_FORMATS, RESOLUTIONS
from utils.ui_helpers import looks_like_url
from workers.batch_worker import BatchDownloadWorker


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


class BatchTab(QtWidgets.QWidget):
    def __init__(self, cookies_file_ref):
        super().__init__()
        self.cookies_file_ref = cookies_file_ref
        self.batch_worker = None
        self._row_for_index = []
        self.settings = QtCore.QSettings()
        self.init_ui()

    def init_ui(self):
        batch_layout = QtWidgets.QVBoxLayout(self)
        batch_layout.setContentsMargins(8, 8, 8, 8)
        batch_layout.setSpacing(6)

        urls_heading = QtWidgets.QLabel("URLs")
        urls_heading.setStyleSheet("font-weight: bold; font-size: 12px;")
        batch_layout.addWidget(urls_heading)

        urls_toolbar = QtWidgets.QHBoxLayout()
        self.add_urls_btn = QtWidgets.QPushButton("Add URLs")
        self.add_urls_btn.clicked.connect(self.on_add_urls)
        urls_toolbar.addWidget(self.add_urls_btn)
        self.paste_urls_btn = QtWidgets.QPushButton("Paste")
        self.paste_urls_btn.clicked.connect(self.on_paste_urls)
        urls_toolbar.addWidget(self.paste_urls_btn)
        urls_toolbar.addStretch(1)
        batch_layout.addLayout(urls_toolbar)

        self.batch_table = QtWidgets.QTableWidget(0, 3)
        self.batch_table.setHorizontalHeaderLabels(["URL", "Status", "Detail"])
        self.batch_table.horizontalHeader().setStretchLastSection(True)
        self.batch_table.setColumnWidth(0, 340)
        self.batch_table.setColumnWidth(1, 90)
        self.batch_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.batch_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        batch_layout.addWidget(self.batch_table)

        opts_heading = QtWidgets.QLabel("Output")
        opts_heading.setStyleSheet("font-weight: bold; font-size: 12px;")
        batch_layout.addWidget(opts_heading)

        batch_save_layout = QtWidgets.QHBoxLayout()
        self.batch_save_dir_input = QtWidgets.QLineEdit(
            restore_or(default_download_folder(), self.settings.value("batch/save_dir"))
        )
        self.batch_save_dir_input.editingFinished.connect(self._on_batch_save_dir_changed)
        batch_save_layout.addWidget(self.batch_save_dir_input)
        batch_browse_btn = QtWidgets.QPushButton("Browse")
        batch_browse_btn.clicked.connect(self.on_batch_browse)
        batch_save_layout.addWidget(batch_browse_btn)
        batch_layout.addLayout(batch_save_layout)

        batch_opts_layout = QtWidgets.QHBoxLayout()
        self.batch_output_combo = QtWidgets.QComboBox()
        self.batch_output_combo.addItems(OUTPUT_FORMATS)
        batch_opts_layout.addWidget(QtWidgets.QLabel("Output:"))
        batch_opts_layout.addWidget(self.batch_output_combo)
        self.batch_resolution_combo = QtWidgets.QComboBox()
        self.batch_resolution_combo.addItems(RESOLUTIONS)
        self.batch_resolution_combo.setCurrentText("1080")
        batch_opts_layout.addWidget(QtWidgets.QLabel("Resolution:"))
        batch_opts_layout.addWidget(self.batch_resolution_combo)
        batch_layout.addLayout(batch_opts_layout)

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
        batch_layout.addLayout(cookies_row)

        start_row = QtWidgets.QHBoxLayout()
        self.batch_start_btn = QtWidgets.QPushButton("Start Batch")
        self.batch_start_btn.clicked.connect(self.on_start_batch)
        start_row.addWidget(self.batch_start_btn)
        self.batch_cancel_btn = QtWidgets.QPushButton("Cancel")
        self.batch_cancel_btn.setEnabled(False)
        self.batch_cancel_btn.clicked.connect(self.on_cancel_batch)
        start_row.addWidget(self.batch_cancel_btn)
        batch_layout.addLayout(start_row)

        self.batch_console_log = QtWidgets.QTextEdit()
        self.batch_console_log.setReadOnly(True)
        self.batch_console_log.setFixedHeight(200)
        batch_layout.addWidget(self.batch_console_log)

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

    def _append_urls(self, urls):
        valid = [u for u in urls if looks_like_url(u)]
        skipped = len(urls) - len(valid)
        for url in valid:
            row = self.batch_table.rowCount()
            self.batch_table.insertRow(row)
            self.batch_table.setItem(row, 0, QtWidgets.QTableWidgetItem(url))
            self.batch_table.setItem(row, 1, QtWidgets.QTableWidgetItem("pending"))
            self.batch_table.setItem(row, 2, QtWidgets.QTableWidgetItem(""))
        if skipped:
            self.batch_log(f"Skipped {skipped} line(s) that did not look like a URL.")

    def on_add_urls(self):
        dialog = BulkPasteDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self._append_urls(dialog.urls())

    def on_paste_urls(self):
        self._append_urls(parse_url_lines(QtWidgets.QApplication.clipboard().text()))

    def _set_row_status(self, row, status, detail=""):
        if 0 <= row < self.batch_table.rowCount():
            self.batch_table.item(row, 1).setText(status)
            self.batch_table.item(row, 2).setText(detail or "")

    def _on_item(self, index, state, result):
        row = self._row_for_index[index] if index < len(self._row_for_index) else index
        if state == "running":
            self._set_row_status(row, "running")
            self.batch_cancel_btn.setEnabled(True)
        elif state == "done":
            detail = os.path.basename(result.path) if result.path else ""
            self._set_row_status(row, "done", detail)
        elif state == "failed":
            self._set_row_status(row, "failed", result.message or "")
        elif state == "cancelled":
            self._set_row_status(row, "cancelled")

    def on_start_batch(self):
        if self.batch_worker and self.batch_worker.isRunning():
            self.batch_log("Already running a batch. Wait for it to finish.")
            return
        urls = []
        self._row_for_index = []
        for row in range(self.batch_table.rowCount()):
            url = self.batch_table.item(row, 0).text().strip()
            if url:
                urls.append(url)
                self._row_for_index.append(row)
                self._set_row_status(row, "pending")
        if not urls:
            QtWidgets.QMessageBox.warning(self, "No URLs", "Please add at least one URL.")
            return
        save_dir = self.batch_save_dir_input.text().strip() or default_download_folder()
        os.makedirs(save_dir, exist_ok=True)
        output_type = "MP3" if "MP3" in self.batch_output_combo.currentText() else "MP4"
        target_resolution = int(self.batch_resolution_combo.currentText())
        self.batch_start_btn.setEnabled(False)
        self.batch_cancel_btn.setEnabled(True)
        self.batch_log(f"Starting batch download of {len(urls)} URLs...")
        self.batch_worker = BatchDownloadWorker(
            urls, save_dir, output_type, target_resolution, self._batch_get_cookies_path()
        )
        self.batch_worker.status_signal.connect(self.batch_log)
        self.batch_worker.finished_signal.connect(self.on_batch_finished)
        self.batch_worker.item_signal.connect(self._on_item)
        self.batch_worker.start()

    def on_cancel_batch(self):
        if self.batch_worker and self.batch_worker.isRunning():
            self.batch_worker.cancel()
            self.batch_cancel_btn.setEnabled(False)
            self.batch_log("Cancelling after the current URL...")

    def on_batch_finished(self, msg: str):
        self.batch_log(msg)
        self.batch_start_btn.setEnabled(True)
        self.batch_cancel_btn.setEnabled(False)
