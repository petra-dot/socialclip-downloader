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


def _capture_run(commands):
    class P:
        returncode = 0
        stderr = b""

    def run(cmd, **kwargs):
        commands.append(cmd)
        return P()

    return run


def _probe(vcodec, acodec):
    return lambda path, **k: {
        "vcodec": vcodec,
        "acodec": acodec,
        "height": 0,
        "container": "",
    }


def _run_convert(monkeypatch, tmp_path, src_name, vcodec, acodec, target):
    src = tmp_path / src_name
    src.write_text("x")
    commands = []
    monkeypatch.setattr("core.convert.subprocess.run", _capture_run(commands))
    monkeypatch.setattr("core.convert.probe_media", _probe(vcodec, acodec))
    result = convert_file(str(src), target_format=target)
    assert result.status == "ok"
    return commands[0]


def _value_after(argv, flag):
    return argv[argv.index(flag) + 1]


def test_remux_command_copies_both_streams(monkeypatch, tmp_path):
    argv = _run_convert(monkeypatch, tmp_path, "in.mp4", "h264", "aac", "mkv")
    assert _value_after(argv, "-c:v") == "copy"
    assert _value_after(argv, "-c:a") == "copy"
    assert argv.count("-c:v") == 1 and argv.count("-c:a") == 1


def test_transcode_command_encodes_h264_and_aac(monkeypatch, tmp_path):
    argv = _run_convert(monkeypatch, tmp_path, "in.webm", "vp9", "opus", "mp4")
    assert _value_after(argv, "-c:v") == "h264"
    assert _value_after(argv, "-c:a") == "aac"


def test_audio_target_drops_video_and_sets_no_video_codec(monkeypatch, tmp_path):
    argv = _run_convert(monkeypatch, tmp_path, "in.mp4", "h264", "aac", "mp3")
    assert "-vn" in argv
    assert "-c:v" not in argv


def test_m4a_uses_ipod_muxer(monkeypatch, tmp_path):
    argv = _run_convert(monkeypatch, tmp_path, "in.mp4", "h264", "aac", "m4a")
    assert _value_after(argv, "-f") == "ipod"


def test_gif_emits_palette_filter_and_no_audio_codec(monkeypatch, tmp_path):
    argv = _run_convert(monkeypatch, tmp_path, "in.mp4", "h264", "aac", "gif")
    assert "palettegen" in _value_after(argv, "-vf")
    assert "-an" in argv
    assert "-c:a" not in argv
