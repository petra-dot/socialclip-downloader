from core.download import download_one


class FakeYDL:
    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True):
        return {"id": "x", "title": "T", "height": 1080, "duration": 10,
                "ext": "mp4", "requested_downloads": [{"filepath": "D:/a.mp4"}]}

    def prepare_filename(self, info):
        return "D:/a.mp4"


def test_download_one_returns_ok_result(monkeypatch, tmp_path):
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDL)
    monkeypatch.setattr("core.download.os.path.exists", lambda p: True)
    result = download_one(
        "https://youtu.be/x", outtmpl=str(tmp_path / "%(title)s.%(ext)s"),
        output_type="MP4", convert=False, target_resolution=1080,
    )
    assert result.status == "ok"
    assert result.path == "D:/a.mp4"
    assert result.height == 1080


def test_download_one_classifies_exception(monkeypatch, tmp_path):
    class Boom:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True):
            raise Exception("Sign in to confirm you're not a bot")

    monkeypatch.setattr("yt_dlp.YoutubeDL", Boom)
    result = download_one(
        "https://www.facebook.com/reel/1",
        outtmpl=str(tmp_path / "%(title)s.%(ext)s"),
        output_type="MP4", convert=False, target_resolution=1080,
    )
    assert result.status == "error"
    assert result.error_category == "blocked"
    assert "Facebook" in result.message
