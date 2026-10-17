"""Probe one file for its container and codecs, off the UI thread.

`ffprobe` is a subprocess with a cold-start cost: creating the process, and on
Windows the first read of the file. The History detail pane shows the result,
so the probe must not block the click that asked for it. A runnable on the
shared thread pool keeps the UI responsive and bounds how many probes run at
once.
"""

from PyQt5 import QtCore

from core.probe import probe_media


class _Signals(QtCore.QObject):
    done = QtCore.pyqtSignal(str, dict)


class ProbeWorker(QtCore.QRunnable):
    """Run `probe_media` for one path; emit `signals.done(path, info)`.

    `info` is empty on any failure, so the caller always gets an answer.
    """

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.signals = _Signals()

    def run(self):
        try:
            info = probe_media(self.path) or {}
        except Exception:
            info = {}
        self.signals.done.emit(self.path, info)
