import pytest

from sites.collections import classify_url, collection_note


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/playlist?list=PL123", "collection"),
        ("https://www.youtube.com/@somechannel", "collection"),
        ("https://www.youtube.com/@somechannel/videos", "collection"),
        ("https://www.youtube.com/channel/UCabc123", "collection"),
        ("https://www.youtube.com/c/SomeName", "collection"),
        ("https://www.youtube.com/watch?v=abc", "video"),
        ("https://www.youtube.com/watch?v=abc&list=PL123", "video"),
        ("https://youtu.be/abc", "unknown"),
        ("https://www.instagram.com/someuser/", "collection"),
        ("https://www.instagram.com/p/abc/", "video"),
        ("https://www.instagram.com/reel/abc/", "video"),
        ("https://www.tiktok.com/@user", "collection"),
        ("https://www.tiktok.com/@user/video/123", "video"),
        ("https://twitter.com/user", "collection"),
        ("https://twitter.com/user/status/123", "video"),
        ("https://x.com/user/status/123", "video"),
        ("https://www.facebook.com/somepage", "collection"),
        ("https://www.facebook.com/watch/?v=123", "video"),
        ("https://space.bilibili.com/12345", "collection"),
        ("https://www.bilibili.com/video/BV1xx", "video"),
        ("https://www.douyin.com/user/MS4wLjAB", "collection"),
        ("https://www.douyin.com/video/7123", "video"),
        ("https://example.com/whatever", "unknown"),
        ("", "unknown"),
    ],
)
def test_classify_url(url, expected):
    assert classify_url(url) == expected


def test_collection_note_youtube_is_empty():
    assert collection_note("youtube") == ""


def test_collection_note_instagram_mentions_posts():
    assert "post" in collection_note("instagram").lower()


def test_collection_note_unknown_is_empty():
    assert collection_note("nope") == ""
