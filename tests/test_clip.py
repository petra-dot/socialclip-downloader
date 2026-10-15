import pytest

from core.clip import ClipSpec, clip_ffmpeg_args, parse_time, resolve_range


@pytest.mark.parametrize(
    "text,expected",
    [
        ("90", 90.0),
        ("0", 0.0),
        ("1:30", 90.0),
        ("00:01:30", 90.0),
        ("1:2:3", 3723.0),
        ("90.5", 90.5),
        ("", None),
        ("   ", None),
        (None, None),
        ("abc", None),
        ("-5", None),
        ("1:-30", None),
        ("1:2:3:4", None),
    ],
)
def test_parse_time(text, expected):
    assert parse_time(text) == expected


def test_resolve_range_end_mode():
    spec, error = resolve_range("1:00", "1:30", "", "end")
    assert error is None
    assert spec == ClipSpec(start=60.0, end=90.0, exact=False)


def test_resolve_range_duration_mode():
    spec, error = resolve_range("60", "", "30", "duration")
    assert error is None
    assert spec.start == 60.0 and spec.end == 90.0


def test_resolve_range_open_end():
    spec, error = resolve_range("60", "", "", "end")
    assert error is None
    assert spec.end is None


def test_resolve_range_no_clip():
    spec, error = resolve_range("", "", "", "end")
    assert spec is None and error is None


def test_resolve_range_bad_start():
    spec, error = resolve_range("abc", "", "", "end")
    assert spec is None and error


def test_resolve_range_end_before_start():
    spec, error = resolve_range("90", "60", "", "end")
    assert spec is None and "after" in error.lower()


def test_resolve_range_carries_exact():
    spec, _ = resolve_range("10", "20", "", "end", exact=True)
    assert spec.exact is True


def test_clip_ffmpeg_args_stream_copy():
    args = clip_ffmpeg_args(ClipSpec(start=10.0, end=20.0, exact=False))
    assert args[:4] == ["-ss", "10", "-to", "20"]
    assert "-c" in args and args[args.index("-c") + 1] == "copy"


def test_clip_ffmpeg_args_exact_reencodes():
    args = clip_ffmpeg_args(ClipSpec(start=10.0, end=None, exact=True))
    assert "libx264" in args
    assert "-to" not in args  # open end


import os

from core.download import _clip_name, download_one


def test_clip_name_whole_seconds():
    assert _clip_name("D:/a/Title.mp4", ClipSpec(90.0, 120.0, False)) == \
        "D:/a/Title_clip_90-120.mp4"


def test_clip_name_open_end():
    assert _clip_name("D:/a/Title.mp4", ClipSpec(90.0, None, False)) == \
        "D:/a/Title_clip_90-end.mp4"


class _SectionFailYDL:
    """Fails when asked for a section, succeeds on the full download."""

    def __init__(self, full_path):
        self._full = full_path

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True, **kw):
        return {"id": "x", "title": "T", "height": 1080, "ext": "mp4"}

    def prepare_filename(self, info):
        return self._full


def test_download_one_clip_falls_back_and_cuts(monkeypatch, tmp_path):
    full = tmp_path / "T.mp4"
    full.write_bytes(b"full")

    class YDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True, **kw):
            if "download_ranges" in self.opts:
                raise RuntimeError("section download failed")
            return {"id": "x", "title": "T", "height": 1080, "ext": "mp4"}

        def prepare_filename(self, info):
            return str(full)

    monkeypatch.setattr("yt_dlp.YoutubeDL", YDL)

    class Proc:
        returncode = 0
        stdout = b""
        stderr = b""

    def fake_run(cmd, *a, **k):
        # ffmpeg writes the cut file as the last argument
        with open(cmd[-1], "wb") as fh:
            fh.write(b"cut")
        return Proc()

    monkeypatch.setattr("core.download.subprocess.run", fake_run)
    monkeypatch.setattr("core.download.os.path.getsize", lambda p: 3)
    monkeypatch.setattr(
        "core.download.probe_media",
        lambda path, **k: {"vcodec": "h264", "acodec": "aac", "height": 1080,
                           "container": "mp4"},
    )

    result = download_one(
        "https://youtu.be/x", outtmpl=str(tmp_path / "%(title)s.%(ext)s"),
        output_type="MP4", convert=False, target_resolution=1080,
        clip=ClipSpec(10.0, 20.0, False),
    )
    assert result.status == "ok"
    assert result.path.endswith("_clip_10-20.mp4")
    assert os.path.isfile(result.path)


def test_download_one_clip_cut_failure_returns_error(monkeypatch, tmp_path):
    full = tmp_path / "T.mp4"
    full.write_bytes(b"full")

    class YDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True, **kw):
            if "download_ranges" in self.opts:
                raise RuntimeError("section download failed")
            return {"id": "x", "title": "T", "height": 1080, "ext": "mp4"}

        def prepare_filename(self, info):
            return str(full)

    monkeypatch.setattr("yt_dlp.YoutubeDL", YDL)

    class Proc:
        returncode = 1
        stdout = b""
        stderr = b"boom"

    monkeypatch.setattr("core.download.subprocess.run", lambda cmd, *a, **k: Proc())

    result = download_one(
        "https://youtu.be/x", outtmpl=str(tmp_path / "%(title)s.%(ext)s"),
        output_type="MP4", convert=False, target_resolution=1080,
        clip=ClipSpec(10.0, 20.0, False),
    )
    assert result.status != "ok"
    assert result.error_category == "ffmpeg"
    assert str(full) in result.message
    # The completed full download is left on disk for the user to find.
    assert full.is_file()
