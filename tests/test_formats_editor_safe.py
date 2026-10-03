from core.formats import EDITOR_SAFE_A, EDITOR_SAFE_V, FORMATS, for_kind, keys


def test_every_video_format_writes_h264():
    for f in for_kind("video"):
        if f.key == "gif":
            continue
        assert f.vcodec == "h264", (f.key, f.vcodec)


def test_every_format_writes_editor_safe_audio():
    for f in FORMATS:
        if f.key == "gif":
            continue
        assert f.acodec in EDITOR_SAFE_A, (f.key, f.acodec)


def test_every_video_format_only_remuxes_h264():
    for f in for_kind("video"):
        if f.key == "gif":
            continue
        assert f.remux_v == ("h264",), (f.key, f.remux_v)


def test_every_remux_audio_codec_is_editor_safe():
    for f in FORMATS:
        for codec in f.remux_a:
            assert codec in EDITOR_SAFE_A, (f.key, codec)


def test_webm_is_served_with_safe_codecs():
    webm = [f for f in FORMATS if f.key == "webm"][0]
    assert webm.vcodec == "h264"
    assert webm.acodec == "aac"


def test_editor_hostile_containers_are_removed():
    for gone in ("ogg", "opus", "wma"):
        assert gone not in keys(), gone


def test_safe_set_is_what_we_claim():
    assert EDITOR_SAFE_V == ("h264",)
    assert set(EDITOR_SAFE_A) == {"aac", "mp3", "pcm_s16le"}
