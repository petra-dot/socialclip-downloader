import os
import re
from urllib.parse import urlparse


# Matched with re.fullmatch against the URL's hostname, so substrings
# ("app.box.com" matching "x.com") cannot false-positive.
PLATFORM_PATTERNS = [
    (r"(?:[\w-]+\.)*youtube\.com|(?:[\w-]+\.)*youtu\.be", "youtube"),
    (r"(?:[\w-]+\.)*(?:ies)?douyin\.com", "douyin"),
    (r"(?:[\w-]+\.)*instagram\.com", "instagram"),
    (r"(?:[\w-]+\.)*twitter\.com|(?:[\w-]+\.)*x\.com", "twitter"),
    (r"(?:[\w-]+\.)*tiktok\.com", "tiktok"),
    (r"(?:[\w-]+\.)*bilibili\.com", "bilibili"),
    (r"(?:[\w-]+\.)*facebook\.com|fb\.watch|(?:[\w-]+\.)*fb\.com", "facebook"),
]


def _hostname(url: str) -> str:
    if "//" not in url:
        url = "//" + (url or "")
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def detect_platform(url: str) -> str:
    host = _hostname(url or "")
    if not host:
        return ""
    for pattern, name in PLATFORM_PATTERNS:
        if re.fullmatch(pattern, host):
            return name
    return ""


def default_cookie_dir() -> str:
    """Directory to look for cookie files in.

    Prefers the current working directory (where the user runs / drops the
    file), but falls back to the app directory so packaged builds work when
    launched from elsewhere.
    """
    cwd = os.getcwd()
    if _has_cookie_file(cwd):
        return cwd
    return os.path.dirname(os.path.abspath(__file__))


def _has_cookie_file(directory: str) -> bool:
    try:
        return any(
            name.lower().endswith("_cookies.txt") for name in os.listdir(directory)
        )
    except OSError:
        return False


def cookie_file_for(platform: str, cookie_dir: str = None) -> str:
    """Path to this platform's cookie file, or "" when absent."""
    if cookie_dir is None:
        cookie_dir = default_cookie_dir()
    candidates = [
        os.path.join(cookie_dir, f"{platform}_cookies.txt"),
        os.path.join(cookie_dir, f"{platform}.txt"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ""


def get_cookie_path(url: str, cookie_dir: str = None) -> str:
    platform = detect_platform(url)
    if not platform:
        return ""
    if cookie_dir is None:
        cookie_dir = default_cookie_dir()
    path = cookie_file_for(platform, cookie_dir)
    if path:
        return path
    try:
        for fname in os.listdir(cookie_dir):
            if fname.lower().endswith("_cookies.txt") and platform in fname.lower():
                return os.path.join(cookie_dir, fname)
    except OSError:
        pass
    return ""


PLATFORM_NAMES = {
    "youtube": "YouTube",
    "douyin": "Douyin",
    "instagram": "Instagram",
    "twitter": "Twitter/X",
    "tiktok": "TikTok",
    "bilibili": "Bilibili",
    "facebook": "Facebook",
}


def get_platform_display_name(platform: str) -> str:
    return PLATFORM_NAMES.get(platform, platform.capitalize())


def get_cookie_message(platform: str) -> str:
    messages = {
        "douyin": "Douyin requires cookies. Export from your browser after "
        "visiting douyin.com and save as douyin_cookies.txt.",
        "instagram": "Instagram may require cookies. Export and save as instagram_cookies.txt.",
        "twitter": "Twitter/X may require cookies. Export and save as twitter_cookies.txt.",
        "tiktok": "TikTok may require cookies. Export and save as tiktok_cookies.txt.",
        "bilibili": "Bilibili may require cookies. Export and save as bilibili_cookies.txt.",
        "facebook": "Facebook may require cookies. Export and save as facebook_cookies.txt.",
    }
    return messages.get(platform, "")
