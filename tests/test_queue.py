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


def test_store_jobs_null_loads_empty(tmp_path):
    path = tmp_path / "queue.json"
    path.write_text(json.dumps({"version": 1, "jobs": None}))
    store = QueueStore(str(path))
    store.load()
    assert store.to_dict()["jobs"] == []


def test_store_jobs_dict_loads_empty(tmp_path):
    path = tmp_path / "queue.json"
    path.write_text(json.dumps({"version": 1, "jobs": {"a": 1}}))
    store = QueueStore(str(path))
    store.load()
    assert store.to_dict()["jobs"] == []


def test_store_skips_bad_job_keeps_good(tmp_path):
    path = tmp_path / "queue.json"
    path.write_text(json.dumps({
        "version": 1,
        "jobs": [
            {"id": "good", "url": "https://a.com/1"},
            {"id": "bad", "bogus_key": 1},
        ],
    }))
    store = QueueStore(str(path))
    store.load()
    assert len(store.jobs) == 1
    assert store.jobs[0].url == "https://a.com/1"


def test_store_bad_load_does_not_delete_file(tmp_path):
    path = tmp_path / "queue.json"
    path.write_text(json.dumps({"version": 1, "jobs": {"a": 1}}))
    store = QueueStore(str(path))
    store.load()
    assert path.exists()


def test_run_once_empty_queue_returns_none():
    q = Queue()
    assert q.run_once(lambda j: None) is None


def test_run_once_non_result_return_is_failed():
    q = Queue()
    q.add("https://a.com/1", {})
    done = q.run_once(lambda j: {"status": "ok"})
    assert done.state == "failed"
    assert done.message == "executor returned no result"


def test_run_once_records_generic_failure():
    q = Queue()
    q.add("https://a.com/1", {})

    def executor(j):
        return DownloadResult(status="error", url=j.url,
                              error_category="network", message="No network.")

    done = q.run_once(executor)
    assert done.state == "failed"
    assert done.message == "No network."


def test_cancel_job_marks_non_terminal_cancelled():
    q = Queue()
    job = q.add("https://a.com/1", {})
    assert q.cancel_job(job.id) is True
    assert job.state == "cancelled"
    assert q.cancel_job(job.id) is False


def test_store_coerces_string_int_fields(tmp_path):
    path = tmp_path / "queue.json"
    path.write_text(json.dumps({
        "version": 1,
        "jobs": [{"id": "a", "url": "https://a.com/1",
                  "attempts": "x", "bytes": "y", "height": "z"}],
    }))
    q = Queue(QueueStore(str(path)))
    q.store.load()
    assert q.jobs[0].attempts == 0
    assert q.jobs[0].bytes == 0
    assert q.jobs[0].height == 0


def test_run_once_does_not_raise_on_corrupt_job(tmp_path):
    path = tmp_path / "queue.json"
    path.write_text(json.dumps({
        "version": 1,
        "jobs": [{"id": "a", "url": "https://a.com/1",
                  "attempts": "x", "bytes": "y"}],
    }))
    q = Queue(QueueStore(str(path)))
    q.store.load()

    def executor(j):
        return DownloadResult(status="ok", url=j.url)

    done = q.run_once(executor)
    assert done.state == "done"
    assert done.attempts == 1
