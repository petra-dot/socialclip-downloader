from workers.pipeline import plan_postprocess


def test_mp3_is_audio():
    assert plan_postprocess("MP3", False, 1080, 1080) == "audio"


def test_mp4_without_convert_keeps():
    assert plan_postprocess("MP4", False, 1080, 720) == "keep"


def test_target_below_source_converts():
    assert plan_postprocess("MP4", True, 1080, 720) == "convert"


def test_target_above_source_skips_low():
    assert plan_postprocess("MP4", True, 720, 1080) == "skip_low"


def test_target_equals_source_skips_equal():
    assert plan_postprocess("MP4", True, 1080, 1080) == "skip_equal"


def test_unknown_source_height_converts():
    assert plan_postprocess("MP4", True, 0, 1080) == "convert"
