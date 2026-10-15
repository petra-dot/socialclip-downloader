import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import replace

from PyQt5 import QtCore

from core.download import download_one
from core.queue import resolve_outtmpl

DEFAULT_JOBS = 3
MAX_JOBS = 8


class QueueWorker(QtCore.QThread):
    progress_signal = QtCore.pyqtSignal(str, object)  # (job_id, Progress)
    job_signal = QtCore.pyqtSignal(str, str, object)  # (job_id, state, QueueJob)
    finished_signal = QtCore.pyqtSignal(str)

    def __init__(self, queue, jobs=DEFAULT_JOBS, archive=None, parent=None):
        super().__init__(parent)
        self.queue = queue
        self.jobs = max(1, min(int(jobs), MAX_JOBS))
        self.archive = archive
        self._cancel_events = {}
        self._cancel_all = threading.Event()
        self._lock = threading.Lock()

    def _download(self, job, event):
        opts = job.options or {}
        outtmpl = resolve_outtmpl(opts)
        return download_one(
            job.url,
            outtmpl=outtmpl,
            output_type=opts.get("output_type", "MP4"),
            convert=opts.get("convert", False),
            target_resolution=opts.get("target_resolution", 1080),
            cookies_file=opts.get("cookies_file"),
            cookies_from_browser=opts.get("cookies_from_browser"),
            cancel=event.is_set,
            progress=lambda p: self.progress_signal.emit(job.id, p),
            subtitles=opts.get("subtitles", "off"),
            archive=self.archive,
        )

    def _emit_running(self, job):
        self.job_signal.emit(job.id, job.state, replace(job))

    def _finish(self, job, future):
        try:
            result = future.result()
        except Exception as exc:  # noqa: BLE001 - one job must not kill the pool
            job.state = "failed"
            job.message = str(exc)
            self.job_signal.emit(job.id, job.state, replace(job))
            self.queue.store.save()
            return
        self.queue.apply_result(job, result)
        self.job_signal.emit(job.id, job.state, replace(job))
        self.queue.store.save()

    def run(self):
        with ThreadPoolExecutor(max_workers=self.jobs) as pool:
            pending = {}
            while True:
                if self._cancel_all.is_set():
                    self.queue.cancel_all()
                    self.queue.store.save()
                    break
                if not self.queue.paused:
                    while len(pending) < self.jobs:
                        job = self.queue.claim_next()
                        if job is None:
                            break
                        event = threading.Event()
                        with self._lock:
                            self._cancel_events[job.id] = event
                        self._emit_running(job)
                        pending[pool.submit(self._download, job, event)] = job
                if not pending:
                    if self.queue.paused and self.queue.next_pending() is not None:
                        self.msleep(100)
                        continue
                    break
                done, _pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    self._finish(pending.pop(future), future)
        self.finished_signal.emit(self._summary())

    def _summary(self):
        jobs = self.queue.jobs
        done = sum(1 for j in jobs if j.state == "done")
        failed = sum(1 for j in jobs if j.state == "failed")
        cancelled = sum(1 for j in jobs if j.state == "cancelled")
        skipped = sum(1 for j in jobs if j.state == "skipped")
        return (f"Queue finished: {done} done, {failed} failed, "
                f"{cancelled} cancelled, {skipped} skipped")

    def pause(self):
        self.queue.pause()

    def resume(self):
        self.queue.resume()

    def cancel_job(self, job_id):
        with self._lock:
            event = self._cancel_events.get(job_id)
        if event is not None:
            event.set()

    def cancel_all(self):
        self._cancel_all.set()
        with self._lock:
            events = list(self._cancel_events.values())
        for event in events:
            event.set()
