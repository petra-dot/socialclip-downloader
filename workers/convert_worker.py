import os
import subprocess

from PyQt5 import QtCore

from utils.ffmpeg import ffmpeg_path
from utils.ydl_opts import _ffmpeg_to_nle_mp4, ffprobe_get_height


class ConvertFileWorker(QtCore.QThread):
    status_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(str)

    def __init__(self, input_path, output_type, target_resolution=None):
        super().__init__()
        self.input_path = input_path
        self.output_type = output_type
        self.target_resolution = target_resolution

    def run(self):
        try:
            if not os.path.exists(self.input_path):
                self.finished_signal.emit("Input file does not exist.")
                return

            if self.output_type in ("MP3", "WAV"):
                base = os.path.splitext(self.input_path)[0]
                if self.output_type == "MP3":
                    out_path = base + ".mp3"
                    self.status_signal.emit(f"Converting to MP3: {out_path}")
                    cmd = [
                        ffmpeg_path(), "-i", self.input_path,
                        "-q:a", "0", "-map", "a",
                        "-y", out_path,
                    ]
                else:
                    out_path = base + ".wav"
                    self.status_signal.emit(f"Converting to WAV: {out_path}")
                    cmd = [
                        ffmpeg_path(), "-i", self.input_path,
                        "-vn", "-acodec", "pcm_s16le",
                        "-ar", "44100", "-ac", "2",
                        "-y", out_path,
                    ]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode != 0:
                    self.finished_signal.emit(f"ffmpeg error: {result.stderr.decode(errors='ignore')}")
                    return
                self.finished_signal.emit(f"Audio saved: {out_path}")
                return

            if self.output_type == "MP4":
                src_height = ffprobe_get_height(self.input_path)
                self.status_signal.emit(f"Source resolution detected: {src_height}p")
                if src_height == 0:
                    self.status_signal.emit("Warning: couldn't detect source height; aborting conversion.")
                    self.finished_signal.emit("Conversion aborted: unknown source resolution.")
                    return
                if self.target_resolution > src_height:
                    self.finished_signal.emit(
                        f"Skipped conversion: source ({src_height}p) is lower than "
                        f"target ({self.target_resolution}p). No upscaling."
                    )
                    return
                if self.target_resolution == src_height:
                    self.finished_signal.emit(
                        f"Skipped conversion: source resolution equals target ({src_height}p)."
                    )
                    return
                base = os.path.splitext(self.input_path)[0]
                out_path = f"{base}_{self.target_resolution}p.mp4"
                self.status_signal.emit(f"Converting to {self.target_resolution}p -> {out_path}")
                result = _ffmpeg_to_nle_mp4(self.input_path, out_path, self.target_resolution)
                if result.returncode != 0:
                    self.finished_signal.emit(f"ffmpeg error: {result.stderr.decode(errors='ignore')}")
                    return
                self.finished_signal.emit(f"Conversion completed: {out_path}")
                return

            self.finished_signal.emit("Unknown conversion parameters.")

        except Exception as e:
            self.finished_signal.emit(f"Error during conversion: {e}")
