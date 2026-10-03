from core.formats import FORMATS, for_kind, get, keys


def test_keys_unique_lowercase():
    ks = keys()
    assert len(ks) == len(set(ks))
    assert all(k == k.lower() for k in ks)


def test_every_format_has_extension_and_acodec():
    for f in FORMATS:
        assert f.extension, f.key
        assert f.acodec, f.key


def test_vcodec_empty_iff_audio():
    for f in FORMATS:
        assert (f.vcodec == "") == (f.kind == "audio"), f.key


def test_audio_formats_have_no_video_remux_list():
    for f in for_kind("audio"):
        assert f.remux_v == ()


def test_known_containers():
    # Every video format only remuxes H.264; hostile sources are transcoded.
    assert get("mp4").remux_v == ("h264",)
    assert "vp9" not in get("mp4").remux_v
    assert get("gif").remux_v == ()
    assert get("mkv").kind == "video"
    assert get("mp3").kind == "audio"


def test_get_unknown_returns_none():
    assert get("nope") is None


def test_curated_formats_present():
    expected = {"mp4", "mkv", "mov", "avi", "gif",
                "mp3", "m4a", "wav", "aac"}
    assert set(keys()) == expected
