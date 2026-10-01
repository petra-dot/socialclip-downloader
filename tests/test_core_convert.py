from core.convert import convert_file
from core.formats import get


def test_missing_input_returns_error():
    result = convert_file("D:/nope.mp4", "MP3")
    assert result.status == "error"
    assert result.error_category == "not_found"


def test_mp3_conversion_invokes_ffmpeg(monkeypatch, tmp_path):
    src = tmp_path / "in.mp4"
    src.write_text("x")

    class P:
        returncode = 0
        stderr = b""

    monkeypatch.setattr("core.convert.subprocess.run", lambda *a, **k: P())
    result = convert_file(str(src), "MP3")
    assert result.status == "ok"
    assert result.path.endswith(".mp3")


def test_mp4_equal_resolution_skips_without_ffmpeg(monkeypatch, tmp_path):
    src = tmp_path / "in.mp4"
    src.write_text("x")

    monkeypatch.setattr("core.convert.ffprobe_get_height", lambda p: 1080)
    result = convert_file(str(src), "MP4", 1080)
    assert result.status == "ok"
    assert result.path == str(src)


def test_target_format_mp4_transcodes_and_names_mode(monkeypatch, tmp_path):
    src = tmp_path / "in.webm"
    src.write_text("x")

    class P:
        returncode = 0
        stderr = b""

    monkeypatch.setattr("core.convert.subprocess.run", lambda *a, **k: P())
    monkeypatch.setattr(
        "core.convert.probe_media",
        lambda path, **k: {"vcodec": "vp9", "acodec": "opus", "height": 0, "container": ""},
    )
    result = convert_file(str(src), target_format="mp4")
    assert result.status == "ok"
    assert result.path.endswith(".mp4")
    assert "Converted" in (result.message or "")


def test_target_format_remux_names_remuxed(monkeypatch, tmp_path):
    src = tmp_path / "in.mp4"
    src.write_text("x")

    class P:
        returncode = 0
        stderr = b""

    monkeypatch.setattr("core.convert.subprocess.run", lambda *a, **k: P())
    monkeypatch.setattr(
        "core.convert.probe_media",
        lambda path, **k: {"vcodec": "h264", "acodec": "aac", "height": 0, "container": ""},
    )
    result = convert_file(str(src), target_format="mkv")
    assert "Remuxed" in (result.message or "")


def test_unknown_target_format_is_an_error(monkeypatch, tmp_path):
    src = tmp_path / "in.mp4"
    src.write_text("x")
    result = convert_file(str(src), target_format="nope")
    assert result.status == "error"
    assert result.error_category == "format"


def test_audio_container_muxers_are_pinned():
    assert get("m4a").container == "ipod"
    assert get("aac").container == "adts"
    assert get("wma").container == "asf"
