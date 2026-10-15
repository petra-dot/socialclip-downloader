from core.progress import (
    Progress, format_bytes, format_eta, format_progress, format_speed,
)


def test_format_bytes_units():
    assert format_bytes(512) == "512 B"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(1024 * 1024 * 14.2) == "14.2 MB"
    assert format_bytes(1024 ** 3 * 1.4) == "1.4 GB"


def test_format_speed():
    assert format_speed(1024 * 1024 * 3.2) == "3.2 MB/s"
    assert format_speed(None) == ""


def test_format_eta():
    assert format_eta(12) == "ETA 00:12"
    assert format_eta(3723) == "ETA 1:02:03"
    assert format_eta(None) == ""


def test_format_progress_all_fields():
    p = Progress(percent=45, speed=1024 * 1024 * 3.2, eta=12,
                 downloaded=int(1024 * 1024 * 14.2),
                 total=int(1024 * 1024 * 31.0))
    text = format_progress(p)
    assert text.startswith("45%")
    assert "3.2 MB/s" in text
    assert "ETA 00:12" in text
    assert "14.2/31.0 MB" in text


def test_format_progress_omits_unknown_parts():
    p = Progress(percent=5, speed=None, eta=None, downloaded=1024, total=None)
    assert format_progress(p) == "5%  1.0 KB"


def test_format_progress_never_trailing_separator():
    p = Progress(percent=100, speed=None, eta=None, downloaded=0, total=None)
    assert format_progress(p) == "100%"
