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


def _dest_for(track: SubtitleTrack, base_path: str) -> str:
    suffix = ".auto" if track.kind == "auto" else ""
    return "%s.%s%s.srt" % (base_path, track.lang, suffix)


def write_subtitle(track, base_path, opener=None) -> Optional[str]:
    """Fetch a track and write its sidecar. Returns the path, or None."""
    dest = _dest_for(track, base_path)
    open_url = opener or urllib.request.urlopen
    try:
        request = urllib.request.Request(
            track.url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with open_url(request, timeout=30) as response:
            data = response.read()
    except Exception:  # noqa: BLE001 - a missing subtitle must not fail the download
        return None

    try:
        if track.ext == "srt":
            with open(dest, "wb") as fh:
                fh.write(data)
            return dest

        tmp = dest + ".vtt"
        with open(tmp, "wb") as fh:
            fh.write(data)
        try:
            result = subprocess.run(
                [ffmpeg_path(), "-y", "-i", tmp, dest],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        return dest if result.returncode == 0 else None
    except OSError:  # a missing ffmpeg or an unwritable sidecar must not fail the download
        return None


def embed_command(video_path, subtitles, out_path, ffmpeg="ffmpeg") -> list:
    """ffmpeg args to mux (lang, path) sidecars into the video as mov_text."""
    cmd = [ffmpeg, "-y", "-i", video_path]
    for _lang, path in subtitles:
        cmd += ["-i", path]
    cmd += ["-map", "0"]
    for index in range(len(subtitles)):
        cmd += ["-map", str(index + 1)]
    cmd += ["-c", "copy", "-c:s", "mov_text"]
    for index, (lang, _path) in enumerate(subtitles):
        cmd += ["-metadata:s:s:%d" % index, "language=%s" % lang]
    cmd += [out_path]
    return cmd


def embed_subtitles(video_path, subtitles) -> bool:
    """Mux the sidecars into the video, replacing it only on success."""
    if not subtitles:
        return True
    base, ext = os.path.splitext(video_path)
    out = base + ".subs" + ext
    result = subprocess.run(
        embed_command(video_path, subtitles, out, ffmpeg=ffmpeg_path()),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        try:
            os.remove(out)
        except OSError:
            pass
        return False
    os.replace(out, video_path)
    return True
