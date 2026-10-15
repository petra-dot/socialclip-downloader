import json
import os

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


def test_save_tmp_path_is_unique_per_process(tmp_path, monkeypatch):
    seen = []
    real_replace = os.replace

    def spy(src, dst):
        seen.append(os.path.basename(src))
        return real_replace(src, dst)

    monkeypatch.setattr("core.queue.os.replace", spy)
    store = QueueStore(str(tmp_path / "q.json"))
    store.save()
    assert seen and seen[0] != "q.json.tmp"
    assert str(os.getpid()) in seen[0]

def test_remove_job_deletes_a_pending_job():
    from core.queue import Queue
    q = Queue()
    job = q.add("https://a.com/1", {})
    assert q.remove_job(job.id) is True
    assert q.jobs == []


def test_remove_job_refuses_a_running_job():
    from core.queue import Queue
    q = Queue()
    job = q.add("https://a.com/1", {})
    job.state = "running"
    assert q.remove_job(job.id) is False
    assert len(q.jobs) == 1


def test_remove_job_unknown_id_returns_false():
    from core.queue import Queue
    q = Queue()
    q.add("https://a.com/1", {})
    assert q.remove_job("nope") is False
    assert len(q.jobs) == 1


def test_can_remove_only_blocks_running():
    from core.queue import can_remove
    for state in ("pending", "done", "failed", "cancelled", "paused"):
        assert can_remove(state) is True, state
    assert can_remove("running") is False


def test_job_title_defaults_to_empty():
    from core.queue import QueueJob
    assert QueueJob(url="u").title == ""


def test_add_accepts_a_title():
    from core.queue import Queue
    queue = Queue()
    job = queue.add("https://youtu.be/x", title="My Video")
    assert job.title == "My Video"


def test_store_round_trip_without_title_is_backward_compatible(tmp_path):
    import json
    from core.queue import QueueStore
    path = tmp_path / "queue.json"
    path.write_text(json.dumps({
        "version": 1, "paused": False,
        "jobs": [{"id": "a", "url": "https://youtu.be/x", "state": "pending"}],
    }))
    store = QueueStore(str(path))
    store.load()
    assert store.jobs[0].title == ""


def test_store_persists_title(tmp_path):
    from core.queue import Queue, QueueStore
    path = str(tmp_path / "queue.json")
    queue = Queue(QueueStore(path))
    queue.add("https://youtu.be/x", title="My Video")
    queue.store.save()
    again = QueueStore(path)
    again.load()
    assert again.jobs[0].title == "My Video"


def test_claim_next_marks_running_and_counts_attempt():
    q = Queue()
    job = q.add("https://a.com/1", {})
    claimed = q.claim_next()
    assert claimed is job
    assert job.state == "running"
    assert job.attempts == 1
    assert q.claim_next() is None


def test_claim_next_returns_none_when_paused():
    q = Queue()
    q.add("https://a.com/1", {})
    q.pause()
    assert q.claim_next() is None


def test_apply_result_ok_sets_done_fields():
    q = Queue()
    job = q.add("https://a.com/1", {})
    job.state = "running"
    result = DownloadResult(status="ok", url=job.url, path="C:/out.mp4",
                            bytes=10, height=1080, message="done")
    q.apply_result(job, result)
    assert job.state == "done"
    assert job.path == "C:/out.mp4"
    assert job.bytes == 10
    assert job.height == 1080
    assert job.message == "done"


def test_apply_result_cancelled():
    q = Queue()
    job = q.add("https://a.com/1", {})
    job.state = "running"
    result = DownloadResult(status="error", error_category="cancelled",
                            message="Cancelled.")
    q.apply_result(job, result)
    assert job.state == "cancelled"


def test_apply_result_generic_failure():
    q = Queue()
    job = q.add("https://a.com/1", {})
    job.state = "running"
    result = DownloadResult(status="error", error_category="network",
                            message="No network.")
    q.apply_result(job, result)
    assert job.state == "failed"
    assert job.message == "No network."


def test_apply_result_non_result_is_failed():
    q = Queue()
    job = q.add("https://a.com/1", {})
    job.state = "running"
    q.apply_result(job, None)
    assert job.state == "failed"
    assert job.message == "executor returned no result"


def test_skipped_is_a_terminal_state():
    from core.queue import STATES, TERMINAL_STATES
    assert "skipped" in STATES
    assert "skipped" in TERMINAL_STATES


def test_apply_result_maps_skipped():
    q = Queue()
    job = q.add("https://a.com/1", {})
    job.state = "running"
    result = DownloadResult(status="error", error_category="skipped",
                            message="Already downloaded; skipped.")
    q.apply_result(job, result)
    assert job.state == "skipped"
    assert job.message == "Already downloaded; skipped."


def test_cancel_all_leaves_skipped_jobs_alone():
    q = Queue()
    a = q.add("https://a.com/1", {})
    b = q.add("https://b.com/2", {})
    a.state = "skipped"
    q.cancel_all()
    assert a.state == "skipped"
    assert b.state == "cancelled"
