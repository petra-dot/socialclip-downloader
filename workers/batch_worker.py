import os

from PyQt5 import QtCore

from core.download import download_one


class BatchDownloadWorker(QtCore.QThread):
    status_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(str)
    item_signal = QtCore.pyqtSignal(int, str, object)

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
        outtmpl = os.path.join(self.save_dir, "%(title)s.%(ext)s")
        for i, url in enumerate(self.urls, 1):
            if self._cancelled:
                for skipped in range(i - 1, total):
                    self.item_signal.emit(skipped, "cancelled", None)
                self.status_signal.emit("Batch cancelled by user.")
                break

            self.status_signal.emit(f"[ {i} / {total} ] Starting: {url}")
            self.item_signal.emit(i - 1, "running", None)
            result = download_one(
                url,
                outtmpl=outtmpl,
                output_type=self.output_type,
                convert=self.output_type == "MP4",
                target_resolution=self.target_resolution,
                cookies_file=self.cookies_file,
            )

            if result.status == "ok":
                name = os.path.basename(result.path) if result.path else (result.message or "ok")
                self.item_signal.emit(i - 1, "done", result)
                self.status_signal.emit(f"[ {i} / {total} ] Done: {name}")
                succeeded += 1
            else:
                self.item_signal.emit(i - 1, "failed", result)
                self.status_signal.emit(f"[ {i} / {total} ] Failed: {url} \u2014 {result.message}")
                failed += 1

        if self._cancelled:
            self.finished_signal.emit(f"Batch cancelled. {succeeded} completed, {failed} failed.")
        else:
            self.finished_signal.emit(f"Batch complete. {succeeded} succeeded, {failed} failed.")
