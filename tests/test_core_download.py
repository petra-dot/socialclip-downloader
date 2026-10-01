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


class FakeYDLHeight:
    def __init__(self, height):
        self._height = height

    def __call__(self, opts):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True):
        return {"id": "x", "title": "T", "height": self._height, "duration": 10,
                "ext": "mp4"}

    def prepare_filename(self, info):
        return "D:/a.mp4"


def test_download_one_skip_low_carries_message(monkeypatch, tmp_path):
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDLHeight(720))
    monkeypatch.setattr("core.download.os.path.exists", lambda p: True)
    result = download_one(
        "https://youtu.be/x", outtmpl=str(tmp_path / "%(title)s.%(ext)s"),
        output_type="MP4", convert=True, target_resolution=1080,
    )
    assert result.status == "ok"
    assert result.message is not None
    assert "720" in result.message
    assert "1080" in result.message
    assert "No upscaling" in result.message


def test_download_one_skip_equal_carries_message(monkeypatch, tmp_path):
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDLHeight(1080))
    monkeypatch.setattr("core.download.os.path.exists", lambda p: True)
    result = download_one(
        "https://youtu.be/x", outtmpl=str(tmp_path / "%(title)s.%(ext)s"),
        output_type="MP4", convert=True, target_resolution=1080,
    )
    assert result.status == "ok"
    assert result.message is not None
    assert "1080" in result.message
    assert "resolution equals target" in result.message


def test_mp3_extension_matches_final_artifact(monkeypatch, tmp_path):
    class P:
        returncode = 0
        stderr = b""

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDL)
    monkeypatch.setattr("core.download.os.path.exists", lambda p: True)
    monkeypatch.setattr("core.download.subprocess.run", lambda *a, **k: P())
    monkeypatch.setattr("core.download.os.remove", lambda p: None)

    result = download_one(
        "https://youtu.be/x", outtmpl=str(tmp_path / "%(title)s.%(ext)s"),
        output_type="MP3", convert=True, target_resolution=1080,
    )
    assert result.status == "ok"
    assert result.path.endswith(".mp3")
    assert result.extension == "mp3"  # not the source container ("mp4")


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
