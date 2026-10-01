import os

import pytest

import sites.cookies as cookies
from sites.cookies import (
    default_cookie_dir,
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


def test_default_cookie_dir_prefers_cwd_when_present():
    assert default_cookie_dir() == os.getcwd()


def test_default_cookie_dir_falls_back_to_app_dir(tmp_path, monkeypatch):
    empty = tmp_path / "empty-cwd"
    empty.mkdir()
    monkeypatch.chdir(empty)
    assert default_cookie_dir() == os.path.dirname(os.path.abspath(cookies.__file__))


def test_cookie_path_uses_app_dir_when_cwd_is_barren(tmp_path, monkeypatch):
    empty = tmp_path / "empty-cwd"
    empty.mkdir()
    monkeypatch.chdir(empty)
    app_dir = os.path.dirname(os.path.abspath(cookies.__file__))
    cookie_file = os.path.join(app_dir, "youtube_cookies.txt")
    with open(cookie_file, "w") as handle:
        handle.write("c")
    try:
        assert get_cookie_path("https://youtu.be/x") == cookie_file
    finally:
        os.remove(cookie_file)


def test_display_name_known_and_fallback():
    assert get_platform_display_name("facebook") == "Facebook"
    assert get_platform_display_name("unknown") == "Unknown"


def test_cookie_message_facebook_mentions_filename():
    assert "facebook_cookies.txt" in get_cookie_message("facebook")


def test_cookie_message_unknown_is_empty():
    assert get_cookie_message("nope") == ""
