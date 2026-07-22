import datetime
import os

from PyQt5 import QtCore

from dlqueue.models import QueueItem, DownloadStatus


class QueueManager(QtCore.QObject):
    item_added = QtCore.pyqtSignal(str)
    status_changed = QtCore.pyqtSignal(str, str)
    progress = QtCore.pyqtSignal(str, int)
    queue_finished = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self._items = []
        self._max_concurrent = 2
        self._paused = False
        self._active_workers = {}

    @property
    def items(self):
        return list(self._items)

    def set_max_concurrent(self, n: int):
        self._max_concurrent = max(1, n)

    def enqueue(self, url: str, options: dict = None) -> str:
        item = QueueItem(url, options)
        item.created_at = datetime.datetime.now()
        self._items.append(item)
        self.item_added.emit(item.id)
        self._try_dispatch()
        return item.id

    def cancel(self, item_id: str):
        for item in self._items:
            if item.id == item_id and item.status in (DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING):
                if item_id in self._active_workers:
                    self._active_workers[item_id].requestInterruption()
                    del self._active_workers[item_id]
                item.status = DownloadStatus.CANCELLED
                self.status_changed.emit(item_id, "cancelled")
                self._try_dispatch()
                return

    def retry(self, item_id: str):
        for item in self._items:
            if item.id == item_id and item.status == DownloadStatus.FAILED:
                item.status = DownloadStatus.QUEUED
                item.retries += 1
                item.error_message = ""
                self.status_changed.emit(item_id, "queued")
                self._try_dispatch()
                return

    def move_up(self, item_id: str):
        for i, item in enumerate(self._items):
            if item.id == item_id and i > 0:
                self._items[i], self._items[i - 1] = self._items[i - 1], self._items[i]
                return

    def move_down(self, item_id: str):
        for i, item in enumerate(self._items):
            if item.id == item_id and i < len(self._items) - 1:
                self._items[i], self._items[i + 1] = self._items[i + 1], self._items[i]
                return

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False
        self._try_dispatch()

    def clear_finished(self):
        self._items = [item for item in self._items if item.status in (DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING)]

    def _try_dispatch(self):
        if self._paused:
            return
        active = sum(1 for s in self._active_workers.values() if s.isRunning())
        slots = self._max_concurrent - active
        if slots <= 0:
            return
        for item in self._items:
            if slots <= 0:
                break
            if item.status == DownloadStatus.QUEUED:
                item.status = DownloadStatus.DOWNLOADING
                self.status_changed.emit(item.id, "downloading")
                self._start_worker(item)
                slots -= 1

    def _start_worker(self, item):
        from workers.download_worker import DownloadWorker

        options = item.options
        save_dir = options.get("save_dir", "")
        os.makedirs(save_dir, exist_ok=True)
        base = options.get("filename", "%(title)s")
        outtmpl = os.path.join(save_dir, base + ".%(ext)s")

        cf = options.get("cookies_file", "")
        if not cf:
            from sites.cookies import get_cookie_path
            cf = get_cookie_path(item.url)

        worker = DownloadWorker(
            item.url, outtmpl,
            convert=options.get("convert", False),
            target_resolution=options.get("resolution", 1080),
            output_type=options.get("output_type", "MP4"),
            cookies_file=cf or None,
        )
        worker.progress_signal.connect(lambda p, iid=item.id: self.progress.emit(iid, p))
        worker.finished_signal.connect(lambda msg, iid=item.id: self._on_worker_finished(iid, msg))
        self._active_workers[item.id] = worker
        worker.start()

    def _on_worker_finished(self, item_id: str, msg: str):
        if item_id in self._active_workers:
            del self._active_workers[item_id]
        for item in self._items:
            if item.id == item_id:
                if "Error" in msg or "failed" in msg.lower():
                    item.status = DownloadStatus.FAILED
                    item.error_message = msg
                    self.status_changed.emit(item_id, "failed")
                else:
                    item.status = DownloadStatus.COMPLETED
                    self.status_changed.emit(item_id, "completed")
                break
        self._try_dispatch()
        if not any(i.status in (DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING) for i in self._items):
            self.queue_finished.emit()
