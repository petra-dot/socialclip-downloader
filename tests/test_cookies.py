import os

import pytest

import sites.cookies as cookies
from sites.cookies import (
    cookie_box_value,
    cookie_dialog_dir,
    cookie_file_for,
    cookie_file_platform,
    default_cookie_dir,
    detect_platform,
    get_cookie_message,
    get_cookie_path,
    get_platform_display_name,
    resolve_cookie_file,
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
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
    assert default_cookie_dir() == str(tmp_path / "data")
    assert default_cookie_dir() != str(workdir)
    expected = os.path.dirname(os.path.dirname(os.path.abspath(cookies.__file__)))
    assert cookies.app_dir() == expected


def test_cookie_path_finds_app_dir_cookie(tmp_path, monkeypatch):
    empty = tmp_path / "empty-cwd"
    empty.mkdir()
    monkeypatch.chdir(empty)
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
    monkeypatch.setattr(cookies, "app_dir", lambda: str(tmp_path))
    (tmp_path / "youtube_cookies.txt").write_text("c")
    expected = str(tmp_path / "youtube_cookies.txt")
    assert get_cookie_path("https://youtu.be/x") == expected


def test_cookie_path_still_finds_cwd_cookie(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    (work / "youtube_cookies.txt").write_text("c")
    monkeypatch.chdir(work)
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
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


def test_resolve_cookie_file_prefers_the_override(tmp_path, monkeypatch):
    # An explicit choice the user made must beat an auto-detected platform file.
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    (tmp_path / "youtube_cookies.txt").write_text("c")
    assert resolve_cookie_file(
        "https://youtu.be/x", "C:/custom/mine.txt"
    ) == "C:/custom/mine.txt"


def test_resolve_cookie_file_finds_the_platform_file(tmp_path, monkeypatch):
    # No override: this platform's own file wins, so a per-URL lookup replaces
    # the one global path the UI used to carry.
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    (tmp_path / "youtube_cookies.txt").write_text("c")
    expected = str(tmp_path / "youtube_cookies.txt")
    assert resolve_cookie_file("https://youtu.be/x") == expected


def test_resolve_cookie_file_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    (tmp_path / "no-app").mkdir()
    monkeypatch.setattr(cookies, "app_dir", lambda: str(tmp_path / "no-app"))
    monkeypatch.chdir(tmp_path)
    assert resolve_cookie_file("https://youtu.be/x") == ""


def test_resolve_cookie_file_empty_for_unknown_platform(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    (tmp_path / "youtube_cookies.txt").write_text("c")
    assert resolve_cookie_file("https://example.com/x") == ""


@pytest.mark.parametrize(
    "path,expected",
    [
        ("C:\\Users\\x\\www.youtube.com_cookies.txt", "youtube"),
        ("/home/x/www.youtube.com_cookies.txt", "youtube"),
        ("youtube_cookies.txt", "youtube"),
        ("cookies.txt", ""),
        ("", ""),
    ],
)
def test_cookie_file_platform(path, expected):
    assert cookie_file_platform(path) == expected


def test_resolve_cookie_file_override_scoped_to_its_platform(tmp_path, monkeypatch):
    # A YouTube cookie file must not be sent to Douyin: the Douyin URL uses
    # Douyin's own file, found here, not the override the user typed.
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    monkeypatch.setattr(cookies, "_cookie_search_dirs", lambda: [str(tmp_path)])
    (tmp_path / "www.douyin.com_cookies.txt").write_text("c")
    expected = str(tmp_path / "www.douyin.com_cookies.txt")
    assert resolve_cookie_file(
        "https://www.douyin.com/x", "C:/c/www.youtube.com_cookies.txt"
    ) == expected


def test_resolve_cookie_file_override_skipped_when_no_platform_file(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    monkeypatch.setattr(cookies, "_cookie_search_dirs", lambda: [str(tmp_path)])
    assert resolve_cookie_file(
        "https://www.douyin.com/x", "C:/c/www.youtube.com_cookies.txt"
    ) == ""


def test_resolve_cookie_file_override_used_for_its_own_platform(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    override = "C:/c/www.youtube.com_cookies.txt"
    assert resolve_cookie_file("https://youtu.be/x", override) == override


def test_resolve_cookie_file_generic_override_wins_everywhere(tmp_path, monkeypatch):
    # A file the name tells us nothing about is deliberately generic; it must
    # still apply to every URL (back-compat).
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    assert resolve_cookie_file(
        "https://www.douyin.com/x", "C:/c/cookies.txt"
    ) == "C:/c/cookies.txt"
    assert resolve_cookie_file(
        "https://example.com/x", "C:/c/cookies.txt"
    ) == "C:/c/cookies.txt"


def test_resolve_cookie_file_foreign_override_unknown_platform_is_empty():
    # Owner (youtube) differs from an unknown URL platform: send nothing rather
    # than leak the wrong platform's cookies to a site we cannot identify.
    assert resolve_cookie_file(
        "https://example.com/x", "C:/c/www.youtube.com_cookies.txt"
    ) == ""


def test_cookie_box_value_empty_url_is_blank():
    assert cookie_box_value("") == ""


def test_cookie_box_value_shows_the_url_platform_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    (tmp_path / "youtube_cookies.txt").write_text("c")
    expected = str(tmp_path / "youtube_cookies.txt")
    assert cookie_box_value("https://youtu.be/x") == expected


def test_cookie_box_value_blank_when_no_platform_file(tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    monkeypatch.setenv("SOCIALCLIP_DATA", str(empty))
    monkeypatch.setattr(cookies, "app_dir", lambda: str(empty))
    assert cookie_box_value("https://a.com/1") == ""


def test_cookie_box_value_keeps_an_applicable_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    override = "C:/c/www.youtube.com_cookies.txt"
    assert cookie_box_value("https://youtu.be/x", override) == override


def test_cookie_box_value_replaces_a_foreign_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    (tmp_path / "douyin_cookies.txt").write_text("c")
    expected = str(tmp_path / "douyin_cookies.txt")
    assert cookie_box_value(
        "https://www.douyin.com/x", "C:/c/www.youtube.com_cookies.txt"
    ) == expected


def test_cookie_dialog_dir_empty_falls_back_to_default(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    assert cookie_dialog_dir("") == default_cookie_dir()


def test_cookie_dialog_dir_uses_the_files_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
    cookie = tmp_path / "picked" / "youtube_cookies.txt"
    cookie.parent.mkdir()
    cookie.write_text("c")
    assert cookie_dialog_dir(str(cookie)) == str(cookie.parent)


def test_cookie_dialog_dir_missing_dir_falls_back_to_default(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
    assert cookie_dialog_dir(
        str(tmp_path / "gone" / "youtube_cookies.txt")
    ) == default_cookie_dir()


def test_cookie_dialog_dir_whitespace_falls_back_to_default(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    assert cookie_dialog_dir("   ") == default_cookie_dir()
