from PyQt5 import QtCore


class UpdateCheckWorker(QtCore.QThread):
    """Ask GitHub for the latest release, off the UI thread."""

    done_signal = QtCore.pyqtSignal(object)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, current_version):
        super().__init__()
        self.current_version = current_version

    def run(self):
        from core.updater import fetch_latest_release, is_newer

        try:
            release = fetch_latest_release()
        except Exception as exc:  # noqa: BLE001 - report, never crash the thread
            self.error_signal.emit(str(exc))
            return
        if is_newer(release.version, self.current_version):
            self.done_signal.emit(release)
        else:
            self.done_signal.emit(None)


class UpdateDownloadWorker(QtCore.QThread):
    """Download and digest-verify an update asset, off the UI thread."""

    progress_signal = QtCore.pyqtSignal(int)
    done_signal = QtCore.pyqtSignal(str)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, asset, dest):
        super().__init__()
        self.asset = asset
        self.dest = dest
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        from core.updater import DownloadCancelled, download_asset, verify_digest

        def on_progress(done, total):
            if total:
                self.progress_signal.emit(int(done / total * 100))

        try:
            download_asset(
                self.asset, self.dest, progress=on_progress,
                cancel=lambda: self._cancelled,
            )
            if not verify_digest(self.dest, self.asset.digest):
                if self.asset.digest:
                    self.error_signal.emit(
                        "Download failed verification. The file was deleted."
                    )
                else:
                    self.error_signal.emit(
                        "This release published no checksum, so the download "
                        "was discarded."
                    )
                return
        except DownloadCancelled:
            return  # a cancelled download emits nothing; the UI restores its own state
        except Exception as exc:  # noqa: BLE001
            self.error_signal.emit(str(exc))
            return
        self.done_signal.emit(self.dest)
