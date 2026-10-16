"""Classify a URL as a single video or a collection (playlist, channel,
profile), and describe how reliable listing is per platform.

Pure: no network, no Qt. The listing itself lives in core/collections.py.
"""

import re
from urllib.parse import urlparse

# A URL that points at one video. Checked first, so a video URL that also
# carries a playlist parameter (watch?v=X&list=Y) stays a single video.
VIDEO_PATTERNS = (
    r"youtube\.com/watch",
    r"instagram\.com/(?:p|reel|tv)/",
    r"(?:twitter|x)\.com/[^/]+/status/",
    r"tiktok\.com/@[^/]+/video/",
    r"facebook\.com/(?:watch|reel|.*?/videos/)",
    r"bilibili\.com/video/",
    r"douyin\.com/video/",
)

# A URL that points at many videos.
COLLECTION_PATTERNS = (
    r"youtube\.com/playlist",
    r"youtube\.com/(?:@[^/]+|channel/|c/|user/)",
    r"instagram\.com/[^/]+/?$",
    r"tiktok\.com/@[^/]+/?$",
    r"(?:twitter|x)\.com/[^/]+/?$",
    r"facebook\.com/[^/]+/?$",
    r"space\.bilibili\.com/\d+",
    r"bilibili\.com/space/",
    r"douyin\.com/user/",
)

# A bare YouTube channel URL (no trailing tab path). yt-dlp flat-extracts such
# a URL into the channel's tabs (Videos, Shorts, ...), not the videos, so the
# Videos tab has to be named explicitly.
_YOUTUBE_BARE_CHANNEL = re.compile(
    r"^(?:[\w-]+\.)*youtube\.com/(?:channel/[\w-]+|@[\w.-]+|c/[\w.-]+|user/[\w.-]+)$"
)

_NOTES = {
    "instagram": "Instagram does not list a profile's posts reliably without a "
                 "login. Add an instagram_cookies.txt next to the app, or paste "
                 "individual post or reel links instead.",
    "tiktok": "TikTok rate-limits profile listing and usually needs a login. "
              "Add a tiktok_cookies.txt next to the app, or paste individual "
              "video links instead.",
    "twitter": "Twitter/X does not list a timeline without a login. Add a "
               "twitter_cookies.txt next to the app, or paste individual post "
               "links instead.",
    "facebook": "Facebook does not allow listing a profile's videos. Paste "
                "individual video links instead.",
    "douyin": "Douyin does not list a profile's videos reliably. Add a "
              "douyin_cookies.txt next to the app, or paste individual video "
              "links instead.",
    "bilibili": "Bilibili channel listing may need a login. Add a "
                "bilibili_cookies.txt next to the app, or paste individual "
                "video links instead.",
}


def _target(url: str) -> str:
    """Host + path + query, lowercased, without the scheme."""
    if not url:
        return ""
    if "//" not in url:
        url = "//" + url
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    if not host:
        return ""
    path = (parsed.path or "").rstrip("/")
    target = host + path
    if parsed.query:
        target += "?" + parsed.query
    return target


def classify_url(url: str) -> str:
    """Return "video", "collection", or "unknown"."""
    target = _target(url)
    if not target:
        return "unknown"
    for pattern in VIDEO_PATTERNS:
        if re.search(pattern, target):
            return "video"
    for pattern in COLLECTION_PATTERNS:
        if re.search(pattern, target):
            return "collection"
    return "unknown"


def collection_note(platform: str) -> str:
    """Honest expectation text for listing this platform. Empty when reliable."""
    return _NOTES.get((platform or "").lower(), "")


def normalize_collection_url(url: str) -> str:
    """Point a bare YouTube channel URL at its Videos tab.

    Every other URL is returned unchanged.
    """
    if not url:
        return url
    if _YOUTUBE_BARE_CHANNEL.match(_target(url)):
        return url.rstrip("/") + "/videos"
    return url
