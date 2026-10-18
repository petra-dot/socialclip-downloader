"""Drain a ConvertQueue one job at a time, off the UI thread."""

from PyQt5 import QtCore

from core.convert_queue import STATUS_CANCELLED, TERMINAL_STATES


class ConvertQueueWorker(QtCore.QThread):
    job_signal = QtCore.pyqtSignal(object)
    finished_signal = QtCore.pyqtSignal(str)

    def __init__(self, queue, store=None):
        super().__init__()
        self.queue = queue
        self.store = store
        self._cancelled = set()
        self._cancelling = False

    def cancel(self, job_id):
        """Cancel a running job. It stops between files, not mid-encode."""
        self._cancelled.add(job_id)

    def cancel_all(self):
        self._cancelling = True

    def _save(self):
        if self.store is not None:
            self.store.jobs = list(self.queue.jobs)
            self.store.save()

    def _emit(self, job):
        self.job_signal.emit({
            "id": job.id, "state": job.state, "path": job.path,
            "message": job.message, "output_path": job.output_path,
        })

    def run(self):
        from core.convert import convert_file

        done = 0
        while not self._cancelling:
            job = self.queue.claim_next()
            if job is None:
                break
            self._emit(job)
            if job.id in self._cancelled:
                job.state = STATUS_CANCELLED
                job.message = "Cancelled."
                done += 1
                self._save()
                self._emit(job)
                continue
            try:
                result = convert_file(
                    job.path, target_format=job.target_format,
                    target_resolution=job.resolution or None,
                    copy_streams=job.copy_streams,
                )
            except Exception as exc:  # noqa: BLE001 - a bad file must not stop the batch
                from core.manifest import error_result
                result = error_result("other", str(exc), "")
            self.queue.apply_result(job.id, result)
            done += 1
            self._save()
            self._emit(job)
        self.finished_signal.emit("Converted %d file(s)." % done)
