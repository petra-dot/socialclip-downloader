from core.convert import plan_conversion
from core.formats import EDITOR_SAFE_A, EDITOR_SAFE_V, for_kind, get

VIDEO_KEYS = [f.key for f in for_kind("video") if f.key != "gif"]


def test_no_plan_ever_emits_a_hostile_video_codec():
    for key in VIDEO_KEYS:
        for src_v in ("h264", "hevc", "vp9", "av1"):
            plan = plan_conversion({"vcodec": src_v, "acodec": "aac"}, get(key))
            if plan.vcodec and plan.vcodec != "copy":
                assert plan.vcodec in EDITOR_SAFE_V, (key, src_v, plan)


def test_no_plan_ever_emits_a_hostile_audio_codec():
    for key in VIDEO_KEYS + [f.key for f in for_kind("audio")]:
        for src_a in ("aac", "opus", "vorbis", "wmav2", "flac"):
            plan = plan_conversion({"vcodec": "h264", "acodec": src_a}, get(key))
            if plan.acodec and plan.acodec != "copy":
                assert plan.acodec in EDITOR_SAFE_A, (key, src_a, plan)


def test_hostile_video_source_transcodes():
    plan = plan_conversion({"vcodec": "vp9", "acodec": "aac"}, get("mp4"))
    assert plan.mode == "transcode"
    assert plan.vcodec == "h264"


def test_forced_copy_of_hostile_video_is_upgraded():
    """copy_streams=True must not hand back a VP9 file an editor rejects."""
    plan = plan_conversion({"vcodec": "vp9", "acodec": "aac"}, get("mp4"), copy_streams=True)
    assert plan.vcodec != "copy", plan
    assert plan.vcodec == "h264"


def test_forced_copy_of_safe_codecs_still_copies():
    plan = plan_conversion({"vcodec": "h264", "acodec": "aac"}, get("mkv"), copy_streams=True)
    assert plan.mode == "remux"
    assert plan.vcodec == "copy"


def test_forced_copy_of_hostile_audio_is_upgraded():
    plan = plan_conversion({"vcodec": "h264", "acodec": "opus"}, get("mp4"), copy_streams=True)
    assert plan.acodec != "copy", plan


def test_forced_copy_to_audio_target_upgrades_hostile_audio():
    from core.convert import plan_conversion
    from core.formats import get
    # An Opus source forced-copied to an mp3 target must not copy the Opus.
    plan = plan_conversion({"vcodec": "h264", "acodec": "opus"}, get("mp3"), copy_streams=True)
    assert plan.acodec != "copy", plan
    assert plan.acodec == "mp3"


def test_forced_copy_to_audio_target_copies_safe_audio():
    from core.convert import plan_conversion
    from core.formats import get
    plan = plan_conversion({"vcodec": "h264", "acodec": "mp3"}, get("mp3"), copy_streams=True)
    assert plan.mode == "remux"
    assert plan.acodec == "copy"
