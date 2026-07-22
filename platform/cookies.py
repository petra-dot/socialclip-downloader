import os
import re


PLATFORM_PATTERNS = [
    (r"(?:www\.)?youtube\.com|youtu\.be", "youtube"),
    (r"(?:www\.)?douyin\.com|v\.douyin\.com|iesdouyin\.com", "douyin"),
    (r"(?:www\.)?instagram\.com", "instagram"),
    (r"(?:www\.)?twitter\.com|x\.com", "twitter"),
    (r"(?:www\.)?tiktok\.com|vm\.tiktok\.com", "tiktok"),
    (r"(?:www\.)?bilibili\.com", "bilibili"),
]


def detect_platform(url: str) -> str:
    for pattern, name in PLATFORM_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return name
    return ""


def get_cookie_path(url: str, cookie_dir: str = None) -> str:
    platform = detect_platform(url)
    if not platform:
        return ""
    if cookie_dir is None:
        cookie_dir = os.getcwd()
    candidates = [
        os.path.join(cookie_dir, f"{platform}_cookies.txt"),
        os.path.join(cookie_dir, f"{platform}.txt"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ""


def get_cookie_message(platform: str) -> str:
    messages = {
        "douyin": "Douyin requires cookies. Export from your browser after visiting douyin.com and save as douyin_cookies.txt.",
        "instagram": "Instagram may require cookies. Export and save as instagram_cookies.txt.",
        "twitter": "Twitter/X may require cookies. Export and save as twitter_cookies.txt.",
        "tiktok": "TikTok may require cookies. Export and save as tiktok_cookies.txt.",
        "bilibili": "Bilibili may require cookies. Export and save as bilibili_cookies.txt.",
    }
    return messages.get(platform, "")
