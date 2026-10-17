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


def test_records_the_renamed_file_not_the_raw_title(monkeypatch, tmp_path):
    """A generic site title is renamed on disk; the history names the artifact.

    Facebook reports a bare "Facebook" when cookies are sent, but the file is
    saved under the real title. The recorded entry must name the file that
    exists, or every Facebook row reads "Facebook" and matches nothing on disk.
    """
    site_named = tmp_path / "Facebook.mp4"
    site_named.write_text("data")

    class YDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True):
            if not download:
                return {"title": "My Holiday Video 2026"}
            return {"id": "123", "title": "Facebook", "ext": "mp4", "height": 720}

        def prepare_filename(self, info):
            return str(site_named)

    monkeypatch.setattr("yt_dlp.YoutubeDL", YDL)
    monkeypatch.setattr(
        "core.download.probe_media",
        lambda path, **k: {"vcodec": "h264", "acodec": "aac", "height": 720,
                           "container": "mp4"},
    )
    store = FakeStore()
    result = download_one(
        "https://a.com/1", str(tmp_path / "%(title)s.%(ext)s"),
        "MP4", False, None, history=store, source="single",
    )
    assert result.status == "ok"
    assert result.path == str(tmp_path / "My Holiday Video 2026.mp4")
    assert store.entries[0].title == "My Holiday Video 2026"
    assert store.entries[0].title != "Facebook"

