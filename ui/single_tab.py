import datetime
import os
import urllib.request

from PyQt5 import QtWidgets, QtCore

from utils.file_utils import clean_title, get_uploader, make_unique_filepath, default_download_folder
from utils.ydl_opts import strip_ansi
from workers.download_worker import DownloadWorker
from sites.cookies import get_cookie_path


class SingleTab(QtWidgets.QWidget):
    def __init__(self, main_window_ref, cookies_file_ref):
        super().__init__()
        self.main_window = main_window_ref
        self.cookies_file_ref = cookies_file_ref
        self.worker = None
        self.init_ui()

    def init_ui(self):
        main = QtWidgets.QVBoxLayout(self)

        url_row = QtWidgets.QHBoxLayout()
        self.url_input = QtWidgets.QLineEdit()
        self.url_input.setPlaceholderText("Paste video URL here")
        self.url_input.textChanged.connect(self._on_url_changed)
        url_row.addWidget(self.url_input)
        self.fetch_meta_btn = QtWidgets.QPushButton("Fetch Metadata")
        self.fetch_meta_btn.clicked.connect(self.on_fetch_metadata)
        url_row.addWidget(self.fetch_meta_btn)
        main.addLayout(url_row)

        cookies_row = QtWidgets.QHBoxLayout()
        cookies_label = QtWidgets.QLabel("Cookies (YouTube):")
        cookies_label.setFixedWidth(130)
        cookies_row.addWidget(cookies_label)
        self.cookies_input = QtWidgets.QLineEdit()
        self.cookies_input.setPlaceholderText("Optional: path to cookies.txt for YouTube auth")
        self.cookies_input.textChanged.connect(self._on_cookies_changed)
        cookies_row.addWidget(self.cookies_input)
        browse_cookies_btn = QtWidgets.QPushButton("Browse...")
        browse_cookies_btn.clicked.connect(self.on_browse_cookies)
        cookies_row.addWidget(browse_cookies_btn)
        clear_cookies_btn = QtWidgets.QPushButton("Clear")
        clear_cookies_btn.setFixedWidth(50)
        clear_cookies_btn.clicked.connect(lambda: self.cookies_input.clear())
        cookies_row.addWidget(clear_cookies_btn)
        main.addLayout(cookies_row)

        save_layout = QtWidgets.QHBoxLayout()
        self.save_dir_input = QtWidgets.QLineEdit(default_download_folder())
        save_layout.addWidget(self.save_dir_input)
        browse_btn = QtWidgets.QPushButton("Browse")
        browse_btn.clicked.connect(self.on_browse)
        save_layout.addWidget(browse_btn)
        main.addLayout(save_layout)

        meta_layout = QtWidgets.QHBoxLayout()
        self.thumbnail_label = QtWidgets.QLabel("No preview")
        self.thumbnail_label.setFixedSize(160, 90)
        self.thumbnail_label.setAlignment(QtCore.Qt.AlignCenter)
        meta_layout.addWidget(self.thumbnail_label)
        meta_right = QtWidgets.QVBoxLayout()
        self.meta_title = QtWidgets.QLabel("Title: \u2014")
        self.meta_uploader = QtWidgets.QLabel("Uploader: \u2014")
        self.meta_duration = QtWidgets.QLabel("Duration: \u2014")
        self.meta_platform = QtWidgets.QLabel("Platform: \u2014")
        meta_right.addWidget(self.meta_title)
        meta_right.addWidget(self.meta_uploader)
        meta_right.addWidget(self.meta_duration)
        meta_right.addWidget(self.meta_platform)
        meta_layout.addLayout(meta_right)
        main.addLayout(meta_layout)

        opts_layout = QtWidgets.QHBoxLayout()
        self.output_combo = QtWidgets.QComboBox()
        self.output_combo.addItems(["Video (MP4)", "Audio (MP3)"])
        opts_layout.addWidget(QtWidgets.QLabel("Output:"))
        opts_layout.addWidget(self.output_combo)
        self.convert_checkbox = QtWidgets.QCheckBox("Convert to chosen resolution?")
        opts_layout.addWidget(self.convert_checkbox)
        self.resolution_combo = QtWidgets.QComboBox()
        self.resolution_combo.addItems(["720", "1080", "1440", "2160"])
        self.resolution_combo.setCurrentText("1080")
        opts_layout.addWidget(QtWidgets.QLabel("Resolution:"))
        opts_layout.addWidget(self.resolution_combo)
        main.addLayout(opts_layout)

        rename_row = QtWidgets.QHBoxLayout()
        self.checkbox_timestamp = QtWidgets.QCheckBox("Add timestamp to filename")
        self.checkbox_channel = QtWidgets.QCheckBox("Add channel/uploader to filename")
        rename_row.addWidget(self.checkbox_channel)
        rename_row.addWidget(self.checkbox_timestamp)
        main.addLayout(rename_row)

        dl_row = QtWidgets.QHBoxLayout()
        self.download_btn = QtWidgets.QPushButton("Download")
        self.download_btn.clicked.connect(self.on_download)
        dl_row.addWidget(self.download_btn)
        main.addLayout(dl_row)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        main.addWidget(self.progress_bar)

        self.console_log = QtWidgets.QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setFixedHeight(200)
        main.addWidget(self.console_log)

    def log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.console_log.append(f"[{ts}] {msg}")
        sb = self.console_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_cookies_changed(self, text):
        self.cookies_file_ref["path"] = text.strip()

    def _on_url_changed(self):
        self.thumbnail_label.clear()
        self.thumbnail_label.setText("No preview")
        self.meta_title.setText("Title: \u2014")
        self.meta_uploader.setText("Uploader: \u2014")
        self.meta_duration.setText("Duration: \u2014")
        self.meta_platform.setText("Platform: \u2014")

    def on_browse_cookies(self):
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select cookies.txt",
            os.path.expanduser("~"),
            "Text files (*.txt);;All files (*)",
        )
        if file:
            self.cookies_input.setText(file)
            self.log(f"Cookies file set: {file}")

    def _get_ydl_base_opts(self):
        opts = {
            "skip_download": True,
            "noplaylist": True,
            "age_limit": 99,
            "no_color": True,
        }
        cf = self.cookies_file_ref.get("path", "").strip()
        if cf and os.path.isfile(cf):
            opts["cookiefile"] = cf
        return opts

    def on_browse(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose folder", self.save_dir_input.text()
        )
        if folder:
            self.save_dir_input.setText(folder)

    def on_fetch_metadata(self):
        from yt_dlp import YoutubeDL
        url = self.url_input.text().strip()
        if not url:
            QtWidgets.QMessageBox.warning(self, "No URL", "Please paste a URL first.")
            return
        try:
            auto_cookie = get_cookie_path(url)
            if auto_cookie:
                self.cookies_input.setText(auto_cookie)
                self.cookies_file_ref["path"] = auto_cookie
            self.log("Fetching metadata...")
            self.fetch_meta_btn.setEnabled(False)
            ydl_opts = self._get_ydl_base_opts()
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                self.log("Could not fetch metadata. The video may be private or unavailable.")
                self.fetch_meta_btn.setEnabled(True)
                return
            title = info.get("title") or info.get("id") or "video"
            uploader = get_uploader(info) or "\u2014"
            self.meta_title.setText(f"Title: {title}")
            self.meta_uploader.setText(f"Uploader: {uploader}")
            try:
                thumbnail_url = info.get("thumbnail")
                if thumbnail_url:
                    with urllib.request.urlopen(thumbnail_url) as response:
                        data = response.read()
                    pixmap = QtWidgets.QPixmap()
                    pixmap.loadFromData(data)
                    scaled_pixmap = pixmap.scaled(
                        160, 90, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
                    )
                    self.thumbnail_label.setPixmap(scaled_pixmap)
                else:
                    self.thumbnail_label.setText("No thumbnail")
            except Exception:
                self.thumbnail_label.setText("Failed to load")
            duration = info.get("duration")
            if duration:
                if duration >= 3600:
                    hours = duration // 3600
                    minutes = (duration % 3600) // 60
                    seconds = duration % 60
                    duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    minutes = duration // 60
                    seconds = duration % 60
                    duration_str = f"{minutes:02d}:{seconds:02d}"
                self.meta_duration.setText(f"Duration: {duration_str}")
            else:
                self.meta_duration.setText("Duration: \u2014")
            platform = info.get("extractor") or info.get("webpage_url_domain") or "Unknown"
            self.meta_platform.setText(f"Platform: {platform}")
            self.log("Metadata fetched.")
            self.fetch_meta_btn.setEnabled(True)
        except Exception as e:
            self.fetch_meta_btn.setEnabled(True)
            error_msg = strip_ansi(str(e))
            if any(k in error_msg for k in ["Sign in to confirm", "bot", "cookies", "reloaded", "reload", "page needs"]):
                self.log("YouTube blocked the request. Load a cookies.txt file in the Cookies field and try again.")
            elif "Requested format" in error_msg:
                self.log("Could not find a downloadable format. The video may be unavailable or region-locked.")
            else:
                self.log(f"Metadata fetch failed: {error_msg}")

    def on_download(self):
        from yt_dlp import YoutubeDL
        url = self.url_input.text().strip()
        if not url:
            QtWidgets.QMessageBox.warning(self, "No URL", "Please paste a URL first.")
            return
        save_dir = self.save_dir_input.text().strip() or default_download_folder()
        os.makedirs(save_dir, exist_ok=True)

        try:
            self.log("Preparing download (fetching metadata)...")
            with YoutubeDL(self._get_ydl_base_opts()) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            error_msg = strip_ansi(str(e))
            if any(k in error_msg for k in ["Sign in to confirm", "bot", "cookies", "reloaded", "reload", "page needs"]):
                self.log("YouTube blocked the request. Load a cookies.txt file in the Cookies field and try again.")
            elif "Requested format" in error_msg:
                self.log("Could not find a downloadable format. The video may be unavailable or region-locked.")
            else:
                self.log(f"Failed to fetch metadata: {error_msg}")
            return

        title = info.get("title") or info.get("id") or "video"
        uploader = get_uploader(info) or ""
        vid_id = info.get("id") or ""

        base_filename = clean_title(title)
        if self.checkbox_channel.isChecked() and uploader:
            base_filename += "_" + clean_title(uploader)
        if self.checkbox_timestamp.isChecked():
            base_filename += "_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        temp_outtmpl = os.path.join(save_dir, base_filename + ".%(ext)s")
        tmp_opts = self._get_ydl_base_opts()
        tmp_opts["outtmpl"] = temp_outtmpl
        with YoutubeDL(tmp_opts) as ydl_tmp:
            predicted = ydl_tmp.prepare_filename(info)
        pred_dir, pred_name = os.path.split(predicted)
        pred_base, pred_ext = os.path.splitext(pred_name)
        ext = pred_ext.lstrip(".") or "mp4"

        final_path = make_unique_filepath(save_dir, base_filename, ext, fallback_id=vid_id)
        final_base = os.path.splitext(os.path.basename(final_path))[0]
        final_outtmpl = os.path.join(save_dir, final_base + ".%(ext)s")

        output_type = "MP3" if "MP3" in self.output_combo.currentText() else "MP4"
        convert = self.convert_checkbox.isChecked() and (output_type == "MP4")
        target_resolution = int(self.resolution_combo.currentText())

        auto_cookie = get_cookie_path(url)
        if auto_cookie and not self.cookies_file_ref.get("path", ""):
            self.cookies_file_ref["path"] = auto_cookie
            self.log(f"Auto-detected cookies: {auto_cookie}")

        self.download_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.log(f"Downloading as: {final_base} (NLE-safe H.264/AAC MP4).")
        self.worker = DownloadWorker(
            url, final_outtmpl, convert, target_resolution, output_type,
            cookies_file=self.cookies_file_ref.get("path", "") or None,
        )
        self.worker.status_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.finished_signal.connect(self.on_worker_finished)
        self.worker.start()

    def on_worker_finished(self, msg: str):
        self.log(msg)
        self.download_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
