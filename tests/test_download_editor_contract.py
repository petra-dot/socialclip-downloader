"""Post-download MP4s must be H.264 video AND editor-safe audio, or be
re-encoded. An absent audio stream is fine (silent video)."""

from core.download import needs_universal_reencode


def test_hostile_video_triggers_reencode():
    assert needs_universal_reencode({"vcodec": "vp9", "acodec": "aac"}) is True
    assert needs_universal_reencode({"vcodec": "hevc", "acodec": "aac"}) is True
    assert needs_universal_reencode({"vcodec": "av1", "acodec": "opus"}) is True


def test_hostile_audio_triggers_reencode():
    assert needs_universal_reencode({"vcodec": "h264", "acodec": "opus"}) is True
    assert needs_universal_reencode({"vcodec": "h264", "acodec": "vorbis"}) is True


def test_safe_pair_is_left_alone():
    assert needs_universal_reencode({"vcodec": "h264", "acodec": "aac"}) is False
    assert needs_universal_reencode({"vcodec": "h264", "acodec": "mp3"}) is False


def test_unknown_is_reencoded():
    assert needs_universal_reencode({"vcodec": "", "acodec": ""}) is True
