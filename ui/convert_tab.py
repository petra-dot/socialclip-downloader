import datetime
import os

from PyQt5 import QtWidgets, QtCore

from core import formats
from utils.file_utils import default_download_folder, RESOLUTIONS
from utils.ui_helpers import reveal_in_folder
from workers.convert_worker import ConvertFileWorker
from ui.style import make_heading


class ConvertTab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.conv_worker = None
        self._last_output = ""
        self.settings = QtCore.QSettings()
        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        file_heading = QtWidgets.QLabel("File")
        make_heading(file_heading)
        layout.addWidget(file_heading)
        file_row = QtWidgets.QHBoxLayout()
        self.file_path_input = QtWidgets.QLineEdit()
        self.file_path_input.setAccessibleName("File to convert")
        file_row.addWidget(self.file_path_input)
        pick_btn = QtWidgets.QPushButton("Select File...")
        pick_btn.clicked.connect(self.on_pick_file)
        file_row.addWidget(pick_btn)
        layout.addLayout(file_row)

        conv_heading = QtWidgets.QLabel("Convert")
        make_heading(conv_heading)
        layout.addWidget(conv_heading)
        conv_opts = QtWidgets.QHBoxLayout()
        self.conv_output_combo = QtWidgets.QComboBox()
        self.conv_output_combo.setAccessibleName("Convert to format")
        for fmt in formats.for_kind("video") + formats.for_kind("audio"):
            self.conv_output_combo.addItem(fmt.label, fmt.key)
        saved_output = self.settings.value("convert/output")
        idx = self.conv_output_combo.findData(saved_output)
        self.conv_output_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.conv_output_combo.currentIndexChanged.connect(self._on_conv_output_changed)
        conv_opts.addWidget(QtWidgets.QLabel("Convert to:"))
        conv_opts.addWidget(self.conv_output_combo)
        self.conv_res_combo = QtWidgets.QComboBox()
        self.conv_res_combo.setAccessibleName("Convert target resolution")
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
        self.open_folder_btn = QtWidgets.QPushButton("Open folder")
        self.open_folder_btn.setVisible(False)
        self.open_folder_btn.clicked.connect(self._on_open_folder)
        conv_btn_row.addWidget(self.open_folder_btn)
        layout.addLayout(conv_btn_row)

        # Inline hint for recoverable mistakes, instead of a modal popup.
        self.hint_label = QtWidgets.QLabel("")
        self.hint_label.setVisible(False)
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        self.console_log = QtWidgets.QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setMinimumHeight(120)
        self.console_log.setAccessibleName("Conversion log")
        layout.addWidget(self.console_log, 1)

    def show_hint(self, text: str):
        self.hint_label.setText(text)
        self.hint_label.setVisible(bool(text))

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
        # GIF has a fixed recipe (hardcoded scale=320); the combo must not
        # advertise a resolution it silently ignores.
        is_gif = fmt is not None and fmt.key == "gif"
        force_copy = self.copy_combo.currentData() is True
        self.conv_res_combo.setEnabled(not (is_audio or is_gif or force_copy))

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
            self.show_hint("Select a file to convert first.")
            return
        if not os.path.exists(path):
            self.show_hint("That file path does not exist.")
            return
        self.show_hint("")

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
        self.conv_worker.output_signal.connect(self._on_conv_output)
        self.conv_worker.finished_signal.connect(self.on_conv_finished)
        self.conv_worker.start()

    def _on_conv_output(self, path: str):
        self._last_output = path
        self.open_folder_btn.setVisible(bool(path))

    def _on_open_folder(self):
        reveal_in_folder(self._last_output)

    def on_conv_finished(self, msg: str):
        self.log(msg)
        self.convert_file_btn.setEnabled(True)
