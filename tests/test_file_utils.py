from utils.file_utils import clean_title, get_uploader, make_unique_filepath, restore_or


def test_restore_or_returns_saved_value():
    assert restore_or("/fallback", "/saved") == "/saved"


def test_restore_or_falls_back_when_none():
    assert restore_or("/fallback", None) == "/fallback"


def test_restore_or_falls_back_when_empty_or_whitespace():
    assert restore_or("/fallback", "") == "/fallback"
    assert restore_or("/fallback", "   ") == "/fallback"


def test_restore_or_falls_back_when_key_missing():
    class FakeSettings:
        def value(self, key, default=None):
            return default

    assert restore_or("/fallback", FakeSettings().value("missing", None)) == "/fallback"


def test_clean_title_strips_illegal_chars():
    assert clean_title('a/b\\c:d*e?f"g<h>i|j') == "a b c d e f g h i j"


def test_clean_title_collapses_whitespace():
    assert clean_title("  hello   world  ") == "hello world"


def test_clean_title_empty_returns_video():
    assert clean_title("") == "video"
    assert clean_title("///") == "video"
    assert clean_title(None) == "video"


def test_clean_title_truncates_to_120():
    assert len(clean_title("x" * 200)) == 120


def test_clean_title_preserves_non_ascii():
    assert clean_title("中文标题") == "中文标题"


def test_get_uploader_prefers_uploader_then_channel_then_creator():
    assert get_uploader({"uploader": "U", "channel": "C", "creator": "X"}) == "U"
    assert get_uploader({"channel": "C", "creator": "X"}) == "C"
    assert get_uploader({"creator": "X"}) == "X"
    assert get_uploader({}) == ""


def test_unique_filepath_when_free(tmp_path):
    expected = str(tmp_path / "clip.mp4")
    assert make_unique_filepath(str(tmp_path), "clip", "mp4") == expected


def test_unique_filepath_uses_fallback_id_on_collision(tmp_path):
    (tmp_path / "clip.mp4").write_text("x")
    expected = str(tmp_path / "clip_abc.mp4")
    assert make_unique_filepath(str(tmp_path), "clip", "mp4", fallback_id="abc") == expected


def test_unique_filepath_numeric_suffix_when_both_taken(tmp_path):
    (tmp_path / "clip.mp4").write_text("x")
    (tmp_path / "clip_abc.mp4").write_text("x")
    expected = str(tmp_path / "clip_1.mp4")
    assert make_unique_filepath(str(tmp_path), "clip", "mp4", fallback_id="abc") == expected
