"""yt-dlp environment helpers: the JavaScript runtime it needs, and its age.

The Python API is not the command-line tool. ``YoutubeDL`` does not read the
user's yt-dlp config file, and its only default JavaScript runtime is deno. A
machine with node but no deno therefore extracts YouTube without a runtime,
and YouTube answers the media request with HTTP 403. So the app detects a
runtime itself and passes it explicitly.
"""

import datetime
import shutil
from typing import Optional

# Preference order: yt-dlp's own default first, then the runtime most likely
# to be installed already on an editor's machine.
RUNTIMES = ("deno", "node", "bun", "quickjs")

# yt-dlp warns at 90 days; YouTube extraction breaks well before a year.
STALE_AFTER_DAYS = 90


def find_js_runtime(which=None):
    """(name, path) of the first available JS runtime, or ("", "")."""
    which = shutil.which if which is None else which
    for name in RUNTIMES:
        try:
            found = which(name)
        except Exception:
            found = None
        if found:
            return name, found
    return "", ""


def js_runtimes(which=None) -> dict:
    """The yt-dlp ``js_runtimes`` option, or {} when nothing is installed."""
    name, path = find_js_runtime(which=which)
    if not name:
        return {}
    return {name: {"path": path}}


def ytdlp_version() -> str:
    """The installed yt-dlp version, or "" when it cannot be read."""
    try:
        from yt_dlp.version import __version__
        return __version__
    except Exception:
        return ""


def version_age_days(version: str, today=None) -> Optional[int]:
    """Age in days of a date-stamped version like '2026.07.04'.

    None when the version is not a date. Pure; ``today`` is injectable.
    """
    parts = (version or "").split(".")
    if len(parts) < 3:
        return None
    try:
        released = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (TypeError, ValueError):
        return None
    today = today or datetime.date.today()
    return (today - released).days


def is_stale(version: str, today=None) -> bool:
    """True when yt-dlp is older than STALE_AFTER_DAYS.

    An undateable version is not stale: better to say nothing than to nag.
    """
    age = version_age_days(version, today=today)
    if age is None:
        return False
    return age > STALE_AFTER_DAYS
