from core.convert import ConvertPlan, plan_conversion
from core.formats import get


def _src(vcodec="h264", acodec="aac"):
    return {"vcodec": vcodec, "acodec": acodec, "height": 1080, "container": "mp4"}


def test_auto_remux_when_both_streams_fit():
    plan = plan_conversion(_src("h264", "aac"), get("mkv"))
    assert plan.mode == "remux"
    assert plan.vcodec == "copy" and plan.acodec == "copy"


def test_auto_transcodes_when_video_not_allowed():
    plan = plan_conversion(_src("vp9", "opus"), get("mp4"))
    assert plan.mode == "transcode"
    assert plan.vcodec == "h264"


def test_auto_transcodes_when_audio_not_allowed():
    plan = plan_conversion(_src("h264", "dts"), get("mp4"))
    assert plan.mode == "transcode"


def test_force_copy_keeps_copy_even_if_incompatible():
    plan = plan_conversion(_src("vp9", "opus"), get("mp4"), copy_streams=True)
    assert plan.mode == "remux"
    assert plan.vcodec == "copy"


def test_force_transcode_never_copies():
    plan = plan_conversion(_src("h264", "aac"), get("mkv"), copy_streams=False)
    assert plan.mode == "transcode"
    assert plan.vcodec == "h264"


def test_audio_target_drops_video_and_may_copy_audio():
    plan = plan_conversion(_src("h264", "mp3"), get("mp3"))
    assert plan.mode == "remux"
    assert plan.vcodec == ""
    assert plan.acodec == "copy"


def test_audio_target_transcodes_when_audio_mismatched():
    plan = plan_conversion(_src("h264", "aac"), get("mp3"))
    assert plan.mode == "transcode"
    assert plan.acodec == "mp3"


def test_audio_force_copy_wins_over_mismatch():
    plan = plan_conversion(_src("h264", "aac"), get("mp3"), copy_streams=True)
    assert plan.mode == "remux"
    assert plan.vcodec == ""
    assert plan.acodec == "copy"


def test_audio_auto_still_transcodes_on_mismatch():
    plan = plan_conversion(_src("h264", "aac"), get("mp3"))
    assert plan.mode == "transcode"
    assert plan.acodec == "mp3"


def test_gif_never_remuxes():
    plan = plan_conversion(_src("h264", "aac"), get("gif"))
    assert plan.mode == "transcode"
