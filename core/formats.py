"""Curated registry of output formats.

Pure data table: no I/O, no ffmpeg, no Qt. Later stages use the per-format
``remux_v`` / ``remux_a`` allow-lists to decide remux vs re-encode.

Only editor-safe codecs are ever written: every video format targets H.264 and
every audio format targets AAC, MP3, or PCM, so output imports into CapCut,
Premiere Pro, After Effects, and DaVinci Resolve.
"""

from dataclasses import dataclass

EDITOR_SAFE_V = ("h264",)
EDITOR_SAFE_A = ("aac", "mp3", "pcm_s16le")


@dataclass(frozen=True)
class Format:
    key: str
    label: str
    kind: str
    container: str
    vcodec: str
    acodec: str
    extension: str
    remux_v: tuple
    remux_a: tuple


FORMATS = [
    Format(
        key="mp4",
        label="MP4 (H.264 + AAC)",
        kind="video",
        container="mp4",
        vcodec="h264",
        acodec="aac",
        extension="mp4",
        remux_v=("h264",),
        remux_a=("aac", "mp3"),
    ),
    Format(
        key="mkv",
        label="MKV (H.264 + AAC)",
        kind="video",
        container="matroska",
        vcodec="h264",
        acodec="aac",
        extension="mkv",
        remux_v=("h264",),
        remux_a=("aac", "mp3"),
    ),
    Format(
        key="webm",
        label="WebM (H.264 + AAC, editor-friendly)",
        kind="video",
        container="webm",
        vcodec="h264",
        acodec="aac",
        extension="webm",
        remux_v=("h264",),
        remux_a=("aac", "mp3"),
    ),
    Format(
        key="mov",
        label="MOV (H.264 + AAC)",
        kind="video",
        container="mov",
        vcodec="h264",
        acodec="aac",
        extension="mov",
        remux_v=("h264",),
        remux_a=("aac", "pcm_s16le"),
    ),
    Format(
        key="avi",
        label="AVI (H.264 + MP3)",
        kind="video",
        container="avi",
        vcodec="h264",
        acodec="mp3",
        extension="avi",
        remux_v=("h264",),
        remux_a=("mp3", "pcm_s16le"),
    ),
    Format(
        key="gif",
        label="GIF (no audio)",
        kind="video",
        container="gif",
        vcodec="gif",
        acodec="none",
        extension="gif",
        remux_v=(),
        remux_a=(),
    ),
    Format(
        key="mp3",
        label="MP3 (audio)",
        kind="audio",
        container="mp3",
        vcodec="",
        acodec="mp3",
        extension="mp3",
        remux_v=(),
        remux_a=("mp3",),
    ),
    Format(
        key="m4a",
        label="M4A (AAC audio)",
        kind="audio",
        container="ipod",
        vcodec="",
        acodec="aac",
        extension="m4a",
        remux_v=(),
        remux_a=("aac",),
    ),
    Format(
        key="wav",
        label="WAV (PCM audio)",
        kind="audio",
        container="wav",
        vcodec="",
        acodec="pcm_s16le",
        extension="wav",
        remux_v=(),
        remux_a=("pcm_s16le",),
    ),
    Format(
        key="aac",
        label="AAC (audio)",
        kind="audio",
        container="adts",
        vcodec="",
        acodec="aac",
        extension="aac",
        remux_v=(),
        remux_a=("aac",),
    ),
]

_BY_KEY = {f.key: f for f in FORMATS}


def get(key):
    return _BY_KEY.get(key)


def for_kind(kind):
    return [f for f in FORMATS if f.kind == kind]


def keys():
    return [f.key for f in FORMATS]
