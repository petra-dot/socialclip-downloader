import os
import re

OUTPUT_FORMATS = ["Video (MP4)", "Audio (MP3)"]
RESOLUTIONS = ["720", "1080", "1440", "2160"]

# "Best" means no re-encode, so it replaces the old "Convert to chosen
# resolution" checkbox with one option in the resolution combo.
BEST_RESOLUTION = "Best (no re-encode)"


def resolution_to_convert(choice: str) -> bool:
    """True when a resolution choice should trigger a re-encode."""
    return choice != BEST_RESOLUTION


def output_index_for(value: str) -> int:
    """Map a preset output code ("MP4"/"MP3") to its OUTPUT_FORMATS index."""
    for index, text in enumerate(OUTPUT_FORMATS):
        if text == value or (value and value in text):
            return index
    return -1


def output_code_for(value: str) -> str:
    """Map an OUTPUT_FORMATS label or a short code to "MP4" or "MP3".

    The GUI stores the combo's label ("Audio (MP3)") and built-in presets store
    the code ("MP3"); both must resolve to the same thing.
    """
    return "MP3" if "MP3" in (value or "").upper() else "MP4"


def default_download_folder():
    home = os.path.expanduser("~")
    downloads = os.path.join(home, "Downloads")
    return downloads if os.path.isdir(downloads) else home


def restore_or(default: str, value) -> str:
    """Return a saved setting, falling back to the default when empty or missing."""
    if value is None:
        return default
    value = str(value).strip()
    return value or default


# A title that is just the site's own name tells us nothing, and naming a file
# after it is worse than useless. Facebook returns exactly this when a cookie
# file is supplied.
GENERIC_TITLES = frozenset((
    "facebook", "youtube", "instagram", "tiktok", "twitter", "x", "douyin",
    "bilibili", "video", "untitled", "unknown",
))


def is_generic_title(title, info=None) -> bool:
    """True when `title` carries no information about the video. Pure.

    Empty, a known site name, or the extractor's own name all count.
    """
    text = (title or "").strip()
    if not text:
        return True
    lowered = text.lower()
    if lowered in GENERIC_TITLES:
        return True
    if info:
        site = (info.get("extractor_key") or info.get("extractor") or "")
        if site and lowered == site.lower():
            return True
    return False


def clean_title(title: str) -> str:
    if not title:
        return "video"
    safe = re.sub(r"[\\/:*?\"<>|]", " ", title)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe[:120] or "video"


def get_uploader(info: dict) -> str:
    for k in ("uploader", "channel", "creator", "uploader_id"):
        v = info.get(k)
        if v:
            return v
    return ""


# Two videos can share a title (Facebook returns a generic "Facebook" when a
# cookie file is sent), and two concurrent downloads of such videos would then
# share one output path and fail inside yt-dlp's converter. The id makes every
# path unique per video. Single-tab downloads build their own unique base
# instead and do not use this template.
OUTPUT_TEMPLATE = "%(title)s [%(id)s].%(ext)s"


def clean_download_base(base: str, video_id: str = "") -> str:
    """Drop the " [<id>]" uniqueness token OUTPUT_TEMPLATE writes.

    Only the exact token for a known id is removed, so a title that genuinely
    ends in brackets is left alone.
    """
    if not base or not video_id:
        return base
    suffix = " [%s]" % video_id
    if base.endswith(suffix):
        return base[: -len(suffix)]
    return base


def make_unique_filepath(
    save_dir: str, base_filename: str, ext: str, fallback_id: str = None
) -> str:
    candidate = os.path.join(save_dir, f"{base_filename}.{ext}")
    if not os.path.exists(candidate):
        return candidate
    if fallback_id:
        candidate2 = os.path.join(save_dir, f"{base_filename}_{fallback_id}.{ext}")
        if not os.path.exists(candidate2):
            return candidate2
    i = 1
    while True:
        candidate3 = os.path.join(save_dir, f"{base_filename}_{i}.{ext}")
        if not os.path.exists(candidate3):
            return candidate3
        i += 1
