import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets  # noqa: E402

from core.manifest import DownloadResult  # noqa: E402
from workers.batch_worker import BatchDownloadWorker  # noqa: E402


def test_batch_emits_item_states(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    seen = []

    def fake_download_one(url, **kw):
        if "bad" in url:
            return DownloadResult(status="error", url=url, message="boom",
                                  error_category="other")
        return DownloadResult(status="ok", url=url, path="C:/o.mp4", message="ok")

    monkeypatch.setattr("workers.batch_worker.download_one", fake_download_one)

    worker = BatchDownloadWorker(
        ["https://a.com/1", "https://bad.com/2"], "C:/out", "MP4", 1080, ""
    )
    worker.item_signal.connect(lambda i, s, r: seen.append((i, s)))
    worker.run()  # synchronous

    assert (0, "running") in seen and (0, "done") in seen
    assert (1, "running") in seen and (1, "failed") in seen
    assert seen[-1] == (1, "failed")


def test_batch_emits_cancelled_for_skipped(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    seen = []

    def fake_download_one(url, **kw):
        return DownloadResult(status="ok", url=url, path="C:/o.mp4", message="ok")

    monkeypatch.setattr("workers.batch_worker.download_one", fake_download_one)

    worker = BatchDownloadWorker(
        ["https://a.com/1", "https://a.com/2"], "C:/out", "MP4", 1080, ""
    )
    worker.item_signal.connect(lambda i, s, r: seen.append((i, s)))
    worker.cancel()
    worker.run()

    assert seen == [(0, "cancelled"), (1, "cancelled")]
