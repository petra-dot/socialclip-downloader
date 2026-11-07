import os

import pytest

from core.queue import build_job_options
from utils.file_utils import OUTPUT_TEMPLATE


def test_mp4_options_match_the_queue_tab_contract():
    opts = build_job_options("/out", "Video (MP4)", "1080", "", "sidecar", "chrome")
    assert opts == {
        "outtmpl": os.path.join("/out", OUTPUT_TEMPLATE),
        "output_type": "MP4",
        "convert": True,
        "target_resolution": 1080,
        "cookies_file": "",
        "subtitles": "sidecar",
        "cookies_from_browser": "chrome",
    }


@pytest.mark.parametrize("label", ["Audio (MP3)", "MP3"])
def test_mp3_label_sets_audio_without_convert(label):
    opts = build_job_options("/out", label, "720", "c.txt", "off", "")
    assert opts["output_type"] == "MP3"
    assert opts["convert"] is False
    assert opts["target_resolution"] == 720
