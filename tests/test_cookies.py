import os

import pytest

import sites.cookies as cookies
from sites.cookies import (
    cookie_file_for,
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
        ("https://m.youtube.com/watch?v=1", "youtube"),
        ("https://v.douyin.com/xyz", "douyin"),
        ("https://www.instagram.com/reel/1", "instagram"),
        ("https://x.com/u/status/1", "twitter"),
        ("https://www.tiktok.com/@u/video/1", "tiktok"),
        ("https://www.bilibili.com/video/1", "bilibili"),
        ("https://www.facebook.com/reel/123456789", "facebook"),
        ("https://fb.watch/abc", "facebook"),
        ("https://example.com/video", ""),
        ("https://app.box.com/s/xyz", ""),
        ("https://www.reddit.com/r/videos/x.com", ""),
        ("youtu.be", "youtube"),
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


def test_default_cookie_dir_is_the_data_dir_not_cwd(tmp_path, monkeypatch):
    # Launching from a directory with a stray cookie file must not change where
    # the app looks: the per-user data directory is the stable location.
    workdir = tmp_path / "work"
    workdir.mkdir()
    (workdir / "youtube_cookies.txt").write_text("c")
    monkeypatch.chdir(workdir)
    from core.paths import data_dir
    assert default_cookie_dir() == data_dir()
    assert default_cookie_dir() != str(workdir)
    expected = os.path.dirname(os.path.dirname(os.path.abspath(cookies.__file__)))
    assert cookies.app_dir() == expected


def test_cookie_path_finds_app_dir_cookie(tmp_path, monkeypatch):
    empty = tmp_path / "empty-cwd"
    empty.mkdir()
    monkeypatch.chdir(empty)
    monkeypatch.setattr(cookies, "app_dir", lambda: str(tmp_path))
    (tmp_path / "youtube_cookies.txt").write_text("c")
    expected = str(tmp_path / "youtube_cookies.txt")
    assert get_cookie_path("https://youtu.be/x") == expected


def test_cookie_path_still_finds_cwd_cookie(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    (work / "youtube_cookies.txt").write_text("c")
    monkeypatch.chdir(work)
    monkeypatch.setattr(cookies, "app_dir", lambda: str(tmp_path / "elsewhere"))
    assert get_cookie_path("https://youtu.be/x") == str(work / "youtube_cookies.txt")


def test_display_name_known_and_fallback():
    assert get_platform_display_name("facebook") == "Facebook"
    assert get_platform_display_name("unknown") == "Unknown"


def test_cookie_message_facebook_mentions_filename():
    assert "facebook_cookies.txt" in get_cookie_message("facebook")


def test_cookie_message_unknown_is_empty():
    assert get_cookie_message("nope") == ""


def test_cookie_file_for_finds_and_misses(tmp_path):
    (tmp_path / "youtube_cookies.txt").write_text("c")
    assert cookie_file_for("youtube", str(tmp_path)).endswith("youtube_cookies.txt")
    assert cookie_file_for("tiktok", str(tmp_path)) == ""


def test_browsers_is_a_nonempty_tuple_of_names():
    from sites.cookies import BROWSERS
    assert isinstance(BROWSERS, tuple) and BROWSERS
    assert "chrome" in BROWSERS and "firefox" in BROWSERS


def test_cookie_status_lists_every_platform(monkeypatch):
    from sites import cookies as c
    monkeypatch.setattr(c, "cookie_file_for",
                        lambda platform, cookie_dir=None: "")
    rows = c.cookie_status()
    assert {r[0] for r in rows} == set(c.PLATFORM_NAMES)
    assert all(r[2] == "" for r in rows)


def test_cookie_status_reports_a_present_file(monkeypatch):
    from sites import cookies as c
    monkeypatch.setattr(
        c, "cookie_file_for",
        lambda platform, cookie_dir=None:
        "C:/app/youtube_cookies.txt" if platform == "youtube" else "",
    )
    rows = dict((r[0], r[2]) for r in c.cookie_status())
    assert rows["youtube"].endswith("youtube_cookies.txt")
    assert rows["douyin"] == ""


def test_find_cookie_matches_a_browser_style_name(tmp_path):
    from sites.cookies import _find_cookie
    (tmp_path / "www.youtube.com_cookies.txt").write_text("x")
    assert _find_cookie("youtube", str(tmp_path)).endswith(
        "www.youtube.com_cookies.txt"
    )
    assert _find_cookie("douyin", str(tmp_path)) == ""


def test_find_cookie_prefers_the_exact_name(tmp_path):
    from sites.cookies import _find_cookie
    (tmp_path / "youtube_cookies.txt").write_text("x")
    (tmp_path / "www.youtube.com_cookies.txt").write_text("x")
    assert _find_cookie("youtube", str(tmp_path)).endswith("youtube_cookies.txt")


def test_dialog_and_download_path_resolve_the_same_file(tmp_path, monkeypatch):
    from sites import cookies as c
    (tmp_path / "www.youtube.com_cookies.txt").write_text("x")
    monkeypatch.setattr(c, "_cookie_search_dirs", lambda: [str(tmp_path)])
    assert c.cookie_file_for("youtube") == c.get_cookie_path("https://youtu.be/x")
    assert c.get_cookie_path("https://youtu.be/x").endswith(
        "www.youtube.com_cookies.txt"
    )
