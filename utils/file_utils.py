import os
import re


def default_download_folder():
    home = os.path.expanduser("~")
    downloads = os.path.join(home, "Downloads")
    return downloads if os.path.isdir(downloads) else home


def clean_title(title: str) -> str:
    if not title:
        return "video"
    title_ascii = title.encode("ascii", "ignore").decode("ascii")
    title_ascii = re.sub(r"[#@]", "", title_ascii)
    title_ascii = re.sub(r"[\\/:*?\"<>|]", " ", title_ascii)
    title_ascii = re.sub(r"[^\w\s\-]", "", title_ascii)
    title_ascii = re.sub(r"\s+", " ", title_ascii).strip()
    return title_ascii[:120] or "video"


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
