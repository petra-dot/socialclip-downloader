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


def test_cancel_current_stops_only_active_job(monkeypatch):
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    q = Queue()
    q.add("https://a.com/1", {})
    q.add("https://b.com/2", {})
    q.add("https://c.com/3", {})

    worker = QueueWorker(q)
    calls = []

    def fake_download_one(url, **kw):
        calls.append(url)
        if len(calls) == 1:
            worker.cancel_current()
            assert kw["cancel"]() is True
            return DownloadResult(
                status="error",
                error_category="cancelled",
                url=url,
                message="Cancelled.",
            )
        assert kw["cancel"]() is False
        return DownloadResult(status="ok", url=url, path="C:/o.mp4", message="ok")

    monkeypatch.setattr("workers.queue_worker.download_one", fake_download_one)
    worker.run()

    assert [j.state for j in q.jobs] == ["cancelled", "done", "done"]


def test_executor_ignores_reserved_option_keys(monkeypatch):
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    q = Queue()
    q.add(
        "https://a.com/1",
        {"cancel": "bogus", "progress": "bogus", "outtmpl": "tmpl"},
    )

    captured = {}

    def fake_download_one(url, **kw):
        captured.update(kw)
        return DownloadResult(status="ok", url=url, path="C:/o.mp4", message="ok")

    monkeypatch.setattr("workers.queue_worker.download_one", fake_download_one)
    worker = QueueWorker(q)
    worker.run()

    assert q.jobs[0].state == "done"
    assert callable(captured["cancel"])
    assert callable(captured["progress"])
    assert captured["outtmpl"] == "tmpl"
