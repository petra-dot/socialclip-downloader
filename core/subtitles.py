"""Fetch a video's subtitles as sidecar .srt files, or embed them.

Pure selection helpers plus network and ffmpeg work. No Qt.
"""

import os
import subprocess
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

from utils.ffmpeg import ffmpeg_path

DELIVERIES = ("off", "sidecar", "embed", "both")

# A track is usable only if it offers one of these; an srt is written as-is, a
# vtt is converted. json3/srv sources would need their own parser.
_FORMAT_ORDER = ("srt", "vtt")


@dataclass
class SubtitleTrack:
    lang: str
    kind: str        # "manual" | "auto"
    url: str
    ext: str


def _pick_format(formats):
    for wanted in _FORMAT_ORDER:
        for fmt in formats or []:
            if fmt.get("ext") == wanted and fmt.get("url"):
                return fmt["url"], wanted
    return None


def subtitle_tracks(info) -> List[SubtitleTrack]:
    """Manual and auto tracks from a yt-dlp info dict, srt preferred over vtt."""
    info = info or {}
    tracks: List[SubtitleTrack] = []
    for key, kind in (("subtitles", "manual"), ("automatic_captions", "auto")):
        for lang, formats in (info.get(key) or {}).items():
            picked = _pick_format(formats)
            if not picked:
                continue
            url, ext = picked
            tracks.append(SubtitleTrack(lang=lang, kind=kind, url=url, ext=ext))
    return tracks
