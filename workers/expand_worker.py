from PyQt5 import QtCore


class ExpandWorker(QtCore.QThread):
    """List a collection URL off the UI thread."""

    done_signal = QtCore.pyqtSignal(object)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, url, cookies_file=None, limit=200):
        super().__init__()
        self.url = url
        self.cookies_file = cookies_file
        self.limit = limit

    def run(self):
        from core.collections import expand_collection

        try:
            result = expand_collection(
                self.url, cookies_file=self.cookies_file, limit=self.limit,
            )
        except Exception as exc:  # noqa: BLE001 - report, never crash the thread
            self.error_signal.emit(str(exc))
            return
        self.done_signal.emit(result)
