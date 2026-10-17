import json

from core.history import (
    HistoryEntry, HistoryStore, entry_from_result, filter_entries, record,
    search, sort_entries, status_of,
)
from core.manifest import DownloadResult


def _entry(**kw):
    base = dict(id="a", title="Clip", url="https://a.com/1", platform="YouTube",
                path="C:/v/clip.mp4", bytes=100, extension="mp4", height=1080,
                duration_seconds=30, source="single", created_at="2026-01-01")
    base.update(kw)
    return HistoryEntry(**base)


def test_entry_from_result_maps_a_video_result():
    result = DownloadResult(status="ok", url="https://a.com/1", platform="YouTube",
                            title="Clip", path="C:/v/clip.mp4", extension="mp4",
                            height=1080, bytes=1234, duration_seconds=42)
    entry = entry_from_result(result, source="queue")
    assert entry.title == "Clip"
    assert entry.platform == "YouTube"
    assert entry.path == "C:/v/clip.mp4"
    assert entry.bytes == 1234
    assert entry.height == 1080
    assert entry.duration_seconds == 42
    assert entry.source == "queue"
    assert entry.id
    assert entry.created_at


def test_entry_from_result_handles_an_audio_result_with_no_resolution():
    result = DownloadResult(status="ok", url="https://a.com/1", title="Song",
                            path="C:/v/song.mp3", extension="mp3")
    entry = entry_from_result(result, source="single")
    assert entry.extension == "mp3"
    assert entry.height == 0
    assert entry.bytes == 0


def test_entry_from_result_tolerates_a_missing_title_and_url():
    entry = entry_from_result(DownloadResult(status="ok", path="C:/v/x.mp4"))
    assert entry.title == ""
    assert entry.url == ""
    assert entry.platform == ""


def test_status_of_reports_present_absent_and_deleted():
    assert status_of(_entry(), exists=lambda p: True) == "ok"
    assert status_of(_entry(), exists=lambda p: False) == "missing"
    assert status_of(_entry(removed_at="2026-01-02")) == "deleted"
    assert status_of(_entry(path="")) == "missing"


def test_search_matches_the_title_case_insensitively():
    entries = [_entry(id="1", title="Holiday Video"), _entry(id="2", title="Song")]
    assert [e.id for e in search(entries, "holiday")] == ["1"]
    assert search(entries, "nope") == []
    assert len(search(entries, "")) == 2


def test_filter_entries_by_platform_and_extension():
    entries = [
        _entry(id="1", platform="YouTube", extension="mp4"),
        _entry(id="2", platform="TikTok", extension="mp3"),
    ]
    assert [e.id for e in filter_entries(entries, platform="TikTok")] == ["2"]
    assert [e.id for e in filter_entries(entries, extension="MP4")] == ["1"]
    assert [e.id for e in filter_entries(entries, platform="TikTok",
                                         extension="mp3")] == ["2"]
    assert len(filter_entries(entries)) == 2


def test_sort_entries_by_bytes_both_ways():
    entries = [_entry(id="1", bytes=300), _entry(id="2", bytes=100)]
    assert [e.id for e in sort_entries(entries, "bytes")] == ["2", "1"]
    assert [e.id for e in sort_entries(entries, "bytes", descending=True)] == ["1", "2"]


def test_sort_entries_by_status_uses_the_supplied_map():
    entries = [_entry(id="1"), _entry(id="2")]
    order = sort_entries(entries, "status", statuses={"1": "ok", "2": "missing"})
    assert [e.id for e in order] == ["1", "2"]


def test_store_round_trips_through_a_file(tmp_path):
    path = str(tmp_path / "history.json")
    store = HistoryStore(path)
    store.add(HistoryEntry(title="One", path="C:/v/one.mp4"))
    again = HistoryStore(path)
    again.load()
    assert [e.title for e in again.entries()] == ["One"]


def test_store_keeps_an_entry_with_an_unknown_key(tmp_path):
    path = tmp_path / "history.json"
    path.write_text(json.dumps({
        "version": 1,
        "entries": [{"id": "x", "title": "Kept", "future_field": 42}],
    }), encoding="utf-8")
    store = HistoryStore(str(path))
    store.load()
    assert [e.title for e in store.entries()] == ["Kept"]


def test_store_loads_empty_from_a_corrupt_file(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("{ not json", encoding="utf-8")
    store = HistoryStore(str(path))
    store.load()
    assert store.entries() == []


def test_store_loads_empty_from_a_wrong_version(tmp_path):
    path = tmp_path / "history.json"
    path.write_text(json.dumps({"version": 99, "entries": [{"title": "x"}]}),
                    encoding="utf-8")
    store = HistoryStore(str(path))
    store.load()
    assert store.entries() == []


def test_remove_and_mark_deleted_report_their_result(tmp_path):
    path = str(tmp_path / "history.json")
    store = HistoryStore(path)
    entry = store.add(HistoryEntry(title="One", path="C:/v/one.mp4"))
    assert store.mark_deleted(entry.id) is True
    assert store.mark_deleted("nope") is False
    assert store.remove("nope") is False
    assert store.remove(entry.id) is True
    assert store.entries() == []


def test_save_writes_no_partial_file(tmp_path):
    path = str(tmp_path / "history.json")
    store = HistoryStore(path)
    store.add(HistoryEntry(title="One"))
    store.save()
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
    data = json.loads((tmp_path / "history.json").read_text(encoding="utf-8"))
    assert data["version"] == 1


def test_record_swallows_a_failing_store():
    class Boom:
        def add(self, entry):
            raise OSError("disk full")

    assert record(Boom(), HistoryEntry()) is None
    assert record(None, HistoryEntry()) is None


def test_default_store_uses_the_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("SOCIALCLIP_HISTORY", str(tmp_path / "history.json"))
    store = HistoryStore()
    assert store.path == str(tmp_path / "history.json")
