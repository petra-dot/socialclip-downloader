from core.convert_queue import (
    ConvertQueue, ConvertStore, ConvertJob, STATUS_DONE, STATUS_FAILED,
    STATUS_PENDING, STATUS_RUNNING, TERMINAL_STATES,
)
from core.manifest import DownloadResult

OPTIONS = {"target_format": "mp4", "resolution": 1080, "copy_streams": None}


def _queue(tmp_path, jobs=None):
    store = ConvertStore(str(tmp_path / "convert.json"))
    queue = ConvertQueue(store)
    queue.jobs[:] = jobs or []
    return queue


def test_add_bakes_options_and_skips_duplicate_paths(tmp_path):
    queue = _queue(tmp_path)
    added = queue.add(["C:/v/a.mp4", "C:/v/b.mov"], OPTIONS)
    assert [job.path for job in added] == ["C:/v/a.mp4", "C:/v/b.mov"]
    assert added[0].target_format == "mp4"
    assert added[0].resolution == 1080
    assert added[0].state == STATUS_PENDING
    again = queue.add(["C:/v/a.mp4"], OPTIONS)
    assert again == []


def test_claim_next_returns_the_first_pending_and_marks_it_running(tmp_path):
    queue = _queue(tmp_path)
    queue.add(["C:/v/a.mp4", "C:/v/b.mp4"], OPTIONS)
    first = queue.claim_next()
    assert first.path == "C:/v/a.mp4"
    assert first.state == STATUS_RUNNING
    assert queue.claim_next().path == "C:/v/b.mp4"
    assert queue.claim_next() is None


def test_apply_result_maps_ok_failed_and_cancelled(tmp_path):
    queue = _queue(tmp_path)
    ok, bad, stopped = queue.add(["a", "b", "c"], OPTIONS)
    queue.apply_result(ok.id, DownloadResult(status="ok", path="C:/v/a.mp3"))
    assert ok.state == STATUS_DONE and ok.output_path == "C:/v/a.mp3"
    queue.apply_result(bad.id, DownloadResult(status="error", message="boom"))
    assert bad.state == STATUS_FAILED and bad.message == "boom"
    queue.apply_result(stopped.id, DownloadResult(status="error",
                                                  error_category="cancelled"))
    assert stopped.state == "cancelled"


def test_set_options_touches_pending_only(tmp_path):
    queue = _queue(tmp_path)
    first, second = queue.add(["a", "b"], OPTIONS)
    second.state = STATUS_RUNNING
    changed = queue.set_options([first.id, second.id], {"target_format": "mp3"})
    assert changed == 1
    assert first.target_format == "mp3"
    assert second.target_format == "mp4"


def test_remove_refuses_a_running_job(tmp_path):
    queue = _queue(tmp_path)
    job, = queue.add(["a"], OPTIONS)
    job.state = STATUS_RUNNING
    assert queue.remove(job.id) is False
    job.state = STATUS_PENDING
    assert queue.remove(job.id) is True


def test_retry_failed_and_clear_finished(tmp_path):
    queue = _queue(tmp_path)
    job, = queue.add(["a"], OPTIONS)
    job.state = STATUS_FAILED
    assert queue.retry_failed() == 1
    assert job.state == STATUS_PENDING
    job.state = STATUS_DONE
    assert queue.clear_finished() == 1
    assert queue.jobs == []


def test_store_round_trips_and_keeps_an_unknown_key(tmp_path):
    path = tmp_path / "convert.json"
    path.write_text('{"version": 1, "jobs": [{"id": "x", "path": "a", "future": 1}]}',
                    encoding="utf-8")
    store = ConvertStore(str(path))
    store.load()
    assert [job.path for job in store.jobs] == ["a"]
    store.save()
    reloaded = ConvertStore(str(path))
    reloaded.load()
    assert [job.path for job in reloaded.jobs] == ["a"]


def test_store_loads_empty_from_a_corrupt_file(tmp_path):
    path = tmp_path / "convert.json"
    path.write_text("{ not json", encoding="utf-8")
    store = ConvertStore(str(path))
    store.load()
    assert store.jobs == []
