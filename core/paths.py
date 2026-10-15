"""Where the app keeps writable state: a per-user data directory.

Next to the executable is read-only in several real installs (a macOS app run
from a quarantined download, a Linux binary in /usr/local/bin, anything under
Program Files), so cookies and the queue could silently fail to save. This
module resolves one writable directory and copies any legacy files into it once.

Qt-free: the CLI uses it too.
"""

import os
import sys

DATA_ENV = "SOCIALCLIP_DATA"
APP_DIR_NAME = "SocialClip Downloader"

# State that used to live next to the app and must survive the move.
LEGACY_FILES = ("queue.json", "presets.json", "archive.txt")


def legacy_dir() -> str:
    """The directory state lived in before this module: the app directory."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_data_dir() -> str:
    """The platform's per-user data directory for this app."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_DIR_NAME)
    if sys.platform == "darwin":
        return os.path.join(
            os.path.expanduser("~"), "Library", "Application Support", APP_DIR_NAME
        )
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    return os.path.join(base, "socialclip")


def data_dir() -> str:
    """The writable data directory, created on demand.

    Falls back to the app directory when the per-user directory cannot be
    created, so the app still runs.
    """
    target = os.environ.get(DATA_ENV) or default_data_dir()
    try:
        os.makedirs(target, exist_ok=True)
    except OSError:
        return legacy_dir()
    return target


def data_dir_writable() -> bool:
    """True when a file can be created in the data directory."""
    try:
        probe = os.path.join(data_dir(), ".write-test")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("")
        os.remove(probe)
        return True
    except OSError:
        return False


def queue_path() -> str:
    """The queue file: the SOCIALCLIP_QUEUE override, else the data dir."""
    override = os.environ.get("SOCIALCLIP_QUEUE")
    if override:
        return override
    return os.path.join(data_dir(), "queue.json")


def managed_dir(kind: str) -> str:
    """A subdirectory for a managed component: "yt-dlp" or "bin"."""
    return os.path.join(data_dir(), kind)


def _legacy_names(directory: str) -> list:
    names = list(LEGACY_FILES)
    try:
        for fname in os.listdir(directory):
            if fname.lower().endswith("_cookies.txt"):
                names.append(fname)
    except OSError:
        pass
    return names


def migrate_legacy_files() -> list:
    """Copy legacy app-dir state into the data dir. Returns the names copied.

    Copies only, never moves or deletes, and never overwrites: a file already in
    the data directory is the current one.
    """
    source = legacy_dir()
    target = data_dir()
    if os.path.abspath(source) == os.path.abspath(target):
        return []
    copied = []
    for name in _legacy_names(source):
        src = os.path.join(source, name)
        dst = os.path.join(target, name)
        if not os.path.isfile(src) or os.path.exists(dst):
            continue
        try:
            with open(src, "rb") as fh:
                data = fh.read()
            with open(dst, "wb") as fh:
                fh.write(data)
        except OSError:
            continue
        copied.append(name)
    return copied
