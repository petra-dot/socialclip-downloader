import pytest

from sites.cookies import (
    detect_platform,
    get_cookie_message,
    get_cookie_path,
    get_platform_display_name,
)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=1", "youtube"),
        ("https://youtu.be/abc", "youtube"),
        ("https://v.douyin.com/xyz", "douyin"),
        ("https://www.instagram.com/reel/1", "instagram"),
        ("https://x.com/u/status/1", "twitter"),
        ("https://www.tiktok.com/@u/video/1", "tiktok"),
        ("https://www.bilibili.com/video/1", "bilibili"),
        ("https://www.facebook.com/reel/931231782795079", "facebook"),
        ("https://fb.watch/abc", "facebook"),
        ("https://example.com/video", ""),
    ],
)
def test_detect_platform(url, expected):
    assert detect_platform(url) == expected


def test_cookie_path_found(tmp_path):
    (tmp_path / "youtube_cookies.txt").write_text("c")
    expected = str(tmp_path / "youtube_cookies.txt")
    assert get_cookie_path("https://youtu.be/x", str(tmp_path)) == expected


def test_cookie_path_missing(tmp_path):
    assert get_cookie_path("https://youtu.be/x", str(tmp_path)) == ""


def test_cookie_path_unknown_platform(tmp_path):
    assert get_cookie_path("https://example.com/x", str(tmp_path)) == ""


def test_display_name_known_and_fallback():
    assert get_platform_display_name("facebook") == "Facebook"
    assert get_platform_display_name("unknown") == "Unknown"


def test_cookie_message_facebook_mentions_filename():
    assert "facebook_cookies.txt" in get_cookie_message("facebook")


def test_cookie_message_unknown_is_empty():
    assert get_cookie_message("nope") == ""
