"""Run component checks and repairs off the UI thread."""

from PyQt5 import QtCore

from core.maintenance import (
    check_all,
    install_deno,
    install_ffmpeg,
    install_ytdlp,
)


def run_repairs(keys, progress=None):
    """Install each requested component, then re-check. Returns the components.

    A failure is reported through `progress` and does not stop the others: one
    broken component must not block the rest. `progress` is called with
    `(key, detail)`, matching `MaintenanceRepairWorker`'s two-argument
    `progress_signal`.
    """
    installers = {           # resolved at call time, so tests can patch them
        "yt-dlp": install_ytdlp,
        "ffmpeg": install_ffmpeg,
        "js-runtime": install_deno,
    }
    for key in keys:
        installer = installers.get(key)
        if installer is None:
            if progress:
                progress(key, "unknown component")
            continue
        if progress:
            progress(key, "installing")
        try:
            version = installer()
        except Exception as exc:  # noqa: BLE001 - report, keep going
            if progress:
                progress(key, "failed: %s" % exc)
            continue
        if progress:
            progress(key, "installed %s" % (version or ""))
        if key == "yt-dlp" and progress:
            # core/download.py already holds the yt-dlp it imported at startup,
            # so the new extractor is used only after a restart.
            progress(key, "restart to use the new version")
    return check_all()


class MaintenanceCheckWorker(QtCore.QThread):
    done_signal = QtCore.pyqtSignal(object)
    error_signal = QtCore.pyqtSignal(str)

    def run(self):
        try:
            components = check_all()
        except Exception as exc:  # noqa: BLE001 - never crash the thread
            self.error_signal.emit(str(exc))
            return
        self.done_signal.emit(components)


class DoctorCheckWorker(QtCore.QThread):
    """The Health view's data: component states plus the raw doctor report."""

    done_signal = QtCore.pyqtSignal(object)
    error_signal = QtCore.pyqtSignal(str)

    def run(self):
        from core.doctor import run_checks
        try:
            report = run_checks()
        except Exception as exc:  # noqa: BLE001 - report, never crash the thread
            self.error_signal.emit(str(exc))
            return
        try:
            components = check_all()
        except Exception:
            components = []
        self.done_signal.emit((components, report))


class MaintenanceRepairWorker(QtCore.QThread):
    progress_signal = QtCore.pyqtSignal(str, str)
    done_signal = QtCore.pyqtSignal(object)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, keys):
        super().__init__()
        self.keys = list(keys)

    def run(self):
        try:
            components = run_repairs(
                self.keys, progress=self.progress_signal.emit,
            )
        except Exception as exc:  # noqa: BLE001 - never crash the thread
            self.error_signal.emit(str(exc))
            return
        self.done_signal.emit(components)
