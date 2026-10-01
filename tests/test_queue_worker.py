import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets  # noqa: E402

from core.manifest import DownloadResult  # noqa: E402
from core.queue import Queue  # noqa: E402
from workers.queue_worker import QueueWorker  # noqa: E402


def test_worker_drains_queue_and_emits_states(monkeypatch):
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    q = Queue()
    q.add("https://a.com/1", {})
    q.add("https://b.com/2", {})

    def fake_download_one(url, **kw):
        return DownloadResult(status="ok", url=url, path="C:/o.mp4", message="ok")

    monkeypatch.setattr("workers.queue_worker.download_one", fake_download_one)

    seen = []
    worker = QueueWorker(q)
    worker.job_signal.connect(lambda jid, state, job: seen.append(state))
    worker.run()  # synchronous drain

    assert seen.count("running") == 2
    assert seen.count("done") == 2
    assert all(j.state == "done" for j in q.jobs)
