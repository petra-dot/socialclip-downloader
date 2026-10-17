import threading

from PyQt5 import QtCore


class DownloadWorker(QtCore.QThread):
    status_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(str)
    progress_signal = QtCore.pyqtSignal(object)  # a core.progress.Progress
    path_signal = QtCore.pyqtSignal(str)

    def __init__(self, url, outtmpl, convert, target_resolution, output_type, cookies_file=None, clip=None, subtitles="off", cookies_from_browser=""):
        super().__init__()
        self.url = url
        self.outtmpl = outtmpl
        self.convert = convert
        self.target_resolution = target_resolution
        self.output_type = output_type
        self.cookies_file = cookies_file
        self.clip = clip
        self.subtitles = subtitles
        self.cookies_from_browser = cookies_from_browser
        self._cancel = threading.Event()
        self.cancelled = False

    def cancel(self):
        """Ask the running download to stop. It ends as 'cancelled'."""
        self._cancel.set()

    def run(self):
        from core.download import download_one
        from core.history import HistoryStore

        self.status_signal.emit("Starting download and checking URL...")
        result = download_one(
            self.url,
            outtmpl=self.outtmpl,
            output_type=self.output_type,
            convert=self.convert,
            target_resolution=self.target_resolution,
            cookies_file=self.cookies_file,
            progress=self.progress_signal.emit,
            clip=self.clip,
            subtitles=self.subtitles,
            cookies_from_browser=self.cookies_from_browser,
            cancel=self._cancel.is_set,
            history=HistoryStore(),
            source="single",
        )
        self.cancelled = result.error_category == "cancelled"
        self.path_signal.emit((result.path or "") if result.status == "ok" else "")
        self.finished_signal.emit(result.message or result.path or result.status)
