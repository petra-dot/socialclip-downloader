import json

from core.manifest import DownloadResult
from core.queue import Queue, QueueStore


def test_add_and_next_pending_is_fifo():
    q = Queue()
    a = q.add("https://a.com/1", {})
    b = q.add("https://b.com/2", {})
    assert a.state == "pending"
    assert q.next_pending().id == a.id
    a.state = "done"
    assert q.next_pending().id == b.id


def test_run_once_records_success():
    q = Queue()
    job = q.add("https://a.com/1", {})

    def executor(j):
        return DownloadResult(status="ok", url=j.url, path="C:/out.mp4", bytes=10)

    done = q.run_once(executor)
    assert done.id == job.id
    assert done.state == "done"
    assert done.path == "C:/out.mp4"
    assert done.attempts == 1


def test_run_once_records_failure_without_raising():
    q = Queue()
    q.add("https://a.com/1", {})

    def executor(j):
        raise RuntimeError("boom")

    done = q.run_once(executor)
    assert done.state == "failed"
    assert "boom" in done.message


def test_run_once_records_cancelled():
    q = Queue()
    q.add("https://a.com/1", {})

    def executor(j):
        return DownloadResult(status="error", url=j.url,
                              error_category="cancelled", message="Cancelled.")

    done = q.run_once(executor)
    assert done.state == "cancelled"


def test_pause_blocks_run_once():
    q = Queue()
    q.add("https://a.com/1", {})
    q.pause()
    assert q.paused is True
    assert q.run_once(lambda j: None) is None
    q.resume()
    assert q.paused is False


def test_cancel_all_marks_pending_cancelled():
    q = Queue()
    a = q.add("https://a.com/1", {})
    b = q.add("https://b.com/2", {})
    q.cancel_all()
    assert a.state == "cancelled"
    assert b.state == "cancelled"


def test_store_round_trip(tmp_path):
    path = tmp_path / "queue.json"
    q = Queue(QueueStore(str(path)))
    q.add("https://a.com/1", {"output_type": "MP3"})
    q.store.save()

    reopened = Queue(QueueStore(str(path)))
    reopened.store.load()
    assert len(reopened.jobs) == 1
    assert reopened.jobs[0].url == "https://a.com/1"
    assert reopened.jobs[0].options["output_type"] == "MP3"


def test_store_unknown_version_loads_empty(tmp_path):
    path = tmp_path / "queue.json"
    path.write_text(json.dumps({"version": 999, "jobs": [{"id": "x"}]}))
    store = QueueStore(str(path))
    store.load()
    assert store.to_dict()["jobs"] == []


def test_store_missing_file_loads_empty(tmp_path):
    store = QueueStore(str(tmp_path / "nope.json"))
    store.load()
    assert store.to_dict()["jobs"] == []


def test_store_corrupt_file_loads_empty(tmp_path):
    path = tmp_path / "queue.json"
    path.write_text("{not json")
    store = QueueStore(str(path))
    store.load()
    assert store.to_dict()["jobs"] == []
