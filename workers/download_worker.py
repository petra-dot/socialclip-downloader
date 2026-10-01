from PyQt5 import QtCore


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
        from core.download import download_one

        self.status_signal.emit("Starting download and checking URL...")
        result = download_one(
            self.url,
            outtmpl=self.outtmpl,
            output_type=self.output_type,
            convert=self.convert,
            target_resolution=self.target_resolution,
            cookies_file=self.cookies_file,
            progress=self.progress_signal.emit,
        )
        self.finished_signal.emit(result.message or result.path or result.status)
