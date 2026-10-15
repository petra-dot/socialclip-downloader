from core.subtitles import DELIVERIES, SubtitleTrack, subtitle_tracks


def test_deliveries_values():
    assert DELIVERIES == ("off", "sidecar", "embed", "both")


def test_subtitle_tracks_prefers_srt_and_keeps_both_kinds():
    info = {
        "subtitles": {
            "en": [{"ext": "vtt", "url": "u-en-vtt"},
                   {"ext": "srt", "url": "u-en-srt"}],
        },
        "automatic_captions": {
            "en": [{"ext": "vtt", "url": "u-en-auto"}],
            "fr": [{"ext": "vtt", "url": "u-fr"}],
        },
    }
    tracks = subtitle_tracks(info)
    manual_en = [t for t in tracks if t.lang == "en" and t.kind == "manual"][0]
    assert manual_en.url == "u-en-srt"
    assert manual_en.ext == "srt"
    auto_en = [t for t in tracks if t.lang == "en" and t.kind == "auto"][0]
    assert auto_en.url == "u-en-auto"
    assert any(t.lang == "fr" and t.kind == "auto" for t in tracks)


def test_subtitle_tracks_skips_unusable_formats():
    info = {"subtitles": {"de": [{"ext": "json3", "url": "u"}],
                          "es": [{"ext": "vtt"}]}}
    assert subtitle_tracks(info) == []


def test_subtitle_tracks_empty_info():
    assert subtitle_tracks({}) == []
    assert subtitle_tracks(None) == []


def test_subtitle_track_is_a_dataclass():
    track = SubtitleTrack(lang="en", kind="manual", url="u", ext="srt")
    assert track.lang == "en" and track.kind == "manual"


from core.subtitles import embed_command, write_subtitle


def test_embed_command_maps_and_tags_languages():
    cmd = embed_command("v.mp4", [("en", "en.srt"), ("fr", "fr.srt")], "out.mp4")
    assert cmd[cmd.index("-c:s") + 1] == "mov_text"
    assert "language=en" in cmd and "language=fr" in cmd
    assert cmd.count("-map") == 3          # 0 plus the two sidecar streams
    assert cmd[-1] == "out.mp4"


def test_embed_command_single_track():
    cmd = embed_command("v.mp4", [("en", "en.srt")], "out.mp4")
    assert cmd.count("-map") == 2
    assert "language=en" in cmd


def test_write_subtitle_writes_manual_and_auto_names(tmp_path):
    class Response:
        def __init__(self, body):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self._body

    base = str(tmp_path / "Video")
    manual = SubtitleTrack("en", "manual", "https://example.com/en.srt", "srt")
    auto = SubtitleTrack("en", "auto", "https://example.com/en-auto.srt", "srt")
    opener = lambda req, timeout=None: Response(b"1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    assert write_subtitle(manual, base, opener=opener).endswith("Video.en.srt")
    assert write_subtitle(auto, base, opener=opener).endswith("Video.en.auto.srt")


def test_write_subtitle_bad_url_returns_none(tmp_path):
    bad = SubtitleTrack("en", "manual", "not-a-url", "srt")
    assert write_subtitle(bad, str(tmp_path / "V"), opener=lambda *a, **k: None) is None


def test_write_subtitle_missing_ffmpeg_returns_none(tmp_path, monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"WEBVTT\n"

    def boom(*a, **k):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr("core.subtitles.subprocess.run", boom)
    track = SubtitleTrack("en", "manual", "https://example.com/en.vtt", "vtt")
    opener = lambda req, timeout=None: Response()
    assert write_subtitle(track, str(tmp_path / "V"), opener=opener) is None
