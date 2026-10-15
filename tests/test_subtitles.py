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
