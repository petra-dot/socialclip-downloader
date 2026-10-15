"""Run component checks and repairs off the UI thread."""

from PyQt5 import QtCore

from core.maintenance import (
    check_all,
    install_deno,
    install_ffmpeg,
    install_ytdlp,
)

# component key -> installer attribute name. "js-runtime" is satisfied by a
# managed deno. The name is resolved through the module globals at call time,
# not frozen into a {key: function} dict at import: a module-scope dict would
# bind the original installers, so a test monkeypatching `install_ytdlp` would
# have no effect.
INSTALLERS = {
    "yt-dlp": "install_ytdlp",
    "ffmpeg": "install_ffmpeg",
    "js-runtime": "install_deno",
}


def run_repairs(keys, progress=None):
    """Install each requested component, then re-check. Returns the components.

    A failure is reported through `progress` and does not stop the others: one
    broken component must not block the rest. `progress` is called once per
    component with `(key, detail)`, matching `MaintenanceRepairWorker`'s
    two-argument `progress_signal`.
    """
    for key in keys:
        name = INSTALLERS.get(key)
        installer = globals().get(name) if name else None
        if installer is None:
            continue
        try:
            version = installer()
        except Exception as exc:  # noqa: BLE001 - report, keep going
            if progress:
                progress(key, "failed: %s" % exc)
            continue
        if progress:
            progress(key, "installed %s" % (version or ""))
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
