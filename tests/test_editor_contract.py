"""One test that walks every format and every plan outcome and asserts no
editor-hostile codec can ever be produced."""

from core.convert import plan_conversion
from core.formats import EDITOR_SAFE_A, EDITOR_SAFE_V, FORMATS, for_kind

SOURCE_CODECS_V = ("h264", "hevc", "vp9", "av1", "")
SOURCE_CODECS_A = ("aac", "mp3", "opus", "vorbis", "wmav2", "flac", "")


def test_no_produced_codec_is_editor_hostile():
    bad = []
    for f in FORMATS:
        if f.key == "gif":
            continue
        for sv in SOURCE_CODECS_V:
            for sa in SOURCE_CODECS_A:
                for copy in (None, True, False):
                    plan = plan_conversion(
                        {"vcodec": sv, "acodec": sa}, f, copy_streams=copy
                    )
                    if plan.vcodec and plan.vcodec != "copy":
                        if plan.vcodec not in EDITOR_SAFE_V:
                            bad.append((f.key, sv, sa, copy, "v", plan.vcodec))
                    if plan.acodec and plan.acodec != "copy":
                        if plan.acodec not in EDITOR_SAFE_A:
                            bad.append((f.key, sv, sa, copy, "a", plan.acodec))
    assert not bad, bad[:20]


def test_registry_itself_only_names_safe_codecs():
    for f in FORMATS:
        if f.key == "gif":
            continue
        assert f.vcodec in EDITOR_SAFE_V or f.vcodec == "", f.key
        assert f.acodec in EDITOR_SAFE_A, f.key
