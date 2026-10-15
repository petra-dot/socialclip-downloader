import os
import re
import sys
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


def app_dir() -> str:
    """The directory the app runs from.

    Next to the script in a source run, next to the executable in a frozen
    build. Stable no matter which directory the app was launched from, which
    is what makes it a reliable place for cookies and the queue file.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_cookie_dir() -> str:
    """Where cookie files live by default: the app directory.

    The app tells users to drop cookies "next to the app", so that is the
    primary location. The working directory is still searched as a fallback
    (see ``_cookie_search_dirs``), but it no longer decides the result.
    """
    return app_dir()


def _cookie_search_dirs() -> list:
    """Directories to look in for cookie files, most specific first: the app
    directory, then the working directory."""
    dirs = [app_dir()]
    try:
        cwd = os.getcwd()
    except OSError:
        cwd = ""
    if cwd and cwd not in dirs:
        dirs.append(cwd)
    return dirs


def _find_cookie(platform: str, directory: str) -> str:
    """This platform's cookie file in `directory`, exact name first.

    Falls back to any ``*_cookies.txt`` whose name mentions the platform, so a
    browser export named ``www.youtube.com_cookies.txt`` is found too. The
    download path and the Cookies dialog must resolve cookies identically, or
    the dialog claims "none" while downloads are using a file.
    """
    for name in (f"{platform}_cookies.txt", f"{platform}.txt"):
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return path
    try:
        for fname in os.listdir(directory):
            if fname.lower().endswith("_cookies.txt") and platform in fname.lower():
                return os.path.join(directory, fname)
    except OSError:
        pass
    return ""


def cookie_file_for(platform: str, cookie_dir: str = None) -> str:
    """Path to this platform's cookie file, or "" when absent.

    With an explicit ``cookie_dir`` only that directory is checked; otherwise
    the search dirs are used.
    """
    if cookie_dir is not None:
        return _find_cookie(platform, cookie_dir)
    for directory in _cookie_search_dirs():
        found = _find_cookie(platform, directory)
        if found:
            return found
    return ""


def get_cookie_path(url: str, cookie_dir: str = None) -> str:
    """Path to the cookie file that applies to `url`, or "" when absent."""
    platform = detect_platform(url)
    if not platform:
        return ""
    return cookie_file_for(platform, cookie_dir)


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


BROWSERS = ("chrome", "chromium", "firefox", "edge", "brave", "opera",
            "vivaldi", "safari", "whale")


def cookie_status() -> list:
    """One (platform, display_name, file_path) per known platform.

    ``file_path`` is "" when no cookie file exists for that platform. This is
    a file-presence report only; it never reads a browser.
    """
    return [
        (platform, get_platform_display_name(platform),
         cookie_file_for(platform))
        for platform in PLATFORM_NAMES
    ]
