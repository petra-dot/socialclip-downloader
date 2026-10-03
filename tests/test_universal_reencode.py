"""After download, an MP4 that is not H.264/AAC must be re-encoded so it plays
on WhatsApp and Facebook. An already-H.264 file must be left alone."""

from core.download import needs_universal_reencode


def test_vp9_needs_reencode():
    assert needs_universal_reencode({"vcodec": "vp9", "acodec": "opus"}) is True


def test_av1_needs_reencode():
    assert needs_universal_reencode({"vcodec": "av1", "acodec": "opus"}) is True


def test_hevc_needs_reencode():
    assert needs_universal_reencode({"vcodec": "hevc", "acodec": "aac"}) is True


def test_h264_aac_is_left_alone():
    assert needs_universal_reencode({"vcodec": "h264", "acodec": "aac"}) is False


def test_h264_h264_aliases_are_left_alone():
    # ffprobe reports the codec as "h264"; accept that exact name.
    assert needs_universal_reencode({"vcodec": "h264", "acodec": "mp3"}) is False


def test_unknown_video_codec_is_reencoded():
    """If we cannot confirm H.264, guarantee compatibility by re-encoding."""
    assert needs_universal_reencode({"vcodec": "", "acodec": ""}) is True
