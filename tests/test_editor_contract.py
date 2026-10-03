"""One test that walks every format and every plan outcome and asserts no
editor-hostile codec can ever be produced."""

from core.convert import plan_conversion
from core.formats import EDITOR_SAFE_A, EDITOR_SAFE_V, FORMATS

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
                    # A remux copies the SOURCE codec, so a "copy" plan is only
                    # safe if the source codec is editor-safe.
                    produced_v = sv if plan.vcodec == "copy" else plan.vcodec
                    produced_a = sa if plan.acodec == "copy" else plan.acodec
                    if produced_v and produced_v not in EDITOR_SAFE_V:
                        bad.append((f.key, sv, sa, copy, "v", produced_v))
                    if produced_a and produced_a not in EDITOR_SAFE_A:
                        bad.append((f.key, sv, sa, copy, "a", produced_a))
    assert not bad, bad[:20]


def test_registry_itself_only_names_safe_codecs():
    for f in FORMATS:
        if f.key == "gif":
            continue
        assert f.vcodec in EDITOR_SAFE_V or f.vcodec == "", f.key
        assert f.acodec in EDITOR_SAFE_A, f.key
