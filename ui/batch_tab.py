import datetime
import os

from PyQt5 import QtWidgets

from utils.file_utils import default_download_folder
from workers.batch_worker import BatchDownloadWorker


class BatchTab(QtWidgets.QWidget):
    def __init__(self, cookies_file_ref):
        super().__init__()
        self.cookies_file_ref = cookies_file_ref
        self.batch_worker = None
        self.init_ui()

    def init_ui(self):
        batch_layout = QtWidgets.QVBoxLayout(self)
        batch_layout.setContentsMargins(8, 8, 8, 8)
        batch_layout.setSpacing(6)

        urls_heading = QtWidgets.QLabel("URLs")
        urls_heading.setStyleSheet("font-weight: bold; font-size: 12px;")
        batch_layout.addWidget(urls_heading)
        self.batch_urls_text = QtWidgets.QTextEdit()
        self.batch_urls_text.setPlaceholderText("Paste one URL per line")
        batch_layout.addWidget(self.batch_urls_text)

        opts_heading = QtWidgets.QLabel("Output")
        opts_heading.setStyleSheet("font-weight: bold; font-size: 12px;")
        batch_layout.addWidget(opts_heading)

        batch_save_layout = QtWidgets.QHBoxLayout()
        self.batch_save_dir_input = QtWidgets.QLineEdit(default_download_folder())
        batch_save_layout.addWidget(self.batch_save_dir_input)
        batch_browse_btn = QtWidgets.QPushButton("Browse")
        batch_browse_btn.clicked.connect(self.on_batch_browse)
        batch_save_layout.addWidget(batch_browse_btn)
        batch_layout.addLayout(batch_save_layout)

        batch_opts_layout = QtWidgets.QHBoxLayout()
        self.batch_output_combo = QtWidgets.QComboBox()
        self.batch_output_combo.addItems(["Video (MP4)", "Audio (MP3)"])
        batch_opts_layout.addWidget(QtWidgets.QLabel("Output:"))
        batch_opts_layout.addWidget(self.batch_output_combo)
        self.batch_resolution_combo = QtWidgets.QComboBox()
        self.batch_resolution_combo.addItems(["720", "1080", "1440", "2160"])
        self.batch_resolution_combo.setCurrentText("1080")
        batch_opts_layout.addWidget(QtWidgets.QLabel("Resolution:"))
        batch_opts_layout.addWidget(self.batch_resolution_combo)
        batch_layout.addLayout(batch_opts_layout)

        self.batch_start_btn = QtWidgets.QPushButton("Start Batch")
        self.batch_start_btn.clicked.connect(self.on_start_batch)
        batch_layout.addWidget(self.batch_start_btn)

        self.batch_console_log = QtWidgets.QTextEdit()
        self.batch_console_log.setReadOnly(True)
        self.batch_console_log.setFixedHeight(200)
        batch_layout.addWidget(self.batch_console_log)

    def batch_log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.batch_console_log.append(f"[{ts}] {msg}")
        sb = self.batch_console_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def on_batch_browse(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose folder", self.batch_save_dir_input.text()
        )
        if folder:
            self.batch_save_dir_input.setText(folder)

    def on_start_batch(self):
        urls_text = self.batch_urls_text.toPlainText()
        urls = [line.strip() for line in urls_text.split("\n") if line.strip()]
        if not urls:
            QtWidgets.QMessageBox.warning(self, "No URLs", "Please paste at least one URL.")
            return
        save_dir = self.batch_save_dir_input.text().strip() or default_download_folder()
        os.makedirs(save_dir, exist_ok=True)
        output_type = "MP3" if "MP3" in self.batch_output_combo.currentText() else "MP4"
        target_resolution = int(self.batch_resolution_combo.currentText())
        self.batch_start_btn.setEnabled(False)
        self.batch_log(f"Starting batch download of {len(urls)} URLs...")
        self.batch_worker = BatchDownloadWorker(
            urls, save_dir, output_type, target_resolution, self.cookies_file_ref.get("path", "")
        )
        self.batch_worker.status_signal.connect(self.batch_log)
        self.batch_worker.finished_signal.connect(self.on_batch_finished)
        self.batch_worker.start()

    def on_batch_finished(self, msg: str):
        self.batch_log(msg)
        self.batch_start_btn.setEnabled(True)
