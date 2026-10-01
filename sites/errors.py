from sites.cookies import detect_platform, get_platform_display_name

BLOCKED_KEYWORDS = ("Sign in to confirm", "bot", "cookies", "reloaded", "reload", "page needs")
FORMAT_KEYWORDS = ("Requested format",)
NETWORK_KEYWORDS = (
    "urlopen error", "timed out", "Connection refused",
    "Temporary failure in name resolution", "network is unreachable",
)
NOT_FOUND_KEYWORDS = (
    "404", "Not Found", "Video unavailable",
    "This video is unavailable", "does not exist",
)


def classify_error(message: str, url: str = ""):
    """Map a raw yt-dlp/ffmpeg error to (category, user-facing message).

    Categories: "blocked", "format", "ffmpeg", "network", "not_found", "other".
    """
    text = message or ""
    if any(keyword in text for keyword in BLOCKED_KEYWORDS):
        platform = detect_platform(url) if url else ""
        site = get_platform_display_name(platform) if platform else "The site"
        return "blocked", f"{site} blocked the request. Load a cookies.txt file and try again."
    if any(keyword in text for keyword in FORMAT_KEYWORDS):
        return "format", "Could not find a downloadable format. The video may be unavailable or region-locked."
    if "ffmpeg" in text.lower():
        return "ffmpeg", (
            "ffmpeg is not installed or not in PATH. "
            "Install it from https://ffmpeg.org/download.html and add to PATH."
        )
    if any(k in text for k in NETWORK_KEYWORDS):
        return "network", "Network error reaching the site. Check your connection and retry."
    if any(k in text for k in NOT_FOUND_KEYWORDS):
        return "not_found", "The video was not found. It may be deleted, private, or region-locked."
    return "other", text
