import sys
import os
import re
import datetime
import subprocess
import urllib.request

__version__ = "0.3.0"

PYQT_IMPORT_ERROR = None
YTDLP_IMPORT_ERROR = None
try:
    from PyQt5 import QtWidgets, QtCore
except Exception as e:
    QtWidgets = None
    QtCore = None
    PYQT_IMPORT_ERROR = e

try:
    from yt_dlp import YoutubeDL
except Exception as e:
    YoutubeDL = None
    YTDLP_IMPORT_ERROR = e

# ---------------- Utility ----------------

def strip_ansi(text: str) -> str:
    """Remove ANSI terminal color codes from yt-dlp error messages."""
    return re.sub(r"\[[0-9;]*m", "", text)



def default_download_folder():
    home = os.path.expanduser("~")
    downloads = os.path.join(home, "Downloads")
    return downloads if os.path.isdir(downloads) else home


def clean_title(title: str) -> str:
    if not title:
        return "video"
    title_ascii = title.encode("ascii", "ignore").decode("ascii")
    title_ascii = re.sub(r"[#@]", "", title_ascii)
    title_ascii = re.sub(r"[\\/:*?\"<>|]", " ", title_ascii)
    title_ascii = re.sub(r"[^\w\s\-]", "", title_ascii)
    title_ascii = re.sub(r"\s+", " ", title_ascii).strip()
    return title_ascii[:120] or "video"


def get_uploader(info: dict) -> str:
    for k in ("uploader", "channel", "creator", "uploader_id"):
        v = info.get(k)
        if v:
            return v
    return ""


def ffprobe_get_height(path: str) -> int:
    """Return video height using ffprobe or ffmpeg fallback. Returns 0 on failure."""
    try:
        # try ffprobe first
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=height",
            "-of",
            "csv=p=0",
            path,
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip()
        if out:
            # sometimes multiple lines; take first numeric
            line = out.splitlines()[0].strip()
            return int(line)
    except Exception:
        pass
    try:
        # fallback with ffmpeg
        cmd = [
            "ffmpeg",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=height",
            "-of",
            "csv=p=0",
            path,
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip()
        if out:
            return int(out.splitlines()[0].strip())
    except Exception:
        pass
    return 0


def make_unique_filepath(
    save_dir: str, base_filename: str, ext: str, fallback_id: str = None
) -> str:
    """Return a filesystem path that does not collide. If file exists, append fallback_id or numeric suffix."""
    candidate = os.path.join(save_dir, f"{base_filename}.{ext}")
    if not os.path.exists(candidate):
        return candidate
    # try with fallback id if provided
    if fallback_id:
        candidate2 = os.path.join(save_dir, f"{base_filename}_{fallback_id}.{ext}")
        if not os.path.exists(candidate2):
            return candidate2
    # else add numeric increment
    i = 1
    while True:
        candidate3 = os.path.join(save_dir, f"{base_filename}_{i}.{ext}")
        if not os.path.exists(candidate3):
            return candidate3
        i += 1


# ---------------- Workers ----------------


class DownloadWorker(QtCore.QThread):
    status_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(str)
    progress_signal = QtCore.pyqtSignal(int)

    def __init__(self, url, outtmpl, convert, target_resolution, output_type, cookies_file=None):
        super().__init__()
        self.url = url
        self.outtmpl = outtmpl  # full template including .%(ext)s
        self.convert = convert
        self.target_resolution = target_resolution
        self.output_type = output_type
        self.cookies_file = cookies_file  # path to cookies.txt or None
        self._progress_hook = self._create_progress_hook()

    def _create_progress_hook(self):
        def hook(d):
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes", 0)
                if total and total > 0:
                    pct = int(downloaded / total * 100)
                    self.progress_signal.emit(pct)
            elif d.get("status") == "finished":
                self.progress_signal.emit(100)
        return hook

    def run(self):
        try:
            # Check if URL is valid and extractable
            self.status_signal.emit("Starting download and checking URL...")
            ydl_opts = {
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
                "outtmpl": self.outtmpl,
                "merge_output_format": "mp4",
                "noplaylist": True,
                "updatetime": False,
                "no_warnings": False,
                "ignoreerrors": False,
                "age_limit": 99,
                "no_color": True,
                "progress_hooks": [self._progress_hook],
            }
            if self.cookies_file and os.path.isfile(self.cookies_file):
                ydl_opts["cookiefile"] = self.cookies_file
                self.status_signal.emit(f"Using cookies: {self.cookies_file}")

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                if not info:
                    self.finished_signal.emit("Download failed: could not extract video info. The video may be private, deleted, or region-locked.")
                    return
                downloaded_file = ydl.prepare_filename(info)
            self.status_signal.emit(f"Downloaded: {downloaded_file}")

            # Get final extension (in case)
            final_height = info.get("height") or ffprobe_get_height(downloaded_file)
            self.status_signal.emit(f"Detected source height: {final_height}p")

            # If user requested audio only (MP3) and asked conversion at download stage
            if self.output_type == "MP3":
                mp3_path = os.path.splitext(downloaded_file)[0] + ".mp3"
                self.status_signal.emit("Converting downloaded file to MP3...")
                cmd = [
                    "ffmpeg",
                    "-i",
                    downloaded_file,
                    "-q:a",
                    "0",
                    "-map",
                    "a",
                    "-y",
                    mp3_path,
                ]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode != 0:
                    self.status_signal.emit(f"ffmpeg error: {result.stderr.decode(errors='ignore')}")
                self.finished_signal.emit(f"MP3 saved: {mp3_path}")
                return

            # If conversion requested and it's a video conversion
            if self.convert and self.output_type == "MP4":
                # skip upscaling
                if final_height == 0:
                    self.status_signal.emit(
                        "Warning: could not detect source resolution; attempting conversion."
                    )
                if self.target_resolution > final_height and final_height > 0:
                    self.finished_signal.emit(
                        f"Skipped conversion: source ({final_height}p) is lower than target ({self.target_resolution}p). No upscaling."
                    )
                    return
                if final_height == self.target_resolution:
                    self.finished_signal.emit(
                        f"Skipped conversion: source resolution equals target ({final_height}p)."
                    )
                    return
                # build output path
                base, _ = os.path.splitext(downloaded_file)
                out_file = f"{base}_{self.target_resolution}p.mp4"
                self.status_signal.emit(
                    f"Converting to {self.target_resolution}p -> {out_file}"
                )
                cmd = [
                    "ffmpeg",
                    "-i",
                    downloaded_file,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "slow",
                    "-crf",
                    "22",
                    "-vf",
                    f"scale=-2:{self.target_resolution}",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-y",
                    out_file,
                ]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode != 0:
                    self.status_signal.emit(f"ffmpeg error: {result.stderr.decode(errors='ignore')}")
                self.finished_signal.emit(f"Conversion completed: {out_file}")
                return

            # If no conversion or conversion not applicable
            self.finished_signal.emit(f"Download finished: {downloaded_file}")
        except Exception as e:
            error_msg = strip_ansi(str(e))
            if any(k in error_msg for k in ["Sign in to confirm", "bot", "cookies", "reloaded", "reload", "page needs", "Requested format"]):
                if "Requested format" in error_msg:
                    self.finished_signal.emit("Could not find a downloadable format. Try a different video or check if it is region-locked.")
                else:
                    self.finished_signal.emit("YouTube blocked the request. Load a cookies.txt file in the Cookies field and try again.")
            else:
                self.finished_signal.emit(f"Error during download/conversion: {error_msg}")


class ConvertFileWorker(QtCore.QThread):
    status_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(str)

    def __init__(self, input_path, output_type, target_resolution=None):
        super().__init__()
        self.input_path = input_path
        self.output_type = output_type  # 'MP4','MP3','WAV'
        self.target_resolution = target_resolution

    def run(self):
        try:
            if not os.path.exists(self.input_path):
                self.finished_signal.emit("Input file does not exist.")
                return

            # if audio output
            if self.output_type in ("MP3", "WAV"):
                base = os.path.splitext(self.input_path)[0]
                if self.output_type == "MP3":
                    out_path = base + ".mp3"
                    self.status_signal.emit(f"Converting to MP3: {out_path}")
                    cmd = [
                        "ffmpeg",
                        "-i",
                        self.input_path,
                        "-q:a",
                        "0",
                        "-map",
                        "a",
                        "-y",
                        out_path,
                    ]
                else:  # WAV
                    out_path = base + ".wav"
                    self.status_signal.emit(f"Converting to WAV: {out_path}")
                    cmd = [
                        "ffmpeg",
                        "-i",
                        self.input_path,
                        "-vn",
                        "-acodec",
                        "pcm_s16le",
                        "-ar",
                        "44100",
                        "-ac",
                        "2",
                        "-y",
                        out_path,
                    ]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode != 0:
                    self.status_signal.emit(f"ffmpeg error: {result.stderr.decode(errors='ignore')}")
                self.finished_signal.emit(f"Audio saved: {out_path}")
                return

            # video conversion (MP4 target)
            if self.output_type == "MP4":
                src_height = ffprobe_get_height(self.input_path)
                self.status_signal.emit(f"Source resolution detected: {src_height}p")
                if src_height == 0:
                    self.status_signal.emit(
                        "Warning: couldn't detect source height; aborting conversion."
                    )
                    self.finished_signal.emit(
                        "Conversion aborted: unknown source resolution."
                    )
                    return
                if self.target_resolution > src_height:
                    self.finished_signal.emit(
                        f"Skipped conversion: source ({src_height}p) is lower than target ({self.target_resolution}p). No upscaling."
                    )
                    return
                if self.target_resolution == src_height:
                    self.finished_signal.emit(
                        f"Skipped conversion: source resolution equals target ({src_height}p)."
                    )
                    return
                base = os.path.splitext(self.input_path)[0]
                out_path = f"{base}_{self.target_resolution}p.mp4"
                self.status_signal.emit(
                    f"Converting to {self.target_resolution}p -> {out_path}"
                )
                cmd = [
                    "ffmpeg",
                    "-i",
                    self.input_path,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "slow",
                    "-crf",
                    "22",
                    "-vf",
                    f"scale=-2:{self.target_resolution}",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-y",
                    out_path,
                ]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode != 0:
                    self.status_signal.emit(f"ffmpeg error: {result.stderr.decode(errors='ignore')}")
                self.finished_signal.emit(f"Conversion completed: {out_path}")
                return

            self.finished_signal.emit("Unknown conversion parameters.")
        except Exception as e:
            self.finished_signal.emit(f"Error during conversion: {e}")


class BatchDownloadWorker(QtCore.QThread):
    status_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(str)

    def __init__(self, urls, save_dir, output_type, target_resolution, cookies_file):
        super().__init__()
        self.urls = urls
        self.save_dir = save_dir
        self.output_type = output_type
        self.target_resolution = target_resolution
        self.cookies_file = cookies_file

    def run(self):
        succeeded = 0
        failed = 0
        total = len(self.urls)
        for i, url in enumerate(self.urls, 1):
            try:
                self.status_signal.emit(f"[ {i} / {total} ] Starting: {url}")
                ydl_opts = {
                    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
                    "outtmpl": os.path.join(self.save_dir, "%(title)s.%(ext)s"),
                    "merge_output_format": "mp4",
                    "noplaylist": True,
                    "updatetime": False,
                    "no_warnings": False,
                    "ignoreerrors": False,
                    "age_limit": 99,
                    "no_color": True,
                }
                if self.cookies_file and os.path.isfile(self.cookies_file):
                    ydl_opts["cookiefile"] = self.cookies_file
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                if not info:
                    raise Exception("Could not extract video info. Video may be private, deleted, or region-locked.")
                downloaded_file = ydl.prepare_filename(info)
                final_height = info.get("height") or ffprobe_get_height(downloaded_file)
                if self.output_type == "MP3":
                    mp3_path = os.path.splitext(downloaded_file)[0] + ".mp3"
                    cmd = [
                        "ffmpeg",
                        "-i",
                        downloaded_file,
                        "-q:a",
                        "0",
                        "-map",
                        "a",
                        "-y",
                        mp3_path,
                    ]
                    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if result.returncode != 0:
                        raise Exception(f"ffmpeg error: {result.stderr.decode(errors='ignore')}")
                    final_file = mp3_path
                else:
                    if self.target_resolution < final_height and final_height > 0:
                        base, _ = os.path.splitext(downloaded_file)
                        out_file = f"{base}_{self.target_resolution}p.mp4"
                        cmd = [
                            "ffmpeg",
                            "-i",
                            downloaded_file,
                            "-c:v",
                            "libx264",
                            "-preset",
                            "slow",
                            "-crf",
                            "22",
                            "-vf",
                            f"scale=-2:{self.target_resolution}",
                            "-c:a",
                            "aac",
                            "-b:a",
                            "128k",
                            "-y",
                            out_file,
                        ]
                        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        if result.returncode != 0:
                            raise Exception(f"ffmpeg error: {result.stderr.decode(errors='ignore')}")
                        final_file = out_file
                    else:
                        final_file = downloaded_file
                self.status_signal.emit(f"[ {i} / {total} ] Done: {os.path.basename(final_file)}")
                succeeded += 1
            except Exception as e:
                error_msg = strip_ansi(str(e))
                if any(k in error_msg for k in ["Sign in to confirm", "bot", "cookies", "reloaded", "reload", "page needs"]):
                    error_msg = "YouTube blocked. Load cookies.txt and try again."
                elif "Requested format" in error_msg:
                    error_msg = "Format not available. Video may be region-locked."
                self.status_signal.emit(f"[ {i} / {total} ] Failed: {url} — {error_msg}")
                failed += 1
        self.finished_signal.emit(f"Batch complete. {succeeded} succeeded, {failed} failed.")


# ---------------- GUI ----------------


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"SocialClip Downloader v{__version__}")
        self.setMinimumSize(820, 520)
        self.worker = None
        self.conv_worker = None
        self.batch_worker = None
        self.cookies_file = ""  # path to cookies.txt; empty = no cookies
        self.init_ui()

    def init_ui(self):
        self.tabs = QtWidgets.QTabWidget()
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().addWidget(self.tabs)

        single_tab = QtWidgets.QWidget()
        main = QtWidgets.QVBoxLayout(single_tab)
        self.tabs.addTab(single_tab, "Single Download")

        # URL & download area
        url_row = QtWidgets.QHBoxLayout()
        self.url_input = QtWidgets.QLineEdit()
        self.url_input.setPlaceholderText("Paste video URL here")
        self.url_input.textChanged.connect(self._on_url_changed)
        url_row.addWidget(self.url_input)
        self.fetch_meta_btn = QtWidgets.QPushButton("Fetch Metadata")
        self.fetch_meta_btn.clicked.connect(self.on_fetch_metadata)
        url_row.addWidget(self.fetch_meta_btn)
        main.addLayout(url_row)

        # Cookies file row
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

        # Metadata preview
        meta_layout = QtWidgets.QHBoxLayout()
        self.thumbnail_label = QtWidgets.QLabel("No preview")
        self.thumbnail_label.setFixedSize(160, 90)
        self.thumbnail_label.setAlignment(QtCore.Qt.AlignCenter)
        meta_layout.addWidget(self.thumbnail_label)
        meta_right = QtWidgets.QVBoxLayout()
        self.meta_title = QtWidgets.QLabel("Title: —")
        self.meta_uploader = QtWidgets.QLabel("Uploader: —")
        self.meta_duration = QtWidgets.QLabel("Duration: —")
        self.meta_platform = QtWidgets.QLabel("Platform: —")
        meta_right.addWidget(self.meta_title)
        meta_right.addWidget(self.meta_uploader)
        meta_right.addWidget(self.meta_duration)
        meta_right.addWidget(self.meta_platform)
        meta_layout.addLayout(meta_right)
        main.addLayout(meta_layout)

        # Output type and convert choices
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

        # Rename options
        rename_row = QtWidgets.QHBoxLayout()
        self.checkbox_timestamp = QtWidgets.QCheckBox("Add timestamp to filename")
        self.checkbox_channel = QtWidgets.QCheckBox("Add channel/uploader to filename")
        rename_row.addWidget(self.checkbox_channel)
        rename_row.addWidget(self.checkbox_timestamp)
        main.addLayout(rename_row)

        # Download button
        dl_row = QtWidgets.QHBoxLayout()
        self.download_btn = QtWidgets.QPushButton("Download")
        self.download_btn.clicked.connect(self.on_download)
        dl_row.addWidget(self.download_btn)
        main.addLayout(dl_row)

        # Progress bar
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        main.addWidget(self.progress_bar)

        # Console log
        self.console_log = QtWidgets.QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setFixedHeight(200)
        main.addWidget(self.console_log)

        # Separator
        main.addWidget(QtWidgets.QLabel("Convert existing file (select file below)"))

        # Convert-from-file UI
        file_layout = QtWidgets.QHBoxLayout()
        self.file_path_input = QtWidgets.QLineEdit()
        file_layout.addWidget(self.file_path_input)
        pick_btn = QtWidgets.QPushButton("Select File...")
        pick_btn.clicked.connect(self.on_pick_file)
        file_layout.addWidget(pick_btn)
        main.addLayout(file_layout)

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
        main.addLayout(conv_opts)

        conv_btn_row = QtWidgets.QHBoxLayout()
        self.convert_file_btn = QtWidgets.QPushButton("Convert Selected File")
        self.convert_file_btn.clicked.connect(self.on_convert_file)
        conv_btn_row.addWidget(self.convert_file_btn)
        main.addLayout(conv_btn_row)

        # Batch Download Tab
        batch_tab = QtWidgets.QWidget()
        batch_layout = QtWidgets.QVBoxLayout(batch_tab)
        self.tabs.addTab(batch_tab, "Batch Download")

        # 1. QTextEdit for URLs
        self.batch_urls_text = QtWidgets.QTextEdit()
        self.batch_urls_text.setPlaceholderText("Paste one URL per line")
        batch_layout.addWidget(self.batch_urls_text)

        # 2. Save folder row
        batch_save_layout = QtWidgets.QHBoxLayout()
        self.batch_save_dir_input = QtWidgets.QLineEdit(default_download_folder())
        batch_save_layout.addWidget(self.batch_save_dir_input)
        batch_browse_btn = QtWidgets.QPushButton("Browse")
        batch_browse_btn.clicked.connect(self.on_batch_browse)
        batch_save_layout.addWidget(batch_browse_btn)
        batch_layout.addLayout(batch_save_layout)

        # 3. Output and resolution row
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

        # 4. Start Batch button
        self.batch_start_btn = QtWidgets.QPushButton("Start Batch")
        self.batch_start_btn.clicked.connect(self.on_start_batch)
        batch_layout.addWidget(self.batch_start_btn)

        # 5. Console
        self.batch_console_log = QtWidgets.QTextEdit()
        self.batch_console_log.setReadOnly(True)
        self.batch_console_log.setFixedHeight(200)
        batch_layout.addWidget(self.batch_console_log)

    # ------- helpers for GUI and logging -------
    def log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.console_log.append(f"[{ts}] {msg}")
        # auto-scroll
        sb = self.console_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_cookies_changed(self, text):
        self.cookies_file = text.strip()

    def _on_url_changed(self):
        self.thumbnail_label.clear()
        self.thumbnail_label.setText("No preview")
        self.meta_title.setText("Title: —")
        self.meta_uploader.setText("Uploader: —")
        self.meta_duration.setText("Duration: —")
        self.meta_platform.setText("Platform: —")

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
        """Return base ydl options including cookiefile if set."""
        opts = {
            "skip_download": True,
            "noplaylist": True,
            "age_limit": 99,
            "no_color": True,
        }
        if self.cookies_file and os.path.isfile(self.cookies_file):
            opts["cookiefile"] = self.cookies_file
        return opts

    def on_browse(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose folder", self.save_dir_input.text()
        )
        if folder:
            self.save_dir_input.setText(folder)

    # ------- metadata fetch (optional) -------
    def on_fetch_metadata(self):
        url = self.url_input.text().strip()
        if not url:
            QtWidgets.QMessageBox.warning(self, "No URL", "Please paste a URL first.")
            return
        try:
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
            uploader = get_uploader(info) or "—"
            self.meta_title.setText(f"Title: {title}")
            self.meta_uploader.setText(f"Uploader: {uploader}")
            # Thumbnail
            try:
                thumbnail_url = info.get("thumbnail")
                if thumbnail_url:
                    with urllib.request.urlopen(thumbnail_url) as response:
                        data = response.read()
                    pixmap = QtWidgets.QPixmap()
                    pixmap.loadFromData(data)
                    scaled_pixmap = pixmap.scaled(160, 90, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                    self.thumbnail_label.setPixmap(scaled_pixmap)
                else:
                    self.thumbnail_label.setText("No thumbnail")
            except Exception as e:
                self.thumbnail_label.setText("Failed to load")
            # Duration
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
                self.meta_duration.setText("Duration: —")
            # Platform
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

    # ------- download flow -------
    def on_download(self):
        url = self.url_input.text().strip()
        if not url:
            QtWidgets.QMessageBox.warning(self, "No URL", "Please paste a URL first.")
            return
        save_dir = self.save_dir_input.text().strip() or default_download_folder()
        os.makedirs(save_dir, exist_ok=True)

        # Pre-fetch info to build filename and to ensure unique file names
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

        # Build outtmpl and ensure uniqueness (predict ext with prepare_filename)
        # Use a temporary ydl to predict ext
        temp_outtmpl = os.path.join(save_dir, base_filename + ".%(ext)s")
        tmp_opts = self._get_ydl_base_opts()
        tmp_opts["outtmpl"] = temp_outtmpl
        with YoutubeDL(tmp_opts) as ydl_tmp:
            predicted = ydl_tmp.prepare_filename(info)  # this includes extension
        pred_dir, pred_name = os.path.split(predicted)
        pred_base, pred_ext = os.path.splitext(pred_name)
        ext = pred_ext.lstrip(".") or "mp4"

        # if predicted file exists, try to attach id; otherwise numeric increment
        final_path = make_unique_filepath(
            save_dir, base_filename, ext, fallback_id=vid_id
        )
        # final outtmpl should use .%(ext)s so yt-dlp picks correct ext
        final_base = os.path.splitext(os.path.basename(final_path))[0]
        final_outtmpl = os.path.join(save_dir, final_base + ".%(ext)s")

        # options
        output_type = "MP3" if "MP3" in self.output_combo.currentText() else "MP4"
        convert = self.convert_checkbox.isChecked() and (output_type == "MP4")
        target_resolution = int(self.resolution_combo.currentText())

        # Start worker
        self.download_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.log(f"Downloading as: {final_base} (temp outtmpl set).")
        self.worker = DownloadWorker(
            url, final_outtmpl, convert, target_resolution, output_type,
            cookies_file=self.cookies_file or None,
        )
        self.worker.status_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.finished_signal.connect(self.on_worker_finished)
        self.worker.start()

    def on_worker_finished(self, msg: str):
        self.log(msg)
        self.download_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

    # ------- convert-from-file UI -------
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
            QtWidgets.QMessageBox.warning(
                self, "No file", "Please select a file to convert."
            )
            return
        if not os.path.exists(path):
            QtWidgets.QMessageBox.warning(
                self, "Missing", "Selected file path does not exist."
            )
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
        urls = [line.strip() for line in urls_text.split('\n') if line.strip()]
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
            urls, save_dir, output_type, target_resolution, self.cookies_file
        )
        self.batch_worker.status_signal.connect(self.batch_log)
        self.batch_worker.finished_signal.connect(self.on_batch_finished)
        self.batch_worker.start()

    def on_batch_finished(self, msg: str):
        self.batch_log(msg)
        self.batch_start_btn.setEnabled(True)


# ---------------- Run ----------------


def main():
    # Check runtime dependencies
    missing = []
    if YoutubeDL is None:
        missing.append(
            "yt-dlp (Python package 'yt-dlp') - install with: pip install yt-dlp"
        )
    if QtWidgets is None or QtCore is None:
        missing.append("PyQt5 - install with: pip install PyQt5")
    if missing:
        print("Missing required dependencies:")
        for m in missing:
            print(" - ", m)
        print("Or install all via: pip install -r requirements.txt")
        sys.exit(1)

    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()