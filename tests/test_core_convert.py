from core.convert import convert_file


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
