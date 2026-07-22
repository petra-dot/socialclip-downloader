import datetime
import os

from PyQt5 import QtWidgets

from utils.file_utils import default_download_folder
from workers.convert_worker import ConvertFileWorker


class ConvertTab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.conv_worker = None
        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("Convert existing file (select file below)"))

        card = QtWidgets.QFrame()
        card.setObjectName("card")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(8)
        file_layout = QtWidgets.QHBoxLayout()
        self.file_path_input = QtWidgets.QLineEdit()
        file_layout.addWidget(self.file_path_input)
        pick_btn = QtWidgets.QPushButton("Select File...")
        pick_btn.clicked.connect(self.on_pick_file)
        file_layout.addWidget(pick_btn)
        card_layout.addLayout(file_layout)
        layout.addWidget(card)

        card = QtWidgets.QFrame()
        card.setObjectName("card")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(8)
        conv_opts = QtWidgets.QHBoxLayout()
        self.conv_output_combo = QtWidgets.QComboBox()
        self.conv_output_combo.addItems(["MP4 (Video)", "MP3 (Audio)", "WAV (Audio)"])
        conv_opts.addWidget(QtWidgets.QLabel("Convert to:"))
        conv_opts.addWidget(self.conv_output_combo)
        self.conv_res_combo = QtWidgets.QComboBox()
        self.conv_res_combo.addItems(["720", "1080", "1440", "2160"])
        self.conv_res_combo.setCurrentText("1080")
        conv_opts.addWidget(QtWidgets.QLabel("Resolution (for video):"))
        conv_opts.addWidget(self.conv_res_combo)
        card_layout.addLayout(conv_opts)
        conv_btn_row = QtWidgets.QHBoxLayout()
        self.convert_file_btn = QtWidgets.QPushButton("Convert Selected File")
        self.convert_file_btn.setObjectName("primaryBtn")
        self.convert_file_btn.clicked.connect(self.on_convert_file)
        conv_btn_row.addWidget(self.convert_file_btn)
        card_layout.addLayout(conv_btn_row)
        layout.addWidget(card)

        self.console_log = QtWidgets.QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setFixedHeight(150)
        self.console_log.setObjectName("console")
        layout.addWidget(self.console_log)

    def log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.console_log.append(f"[{ts}] {msg}")
        sb = self.console_log.verticalScrollBar()
        sb.setValue(sb.maximum())

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
        path = self.file_path_input.text().strip()
        if not path:
            QtWidgets.QMessageBox.warning(self, "No file", "Please select a file to convert.")
            return
        if not os.path.exists(path):
            QtWidgets.QMessageBox.warning(self, "Missing", "Selected file path does not exist.")
            return

        out_sel = self.conv_output_combo.currentText()
        if "MP4" in out_sel:
            out_type = "MP4"
        elif "MP3" in out_sel:
            out_type = "MP3"
        else:
            out_type = "WAV"
        target_res = int(self.conv_res_combo.currentText())

        self.convert_file_btn.setEnabled(False)
        self.conv_worker = ConvertFileWorker(
            path, out_type, target_resolution=target_res if out_type == "MP4" else None
        )
        self.conv_worker.status_signal.connect(self.log)
        self.conv_worker.finished_signal.connect(self.on_conv_finished)
        self.conv_worker.start()

    def on_conv_finished(self, msg: str):
        self.log(msg)
        self.convert_file_btn.setEnabled(True)
