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
    build. Used to locate bundled resources and as a legacy cookie fallback;
    writable state lives in the per-user data directory instead.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_cookie_dir() -> str:
    """Where cookie files live by default: the per-user data directory.

    Next to the executable is read-only in several real installs, so the app
    keeps cookies (and the queue) in a writable per-user directory instead.
    """
    from core.paths import data_dir
    return data_dir()


def cookie_dialog_dir(current_path: str = "") -> str:
    """The folder the cookie file dialog should open in.

    The folder of `current_path` when it names an existing file, else the
    directory the app's cookie files live in. Pure apart from the filesystem.
    """
    current_path = (current_path or "").strip()
    if current_path:
        directory = os.path.dirname(current_path)
        if directory and os.path.isdir(directory):
            return directory
    return default_cookie_dir()


def _cookie_search_dirs() -> list:
    """Directories to look in for cookie files, most specific first.

    The per-user data directory is where cookies live now; the app directory is
    kept as a fallback so cookies dropped beside the app still resolve before
    the one-time migration has run.
    """
    from core.paths import data_dir

    dirs = []
    for directory in (data_dir(), app_dir()):
        if directory and directory not in dirs:
            dirs.append(directory)
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


def cookie_file_platform(path) -> str:
    """The platform a cookie file belongs to, or "" when the name tells us nothing.

    'www.youtube.com_cookies.txt' -> 'youtube'. Pure apart from os.path.
    """
    name = os.path.basename(path or "").lower()
    for suffix in ("_cookies.txt", ".txt"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    if not name:
        return ""
    platform = detect_platform(name)
    if platform:
        return platform
    for key in PLATFORM_NAMES:
        if key in name:
            return key
    return ""


def resolve_cookie_file(url: str, override: str = "") -> str:
    """The cookie file to use for `url`. Pure apart from the filesystem.

    A manual override is used only for the platform its own filename names, so
    a YouTube cookie file is never sent to Douyin. When the filename tells us
    nothing, the override is used for every URL, so a deliberately generic file
    still works. Otherwise the URL's own platform file applies, or none.
    """
    override = (override or "").strip()
    platform = detect_platform(url)
    if override:
        owner = cookie_file_platform(override)
        if not owner or (platform and owner == platform):
            return override
        return get_cookie_path(url) if platform else ""
    return get_cookie_path(url)


def cookie_box_value(url: str, current: str = "") -> str:
    """The cookie file a URL should show in the Cookies file box.

    This is exactly the file `download_one` will use for `url`: the box's own
    value when it applies to this URL's platform, otherwise the detected
    per-URL file (or ""). Pure apart from the filesystem.
    """
    return resolve_cookie_file(url, current)


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
