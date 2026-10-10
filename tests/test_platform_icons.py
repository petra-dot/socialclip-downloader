"""Platform badge mapping for the queue table.

Only the pure colour/letter mapping is tested here. The Qt rendering is a thin
wrapper (see ui/platform_icons.py) and is verified by launching the app.
"""

from ui.platform_icons import DEFAULT_COLOR, PLATFORM_COLORS, badge_for_url, badge_spec


def test_known_platform_gets_brand_colour_and_initial():
    assert badge_spec("youtube") == ("Y", "#FF0000")
    assert badge_spec("tiktok") == ("T", "#111111")
    assert badge_spec("facebook") == ("F", "#1877F2")


def test_every_supported_platform_has_a_colour():
    from sites.cookies import PLATFORM_NAMES
    for key in PLATFORM_NAMES:
        letter, color = badge_spec(key)
        assert letter != "?", key
        assert color != DEFAULT_COLOR, key


def test_unknown_platform_gets_neutral_badge():
    assert badge_spec("") == ("?", DEFAULT_COLOR)
    assert badge_spec("nope") == ("N", DEFAULT_COLOR)


def test_badge_for_url_detects_platform():
    assert badge_for_url("https://www.youtube.com/watch?v=1")[0] == "Y"
    assert badge_for_url("https://www.instagram.com/reel/1")[0] == "I"
    assert badge_for_url("https://example.com/v")[0] == "?"


def test_badge_for_url_is_case_and_www_tolerant():
    assert badge_for_url("https://WWW.FACEBOOK.COM/reel/1")[0] == "F"
    assert badge_for_url("https://fb.watch/abc")[0] == "F"


def test_colours_are_valid_hex():
    for key, color in PLATFORM_COLORS.items():
        assert color.startswith("#") and len(color) == 7, key
