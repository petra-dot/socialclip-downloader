"""MP4 is the universal-sharing container: WhatsApp and Facebook reject
HEVC and AV1 inside it just as they reject VP9. The mp4 target must therefore
only ever remux H.264 video, and transcode anything else.
"""

from core.convert import plan_conversion
from core.formats import get


def test_mp4_label_matches_its_remux_list():
    mp4 = get("mp4")
    assert mp4.label == "MP4 (H.264 + AAC)"
    assert mp4.remux_v == ("h264",), mp4.remux_v


def test_mp4_remuxes_h264():
    plan = plan_conversion({"vcodec": "h264", "acodec": "aac"}, get("mp4"))
    assert plan.mode == "remux"
    assert plan.vcodec == "copy"


def test_mp4_transcodes_hevc():
    plan = plan_conversion({"vcodec": "hevc", "acodec": "aac"}, get("mp4"))
    assert plan.mode == "transcode"
    assert plan.vcodec == "h264"


def test_mp4_transcodes_av1():
    plan = plan_conversion({"vcodec": "av1", "acodec": "opus"}, get("mp4"))
    assert plan.mode == "transcode"
    assert plan.vcodec == "h264"


def test_mkv_only_remuxes_h264():
    """Editor-safe contract: mkv copies H.264 and transcodes everything else."""
    assert get("mkv").remux_v == ("h264",)
    plan = plan_conversion({"vcodec": "hevc", "acodec": "aac"}, get("mkv"))
    assert plan.mode == "transcode"
    assert plan.vcodec == "h264"
