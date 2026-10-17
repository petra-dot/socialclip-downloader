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

# Signals that a site wanted authentication rather than that the media is
# genuinely unavailable. Wider than BLOCKED_KEYWORDS, which exists to pick the
# friendly message, not to decide whether cookies are worth trying.
AUTH_KEYWORDS = (
    "sign in", "log in", "login", "logged in", "not a bot", "cookies",
    "account", "private", "members only", "age", "confirm your age",
    "authorization", "unauthorized", "forbidden", "http error 403",
)


def looks_like_auth_error(message: str) -> bool:
    """True when `message` suggests the site wanted authentication. Pure."""
    text = (message or "").lower()
    return any(word in text for word in AUTH_KEYWORDS)


def classify_error(message: str, url: str = ""):
    """Map a raw yt-dlp/ffmpeg error to (category, user-facing message).

    Returns one of: "blocked", "format", "ffmpeg", "network", "not_found",
    "unsupported", "other". A "cancelled" category also exists but is produced
    by ``core.download`` when the user cancels; it is never returned here.
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
    if "unsupported url" in text.lower():
        return "unsupported", "That link is not a video yt-dlp can download from."
    return "other", text
