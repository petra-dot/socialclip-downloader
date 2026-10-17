"""Recording is wired into download_one. yt-dlp is never called."""
from core.download import download_one
from core.manifest import DownloadResult, error_result


class FakeStore:
    def __init__(self):
        self.entries = []

    def add(self, entry):
        self.entries.append(entry)
        return entry


def _fake_result(tmp_path):
    out = tmp_path / "clip.mp4"
    out.write_bytes(b"x" * 10)
    return DownloadResult(status="ok", url="https://a.com/1", platform="YouTube",
                          title="Clip", path=str(out), extension="mp4", height=720)


def test_download_one_records_a_success(monkeypatch, tmp_path):
    monkeypatch.setattr("core.download._run_download",
                        lambda *a, **k: _fake_result(tmp_path))
    store = FakeStore()
    result = download_one("https://a.com/1", str(tmp_path / "%(title)s.%(ext)s"),
                          "MP4", False, None, history=store, source="single")
    assert result.status == "ok"
    assert len(store.entries) == 1
    assert store.entries[0].title == "Clip"
    assert store.entries[0].source == "single"


def test_download_one_records_nothing_on_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "core.download._run_download",
        lambda *a, **k: error_result("network", "boom", "https://a.com/1"),
    )
    store = FakeStore()
    result = download_one("https://a.com/1", str(tmp_path / "%(title)s.%(ext)s"),
                          "MP4", False, None, history=store, source="queue")
    assert result.status == "error"
    assert store.entries == []


def test_download_one_works_with_no_store(monkeypatch, tmp_path):
    monkeypatch.setattr("core.download._run_download",
                        lambda *a, **k: _fake_result(tmp_path))
    result = download_one("https://a.com/1", str(tmp_path / "%(title)s.%(ext)s"),
                          "MP4", False, None)
    assert result.status == "ok"
