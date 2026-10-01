import os
import subprocess

from PyQt5 import QtCore

from sites.errors import classify_error
from utils.ffmpeg import ffmpeg_path
from utils.ydl_opts import _nle_ydl_opts, _ffmpeg_to_nle_mp4, ffprobe_get_height, strip_ansi
from workers.pipeline import plan_postprocess


class DownloadWorker(QtCore.QThread):
    status_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(str)
    progress_signal = QtCore.pyqtSignal(int)

    def __init__(self, url, outtmpl, convert, target_resolution, output_type, cookies_file=None):
        super().__init__()
        self.url = url
        self.outtmpl = outtmpl
        self.convert = convert
        self.target_resolution = target_resolution
        self.output_type = output_type
        self.cookies_file = cookies_file
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
            self.status_signal.emit("Starting download and checking URL...")
            from yt_dlp import YoutubeDL

            ydl_opts = _nle_ydl_opts(
                outtmpl=self.outtmpl,
                progress_hooks=[self._progress_hook],
                cookies_file=self.cookies_file,
            )
            if self.cookies_file and os.path.isfile(self.cookies_file):
                self.status_signal.emit(f"Using cookies: {self.cookies_file}")

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                if not info:
                    self.finished_signal.emit(
                        "Download failed: could not extract video info. "
                        "The video may be private, deleted, or region-locked."
                    )
                    return
                downloaded_file = ydl.prepare_filename(info)

            if not os.path.exists(downloaded_file):
                base = os.path.splitext(downloaded_file)[0]
                if os.path.exists(base + ".mp4"):
                    downloaded_file = base + ".mp4"

            self.status_signal.emit(f"Downloaded: {downloaded_file}")

            final_height = info.get("height") or ffprobe_get_height(downloaded_file)
            self.status_signal.emit(f"Detected source height: {final_height}p")

            if self.output_type == "MP3":
                mp3_path = os.path.splitext(downloaded_file)[0] + ".mp3"
                self.status_signal.emit("Converting to MP3...")
                cmd = [
                    ffmpeg_path(), "-i", downloaded_file,
                    "-q:a", "0", "-map", "a",
                    "-y", mp3_path,
                ]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode != 0:
                    self.finished_signal.emit(f"ffmpeg error: {result.stderr.decode(errors='ignore')}")
                    return
                os.remove(downloaded_file)
                self.finished_signal.emit(f"MP3 saved: {mp3_path}")
                return

            if self.output_type == "MP4":
                action = plan_postprocess(
                    "MP4", self.convert, final_height, self.target_resolution
                )
                if action == "skip_low":
                    self.finished_signal.emit(
                        f"Skipped conversion: source ({final_height}p) is lower than "
                        f"target ({self.target_resolution}p). No upscaling."
                    )
                    return
                if action == "skip_equal":
                    self.finished_signal.emit(
                        f"Skipped conversion: source resolution equals target ({final_height}p)."
                    )
                    return
                if action == "convert":
                    if final_height == 0:
                        self.status_signal.emit(
                            "Warning: could not detect source resolution; attempting conversion."
                        )
                    base, _ = os.path.splitext(downloaded_file)
                    out_file = f"{base}_{self.target_resolution}p.mp4"
                    self.status_signal.emit(f"Converting to {self.target_resolution}p -> {out_file}")
                    result = _ffmpeg_to_nle_mp4(downloaded_file, out_file, self.target_resolution)
                    if result.returncode != 0:
                        self.finished_signal.emit(f"ffmpeg error: {result.stderr.decode(errors='ignore')}")
                        return
                    os.remove(downloaded_file)
                    self.finished_signal.emit(f"Conversion completed: {out_file}")
                    return

            self.finished_signal.emit(f"Download finished: {downloaded_file}")

        except Exception as e:
            error_msg = strip_ansi(str(e))
            category, message = classify_error(error_msg, self.url)
            if category == "other":
                message = f"Error during download/conversion: {message}"
            self.finished_signal.emit(message)
