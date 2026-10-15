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


from core.collections import (
    DEFAULT_LIMIT,
    CollectionEntry,
    entries_from_info,
    new_entries,
)


def test_entries_from_info_basic():
    info = {
        "playlist_count": 3,
        "entries": [
            {"url": "https://www.youtube.com/watch?v=a", "title": "A", "id": "a"},
            {"url": "https://www.youtube.com/watch?v=b", "title": "B", "id": "b"},
        ],
    }
    entries, total, truncated = entries_from_info(info, 200, "youtube")
    assert [e.title for e in entries] == ["A", "B"]
    assert total == 3
    assert truncated is True


def test_entries_from_info_builds_youtube_url_from_bare_id():
    info = {"entries": [{"id": "abc123", "title": "T"}]}
    entries, total, truncated = entries_from_info(info, 200, "youtube")
    assert entries[0].url == "https://www.youtube.com/watch?v=abc123"
    assert total is None
    assert truncated is False


def test_entries_from_info_prefers_webpage_url():
    info = {"entries": [{"url": "https://x/y", "webpage_url": "https://x/z",
                         "id": "1", "title": "T"}]}
    entries, _, _ = entries_from_info(info, 200, "youtube")
    assert entries[0].url == "https://x/z"


def test_entries_from_info_respects_limit():
    info = {"entries": [{"id": str(i), "title": str(i)} for i in range(10)]}
    entries, _, _ = entries_from_info(info, 3, "youtube")
    assert len(entries) == 3


def test_entries_from_info_title_falls_back_to_id():
    info = {"entries": [{"id": "abc"}]}
    entries, _, _ = entries_from_info(info, 200, "youtube")
    assert entries[0].title == "abc"


def test_entries_from_info_empty():
    entries, total, truncated = entries_from_info({}, 200, "youtube")
    assert entries == []
    assert total is None
    assert truncated is False


def test_entries_from_info_skips_blank_entries():
    info = {"entries": [None, {}, {"id": "ok", "title": "T"}]}
    entries, _, _ = entries_from_info(info, 200, "youtube")
    assert len(entries) == 1


def test_new_entries_skips_existing_and_counts():
    entries = [CollectionEntry(url="a"), CollectionEntry(url="b"),
               CollectionEntry(url="c")]
    kept, skipped = new_entries(entries, ["b"])
    assert [e.url for e in kept] == ["a", "c"]
    assert skipped == 1


def test_new_entries_dedupes_within_the_batch():
    entries = [CollectionEntry(url="a"), CollectionEntry(url="a")]
    kept, skipped = new_entries(entries, [])
    assert [e.url for e in kept] == ["a"]
    assert skipped == 1


def test_default_limit_value():
    assert DEFAULT_LIMIT == 200


from core.collections import expand_collection


class FakeListYDL:
    info = {"playlist_count": 2, "entries": [
        {"url": "https://www.youtube.com/watch?v=a", "title": "A", "id": "a"},
        {"url": "https://www.youtube.com/watch?v=b", "title": "B", "id": "b"},
    ]}
    last_opts = {}

    def __init__(self, opts):
        FakeListYDL.last_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True):
        return self.info


def test_expand_collection_lists_entries(monkeypatch):
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeListYDL)
    result = expand_collection("https://www.youtube.com/@x")
    assert result.platform == "youtube"
    assert [e.title for e in result.entries] == ["A", "B"]
    assert result.error is None
    # The listing must never download and must not be a noplaylist call.
    assert FakeListYDL.last_opts["skip_download"] is True
    assert FakeListYDL.last_opts["noplaylist"] is False
    assert FakeListYDL.last_opts["extract_flat"] == "in_playlist"


class FakeEmptyYDL(FakeListYDL):
    info = {"entries": []}


def test_expand_collection_empty_is_an_error(monkeypatch):
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeEmptyYDL)
    result = expand_collection("https://www.youtube.com/@x")
    assert result.entries == []
    assert result.error
    assert result.category == "not_found"


class FakeBoomYDL:
    def __init__(self, opts):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True):
        raise RuntimeError("Sign in to confirm you are not a bot")


def test_expand_collection_classifies_failure(monkeypatch):
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeBoomYDL)
    result = expand_collection("https://www.instagram.com/someuser/")
    assert result.category == "blocked"
    assert result.error
    # Instagram's honest note wins over the generic classify_error message.
    assert "post" in result.error.lower()

from sites.collections import normalize_collection_url


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/channel/UCabc",
         "https://www.youtube.com/channel/UCabc/videos"),
        ("https://www.youtube.com/channel/UCabc/",
         "https://www.youtube.com/channel/UCabc/videos"),
        ("https://www.youtube.com/@somechannel",
         "https://www.youtube.com/@somechannel/videos"),
        ("https://www.youtube.com/c/SomeName",
         "https://www.youtube.com/c/SomeName/videos"),
        ("https://www.youtube.com/user/SomeName",
         "https://www.youtube.com/user/SomeName/videos"),
        ("https://m.youtube.com/@handle",
         "https://m.youtube.com/@handle/videos"),
        ("https://www.youtube.com/channel/UCabc/videos",
         "https://www.youtube.com/channel/UCabc/videos"),
        ("https://www.youtube.com/channel/UCabc/shorts",
         "https://www.youtube.com/channel/UCabc/shorts"),
        ("https://www.youtube.com/playlist?list=PL123",
         "https://www.youtube.com/playlist?list=PL123"),
        ("https://www.instagram.com/someuser/",
         "https://www.instagram.com/someuser/"),
        ("https://www.tiktok.com/@user",
         "https://www.tiktok.com/@user"),
    ],
)
def test_normalize_collection_url(url, expected):
    assert normalize_collection_url(url) == expected


def test_expand_collection_empty_uses_platform_note(monkeypatch):
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeEmptyYDL)
    result = expand_collection("https://www.tiktok.com/@someuser")
    assert result.category == "not_found"
    assert "tiktok" in result.error.lower()
    assert "cookie" in result.error.lower() or "paste" in result.error.lower()


def test_expand_collection_empty_unknown_platform_is_actionable(monkeypatch):
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeEmptyYDL)
    result = expand_collection("https://example.com/someuser")
    assert result.category == "not_found"
    assert "pasting" in result.error.lower()
