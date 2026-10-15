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
