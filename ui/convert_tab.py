import datetime
import os

from PyQt5 import QtWidgets, QtCore

from core import formats
from utils.file_utils import default_download_folder, RESOLUTIONS
from workers.convert_worker import ConvertFileWorker


class ConvertTab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.conv_worker = None
        self.settings = QtCore.QSettings()
        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        file_heading = QtWidgets.QLabel("File")
        file_heading.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(file_heading)
        file_row = QtWidgets.QHBoxLayout()
        self.file_path_input = QtWidgets.QLineEdit()
        file_row.addWidget(self.file_path_input)
        pick_btn = QtWidgets.QPushButton("Select File...")
        pick_btn.clicked.connect(self.on_pick_file)
        file_row.addWidget(pick_btn)
        layout.addLayout(file_row)

        conv_heading = QtWidgets.QLabel("Convert")
        conv_heading.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(conv_heading)
        conv_opts = QtWidgets.QHBoxLayout()
        self.conv_output_combo = QtWidgets.QComboBox()
        for fmt in formats.for_kind("video") + formats.for_kind("audio"):
            self.conv_output_combo.addItem(fmt.label, fmt.key)
        saved_output = self.settings.value("convert/output")
        idx = self.conv_output_combo.findData(saved_output)
        self.conv_output_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.conv_output_combo.currentIndexChanged.connect(self._on_conv_output_changed)
        conv_opts.addWidget(QtWidgets.QLabel("Convert to:"))
        conv_opts.addWidget(self.conv_output_combo)
        self.conv_res_combo = QtWidgets.QComboBox()
        self.conv_res_combo.addItems(RESOLUTIONS)
        saved_res = self.settings.value("convert/resolution")
        self.conv_res_combo.setCurrentText(saved_res if saved_res in RESOLUTIONS else "1080")
        self.conv_res_combo.currentTextChanged.connect(self._on_conv_res_changed)
        conv_opts.addWidget(QtWidgets.QLabel("Resolution (for video):"))
        conv_opts.addWidget(self.conv_res_combo)
        self.copy_combo = QtWidgets.QComboBox()
        self.copy_combo.addItem("Auto", None)
        self.copy_combo.addItem("Copy streams", True)
        self.copy_combo.addItem("Re-encode", False)
        self.copy_combo.currentIndexChanged.connect(self._on_conv_copy_changed)
        conv_opts.addWidget(QtWidgets.QLabel("Streams:"))
        conv_opts.addWidget(self.copy_combo)
        self._update_conv_controls()
        layout.addLayout(conv_opts)
        conv_btn_row = QtWidgets.QHBoxLayout()
        self.convert_file_btn = QtWidgets.QPushButton("Convert Selected File")
        self.convert_file_btn.clicked.connect(self.on_convert_file)
        conv_btn_row.addWidget(self.convert_file_btn)
        layout.addLayout(conv_btn_row)

        self.console_log = QtWidgets.QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setFixedHeight(150)
        layout.addWidget(self.console_log)

    def log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.console_log.append(f"[{ts}] {msg}")
        sb = self.console_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_conv_output_changed(self, _index):
        key = self.conv_output_combo.currentData()
        if key:
            self.settings.setValue("convert/output", key)
        self._update_conv_controls()

    def _on_conv_copy_changed(self, _index):
        self._update_conv_controls()

    def _update_conv_controls(self):
        fmt = formats.get(self.conv_output_combo.currentData())
        is_audio = fmt is not None and fmt.kind == "audio"
        force_copy = self.copy_combo.currentData() is True
        self.conv_res_combo.setEnabled(not (is_audio or force_copy))

    def _on_conv_res_changed(self, text):
        self.settings.setValue("convert/resolution", text)

    def on_pick_file(self):
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select media file",
            self.file_path_input.text() or default_download_folder(),
        )
        if file:
            self.file_path_input.setText(file)
            self.log(f"Selected file: {file}")

    def on_convert_file(self):
        if self.conv_worker and self.conv_worker.isRunning():
            self.log("Already converting. Wait for current conversion to finish.")
            return
        path = self.file_path_input.text().strip()
        if not path:
            QtWidgets.QMessageBox.warning(self, "No file", "Please select a file to convert.")
            return
        if not os.path.exists(path):
            QtWidgets.QMessageBox.warning(self, "Missing", "Selected file path does not exist.")
            return

        out_key = self.conv_output_combo.currentData()
        copy_streams = self.copy_combo.currentData()
        target_res = (
            int(self.conv_res_combo.currentText())
            if self.conv_res_combo.isEnabled()
            else None
        )

        self.convert_file_btn.setEnabled(False)
        self.conv_worker = ConvertFileWorker(
            path, target_format=out_key, copy_streams=copy_streams,
            target_resolution=target_res,
        )
        self.conv_worker.status_signal.connect(self.log)
        self.conv_worker.finished_signal.connect(self.on_conv_finished)
        self.conv_worker.start()

    def on_conv_finished(self, msg: str):
        self.log(msg)
        self.convert_file_btn.setEnabled(True)
