import threading

from PyQt5 import QtCore

from core.download import download_one
from core.queue import resolve_outtmpl


class QueueWorker(QtCore.QThread):
    progress_signal = QtCore.pyqtSignal(int)
    job_signal = QtCore.pyqtSignal(str, str, object)  # (job_id, state, QueueJob)
    finished_signal = QtCore.pyqtSignal(str)

    def __init__(self, queue, parent=None):
        super().__init__(parent)
        self.queue = queue
        self._cancel_event = threading.Event()

    def _executor(self, job):
        self.job_signal.emit(job.id, job.state, job)
        opts = job.options or {}
        outtmpl = resolve_outtmpl(opts)
        return download_one(
            job.url,
            outtmpl=outtmpl,
            output_type=opts.get("output_type", "MP4"),
            convert=opts.get("convert", False),
            target_resolution=opts.get("target_resolution", 1080),
            cookies_file=opts.get("cookies_file"),
            cancel=self._cancel_event.is_set,
            progress=self.progress_signal.emit,
        )

    def run(self):
        while True:
            if self.queue.paused:
                if self.queue.next_pending() is None:
                    break
                self.msleep(100)
                continue
            self._cancel_event.clear()
            job = self.queue.run_once(self._executor)
            if job is None:
                if self.queue.paused:
                    continue
                break
            self.job_signal.emit(job.id, job.state, job)
            self.queue.store.save()
        self.finished_signal.emit(self._summary())

    def _summary(self):
        jobs = self.queue.jobs
        done = sum(1 for j in jobs if j.state == "done")
        failed = sum(1 for j in jobs if j.state == "failed")
        cancelled = sum(1 for j in jobs if j.state == "cancelled")
        return f"Queue finished: {done} done, {failed} failed, {cancelled} cancelled"

    def pause(self):
        self.queue.pause()

    def resume(self):
        self.queue.resume()

    def cancel_current(self):
        self._cancel_event.set()

    def cancel_all(self):
        self._cancel_event.set()
        self.queue.cancel_all()
