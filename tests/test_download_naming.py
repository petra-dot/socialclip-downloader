"""Download naming: the output template must be unique per video.

Two videos can share a title (Facebook returns a generic "Facebook" when a
cookie file is sent), so a template of just the title makes two concurrent
downloads share one output path and fail inside yt-dlp's converter with
WinError 183. The id token makes every path unique per video.
"""
from utils.file_utils import OUTPUT_TEMPLATE, clean_download_base


def test_output_template_is_unique_per_video():
    assert "%(id)s" in OUTPUT_TEMPLATE
    assert "%(title)s" in OUTPUT_TEMPLATE
    assert "%(ext)s" in OUTPUT_TEMPLATE


def test_clean_download_base_strips_the_id_token():
    assert clean_download_base("Facebook [123]", "123") == "Facebook"
    assert clean_download_base("Real Title [123]", "123") == "Real Title"


def test_clean_download_base_leaves_a_name_without_the_token_alone():
    assert clean_download_base("Real Title", "123") == "Real Title"
    assert clean_download_base("", "123") == ""


def test_clean_download_base_keeps_a_title_that_ends_in_brackets():
    """Only the exact " [<id>]" token is removed, never a real bracket."""
    assert clean_download_base("Song [remix]", "123") == "Song [remix]"


def test_clean_download_base_is_a_no_op_without_an_id():
    assert clean_download_base("Facebook [123]", "") == "Facebook [123]"
