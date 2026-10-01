import datetime
import os
import urllib.request

from PyQt5 import QtWidgets, QtCore
from yt_dlp import YoutubeDL

from utils.file_utils import (
    clean_title,
    get_uploader,
    make_unique_filepath,
    default_download_folder,
    restore_or,
    OUTPUT_FORMATS,
    RESOLUTIONS,
)
from utils.ydl_opts import strip_ansi
from workers.download_worker import DownloadWorker
from sites.cookies import get_cookie_path, detect_platform, get_cookie_message
from sites.errors import classify_error


PLACEHOLDER = "-"


class FetchWorker(QtCore.QThread):
    finished_signal = QtCore.pyqtSignal(object, int)
    error_signal = QtCore.pyqtSignal(str, int)

    def __init__(self, url, cookies_path=None, seq=0):
        super().__init__()
        self.url = url
        self.cookies_path = cookies_path
        self.seq = seq

    def run(self):
        opts = {
            "skip_download": True,
            "noplaylist": True,
            "age_limit": 99,
            "no_color": True,
        }
        if self.cookies_path and os.path.isfile(self.cookies_path):
            opts["cookiefile"] = self.cookies_path
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            self.finished_signal.emit(info, self.seq)
        except Exception as e:
            self.error_signal.emit(strip_ansi(str(e)), self.seq)


class ThumbnailWorker(QtCore.QThread):
    done_signal = QtCore.pyqtSignal(object, int)

    def __init__(self, thumbnail_url, seq=0):
        super().__init__()
        self.thumbnail_url = thumbnail_url
        self.seq = seq

    def run(self):
        try:
            with urllib.request.urlopen(self.thumbnail_url, timeout=10) as response:
                data = response.read()
            pixmap = QtWidgets.QPixmap()
            pixmap.loadFromData(data)
            # Scale in device pixels so the thumbnail is 120x68 layout pixels
            # regardless of display scaling (otherwise it shrinks under HiDPI).
            dpr = QtWidgets.QApplication.desktop().devicePixelRatio()
            scaled = pixmap.scaled(
                int(120 * dpr),
                int(68 * dpr),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(dpr)
            self.done_signal.emit(scaled, self.seq)
        except Exception:
            self.done_signal.emit(None, self.seq)


class SingleTab(QtWidgets.QWidget):
    def __init__(self, cookies_file_ref):
        super().__init__()
        self.cookies_file_ref = cookies_file_ref
        self.worker = None
        self.fetch_worker = None
        self.thumb_worker = None
        self._cached_info = None
        self._fetch_url = ""
        self._fetch_seq = 0
        self._thumb_seq = 0
        self.settings = QtCore.QSettings()
        self.init_ui()

    def init_ui(self):
        main = QtWidgets.QVBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(6)

        # URL row
        url_row = QtWidgets.QHBoxLayout()
        self.url_input = QtWidgets.QLineEdit()
        self.url_input.setPlaceholderText("Paste video URL here")
        self.url_input.editingFinished.connect(self._on_url_changed)
        url_row.addWidget(self.url_input)
        self.fetch_meta_btn = QtWidgets.QPushButton("Fetch")
        self.fetch_meta_btn.clicked.connect(self.on_fetch_metadata)
        url_row.addWidget(self.fetch_meta_btn)
        main.addLayout(url_row)

        # --- Video Info (hidden until fetch) ---
        self.info_section = QtWidgets.QWidget()
        info_section_layout = QtWidgets.QVBoxLayout(self.info_section)
        info_section_layout.setContentsMargins(0, 0, 0, 0)
        info_section_layout.setSpacing(4)

        info_heading = QtWidgets.QLabel("Video Info")
        info_heading.setStyleSheet("font-weight: bold; font-size: 12px;")
        info_section_layout.addWidget(info_heading)

        meta_layout = QtWidgets.QHBoxLayout()
        self.thumbnail_label = QtWidgets.QLabel("No preview")
        self.thumbnail_label.setFixedSize(120, 68)
        self.thumbnail_label.setAlignment(QtCore.Qt.AlignCenter)
        meta_layout.addWidget(self.thumbnail_label)
        meta_right = QtWidgets.QVBoxLayout()
        self.meta_title = QtWidgets.QLabel(f"Title: {PLACEHOLDER}")
        self.meta_uploader = QtWidgets.QLabel(f"Uploader: {PLACEHOLDER}")
        self.meta_duration = QtWidgets.QLabel(f"Duration: {PLACEHOLDER}")
        self.meta_platform = QtWidgets.QLabel(f"Platform: {PLACEHOLDER}")
        meta_right.addWidget(self.meta_title)
        meta_right.addWidget(self.meta_uploader)
        meta_right.addWidget(self.meta_duration)
        meta_right.addWidget(self.meta_platform)
        meta_layout.addLayout(meta_right)
        info_section_layout.addLayout(meta_layout)

        self.info_section.setVisible(False)
        main.addWidget(self.info_section)

        # --- Output ---
        output_heading = QtWidgets.QLabel("Output")
        output_heading.setStyleSheet("font-weight: bold; font-size: 12px;")
        main.addWidget(output_heading)

        fmt_row = QtWidgets.QHBoxLayout()
        self.output_combo = QtWidgets.QComboBox()
        self.output_combo.addItems(OUTPUT_FORMATS)
        fmt_row.addWidget(QtWidgets.QLabel("Format:"))
        fmt_row.addWidget(self.output_combo)
        fmt_row.addSpacing(12)
        self.resolution_combo = QtWidgets.QComboBox()
        self.resolution_combo.addItems(RESOLUTIONS)
        self.resolution_combo.setCurrentText("1080")
        fmt_row.addWidget(QtWidgets.QLabel("Resolution:"))
        fmt_row.addWidget(self.resolution_combo)
        fmt_row.addStretch()
        main.addLayout(fmt_row)

        self.convert_checkbox = QtWidgets.QCheckBox("Convert to chosen resolution")
        main.addWidget(self.convert_checkbox)
        self.checkbox_channel = QtWidgets.QCheckBox("Add channel/uploader to filename")
        main.addWidget(self.checkbox_channel)
        self.checkbox_timestamp = QtWidgets.QCheckBox("Add timestamp to filename")
        main.addWidget(self.checkbox_timestamp)

        save_layout = QtWidgets.QHBoxLayout()
        self.save_dir_input = QtWidgets.QLineEdit(
            restore_or(default_download_folder(), self.settings.value("single/save_dir"))
        )
        self.save_dir_input.editingFinished.connect(self._on_save_dir_changed)
        save_layout.addWidget(self.save_dir_input)
        browse_btn = QtWidgets.QPushButton("Browse")
        browse_btn.clicked.connect(self.on_browse)
        save_layout.addWidget(browse_btn)
        main.addLayout(save_layout)

        # Download bar
        download_bar = QtWidgets.QHBoxLayout()
        self.download_btn = QtWidgets.QPushButton("Download")
        self.download_btn.clicked.connect(self.on_download)
        download_bar.addWidget(self.download_btn)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(18)
        download_bar.addWidget(self.progress_bar)
        main.addLayout(download_bar)

        # --- Cookies ---
        cookies_row = QtWidgets.QHBoxLayout()
        cookies_label = QtWidgets.QLabel("Cookies file:")
        cookies_label.setFixedWidth(130)
        cookies_row.addWidget(cookies_label)
        self.cookies_input = QtWidgets.QLineEdit(
            self.settings.value("single/cookies", "") or ""
        )
        self.cookies_input.setPlaceholderText("Optional: path to cookies.txt for auth")
        self.cookies_input.editingFinished.connect(self._on_cookies_changed)
        cookies_row.addWidget(self.cookies_input)
        browse_cookies_btn = QtWidgets.QPushButton("Browse...")
        browse_cookies_btn.clicked.connect(self.on_browse_cookies)
        cookies_row.addWidget(browse_cookies_btn)
        clear_cookies_btn = QtWidgets.QPushButton("Clear")
        clear_cookies_btn.setFixedWidth(50)
        clear_cookies_btn.clicked.connect(lambda: self.cookies_input.clear())
        cookies_row.addWidget(clear_cookies_btn)
        main.addLayout(cookies_row)

        main.addStretch()

        # Console
        self.console_log = QtWidgets.QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setFixedHeight(180)
        main.addWidget(self.console_log)

    def log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.console_log.append(f"[{ts}] {msg}")
        sb = self.console_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_cookies_changed(self):
        path = self.cookies_input.text().strip()
        self.cookies_file_ref["path"] = path
        self.settings.setValue("single/cookies", path)

    def _on_save_dir_changed(self):
        text = self.save_dir_input.text().strip()
        if text:
            self.settings.setValue("single/save_dir", text)

    def _on_url_changed(self):
        url = self.url_input.text().strip()
        if url == self._fetch_url or (not url and not self._fetch_url):
            return
        self._cancel_fetch()
        self._cancel_thumbnail()
        self.thumbnail_label.clear()
        self.thumbnail_label.setText("No preview")
        self.meta_title.setText(f"Title: {PLACEHOLDER}")
        self.meta_uploader.setText(f"Uploader: {PLACEHOLDER}")
        self.meta_duration.setText(f"Duration: {PLACEHOLDER}")
        self.meta_platform.setText(f"Platform: {PLACEHOLDER}")
        self.info_section.setVisible(False)
        self._cached_info = None
        self._fetch_url = ""
        self.fetch_meta_btn.setEnabled(True)
        self.fetch_meta_btn.setText("Fetch")

    def on_browse_cookies(self):
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select cookies.txt",
            os.path.expanduser("~"),
            "Text files (*.txt);;All files (*)",
        )
        if file:
            self.cookies_input.setText(file)
            self._on_cookies_changed()
            self.log(f"Cookies file set: {file}")

    def _get_cookies_path(self):
        cf = self.cookies_file_ref.get("path", "").strip()
        if cf and os.path.isfile(cf):
            return cf
        return None

    def on_browse(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose folder", self.save_dir_input.text()
        )
        if folder:
            self.save_dir_input.setText(folder)
            self._on_save_dir_changed()

    def _cancel_thumbnail(self):
        if self.thumb_worker and self.thumb_worker.isRunning():
            try:
                self.thumb_worker.done_signal.disconnect()
            except TypeError:
                pass

    def _update_info_display(self, info):
        if not info:
            self.log("Could not fetch metadata. The video may be private or unavailable.")
            return
        self._cached_info = info
        title = info.get("title") or info.get("id") or "video"
        uploader = get_uploader(info) or PLACEHOLDER
        self.meta_title.setText(f"Title: {title}")
        self.meta_uploader.setText(f"Uploader: {uploader}")

        self._cancel_thumbnail()
        thumbnail_url = info.get("thumbnail")
        if thumbnail_url:
            self._thumb_seq += 1
            self.thumbnail_label.setText("Loading...")
            self.thumb_worker = ThumbnailWorker(thumbnail_url, self._thumb_seq)
            self.thumb_worker.done_signal.connect(self._on_thumbnail_loaded)
            self.thumb_worker.start()
        else:
            self.thumbnail_label.setText("No thumbnail")

        duration = info.get("duration")
        if duration:
            duration = int(duration)
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
            self.meta_duration.setText(f"Duration: {PLACEHOLDER}")

        platform = info.get("extractor") or info.get("webpage_url_domain") or "Unknown"
        self.meta_platform.setText(f"Platform: {platform}")
        self.info_section.setVisible(True)
        self.log("Metadata fetched.")

    def _on_thumbnail_loaded(self, pixmap, seq):
        if seq != self._thumb_seq:
            return
        if pixmap:
            self.thumbnail_label.setPixmap(pixmap)
        else:
            self.thumbnail_label.setText("Failed to load")

    def _cancel_fetch(self):
        if self.fetch_worker and self.fetch_worker.isRunning():
            try:
                self.fetch_worker.finished_signal.disconnect()
            except TypeError:
                pass
            try:
                self.fetch_worker.error_signal.disconnect()
            except TypeError:
                pass

    def on_fetch_metadata(self):
        url = self.url_input.text().strip()
        if not url:
            QtWidgets.QMessageBox.warning(self, "No URL", "Please paste a URL first.")
            return
        if self.fetch_worker and self.fetch_worker.isRunning():
            self.log("Already fetching. Waiting for current request...")
            return
        self._fetch_seq += 1
        self._fetch_url = url
        auto_cookie = get_cookie_path(url)
        if auto_cookie and not self.cookies_file_ref.get("path", ""):
            self.cookies_input.setText(auto_cookie)
            self.cookies_file_ref["path"] = auto_cookie
        self.log("Fetching metadata...")
        self.fetch_meta_btn.setEnabled(False)
        self.fetch_meta_btn.setText("Fetching...")
        cookies_path = self._get_cookies_path()
        self.fetch_worker = FetchWorker(url, cookies_path, self._fetch_seq)
        self.fetch_worker.finished_signal.connect(self._on_fetch_finished)
        self.fetch_worker.error_signal.connect(self._on_fetch_error)
        self.fetch_worker.start()

    def _on_fetch_finished(self, info, seq):
        self.fetch_meta_btn.setEnabled(True)
        self.fetch_meta_btn.setText("Fetch")
        if seq != self._fetch_seq:
            return
        self._update_info_display(info)

    def _on_fetch_error(self, error_msg, seq):
        self.fetch_meta_btn.setEnabled(True)
        self.fetch_meta_btn.setText("Fetch")
        if seq != self._fetch_seq:
            return
        url = self.url_input.text().strip()
        category, message = classify_error(error_msg, url)
        if category == "blocked":
            self.log(message)
            extra = get_cookie_message(detect_platform(url) if url else "")
            if extra:
                self.log(extra)
        elif category in ("format", "ffmpeg"):
            self.log(message)
        else:
            self.log(f"Metadata fetch failed: {message}")

    def on_download(self):
        if self.worker and self.worker.isRunning():
            self.log("Already downloading. Wait for current download to finish.")
            return
        url = self.url_input.text().strip()
        if not url:
            QtWidgets.QMessageBox.warning(self, "No URL", "Please paste a URL first.")
            return

        info = self._cached_info
        if not info:
            QtWidgets.QMessageBox.warning(self, "No Metadata", "Click Fetch first to get video info.")
            return

        save_dir = self.save_dir_input.text().strip() or default_download_folder()
        os.makedirs(save_dir, exist_ok=True)

        title = info.get("title") or info.get("id") or "video"
        uploader = get_uploader(info) or ""
        vid_id = info.get("id") or ""

        base_filename = clean_title(title)
        if self.checkbox_channel.isChecked() and uploader:
            base_filename += "_" + clean_title(uploader)
        if self.checkbox_timestamp.isChecked():
            base_filename += "_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        tmp_opts = {
            "skip_download": True,
            "noplaylist": True,
        }
        cf = self._get_cookies_path()
        if cf:
            tmp_opts["cookiefile"] = cf
        with YoutubeDL(tmp_opts) as ydl_tmp:
            predicted = ydl_tmp.prepare_filename(info)
        _, pred_name = os.path.split(predicted)
        _, pred_ext = os.path.splitext(pred_name)
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
        self.log(f"Downloading as: {final_base} (H.264/AAC MP4).")
        self.worker = DownloadWorker(
            url, final_outtmpl, convert, target_resolution, output_type,
            cookies_file=self._get_cookies_path(),
        )
        self.worker.status_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.finished_signal.connect(self.on_worker_finished)
        self.worker.start()

    def on_worker_finished(self, msg: str):
        self.log(msg)
        self.download_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
