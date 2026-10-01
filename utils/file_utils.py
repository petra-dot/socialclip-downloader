import os
import re

OUTPUT_FORMATS = ["Video (MP4)", "Audio (MP3)"]
RESOLUTIONS = ["720", "1080", "1440", "2160"]


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
