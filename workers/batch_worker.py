import os
import subprocess

from PyQt5 import QtCore
from yt_dlp import YoutubeDL

from utils.ydl_opts import _nle_ydl_opts, _ffmpeg_to_nle_mp4, ffprobe_get_height, strip_ansi


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
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        succeeded = 0
        failed = 0
        total = len(self.urls)
        for i, url in enumerate(self.urls, 1):
            if self._cancelled:
                self.status_signal.emit("Batch cancelled by user.")
                break
            try:
                self.status_signal.emit(f"[ {i} / {total} ] Starting: {url}")

                outtmpl = os.path.join(self.save_dir, "%(title)s.%(ext)s")
                ydl_opts = _nle_ydl_opts(
                    outtmpl=outtmpl,
                    cookies_file=self.cookies_file,
                )

                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                if not info:
                    raise Exception(
                        "Could not extract video info. Video may be private, deleted, or region-locked."
                    )
                downloaded_file = ydl.prepare_filename(info)

                if not os.path.exists(downloaded_file):
                    base = os.path.splitext(downloaded_file)[0]
                    if os.path.exists(base + ".mp4"):
                        downloaded_file = base + ".mp4"

                final_height = info.get("height") or ffprobe_get_height(downloaded_file)

                if self.output_type == "MP3":
                    mp3_path = os.path.splitext(downloaded_file)[0] + ".mp3"
                    cmd = [
                        "ffmpeg", "-i", downloaded_file,
                        "-q:a", "0", "-map", "a",
                        "-y", mp3_path,
                    ]
                    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if result.returncode != 0:
                        raise Exception(f"ffmpeg error: {result.stderr.decode(errors='ignore')}")
                    final_file = mp3_path
                else:
                    if self.target_resolution < final_height and final_height > 0:
                        base, _ = os.path.splitext(downloaded_file)
                        out_file = f"{base}_{self.target_resolution}p.mp4"
                        result = _ffmpeg_to_nle_mp4(downloaded_file, out_file, self.target_resolution)
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
                self.status_signal.emit(f"[ {i} / {total} ] Failed: {url} \u2014 {error_msg}")
                failed += 1

        self.finished_signal.emit(f"Batch complete. {succeeded} succeeded, {failed} failed.")
