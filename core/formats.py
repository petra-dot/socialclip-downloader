"""Curated registry of output formats.

Pure data table: no I/O, no ffmpeg, no Qt. Later stages use the per-format
``remux_v`` / ``remux_a`` allow-lists to decide remux vs re-encode.
"""

from dataclasses import dataclass


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
        remux_a=("aac", "mp3", "ac3"),
    ),
    Format(
        key="mkv",
        label="MKV (H.264 + AAC)",
        kind="video",
        container="matroska",
        vcodec="h264",
        acodec="aac",
        extension="mkv",
        remux_v=("h264", "hevc", "vp9", "av1"),
        remux_a=("aac", "mp3", "opus", "vorbis", "flac", "ac3"),
    ),
    Format(
        key="webm",
        label="WebM (VP9 + Opus)",
        kind="video",
        container="webm",
        vcodec="vp9",
        acodec="opus",
        extension="webm",
        remux_v=("vp9", "av1"),
        remux_a=("opus", "vorbis"),
    ),
    Format(
        key="mov",
        label="MOV (H.264 + AAC)",
        kind="video",
        container="mov",
        vcodec="h264",
        acodec="aac",
        extension="mov",
        remux_v=("h264", "hevc", "prores"),
        remux_a=("aac", "pcm_s16le"),
    ),
    Format(
        key="avi",
        label="AVI (MPEG-4 + MP3)",
        kind="video",
        container="avi",
        vcodec="mpeg4",
        acodec="mp3",
        extension="avi",
        remux_v=("mpeg4", "mjpeg"),
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
        label="MP3",
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
        label="M4A (AAC)",
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
        label="WAV (PCM)",
        kind="audio",
        container="wav",
        vcodec="",
        acodec="pcm_s16le",
        extension="wav",
        remux_v=(),
        remux_a=("pcm_s16le", "pcm_s24le"),
    ),
    Format(
        key="flac",
        label="FLAC",
        kind="audio",
        container="flac",
        vcodec="",
        acodec="flac",
        extension="flac",
        remux_v=(),
        remux_a=("flac",),
    ),
    Format(
        key="ogg",
        label="OGG (Vorbis)",
        kind="audio",
        container="ogg",
        vcodec="",
        acodec="libvorbis",
        extension="ogg",
        remux_v=(),
        remux_a=("vorbis",),
    ),
    Format(
        key="opus",
        label="Opus",
        kind="audio",
        container="opus",
        vcodec="",
        acodec="libopus",
        extension="opus",
        remux_v=(),
        remux_a=("opus",),
    ),
    Format(
        key="aac",
        label="AAC",
        kind="audio",
        container="adts",
        vcodec="",
        acodec="aac",
        extension="aac",
        remux_v=(),
        remux_a=("aac",),
    ),
    Format(
        key="wma",
        label="WMA",
        kind="audio",
        container="asf",
        vcodec="",
        acodec="wmav2",
        extension="wma",
        remux_v=(),
        remux_a=("wmav2",),
    ),
]

_BY_KEY = {f.key: f for f in FORMATS}


def get(key):
    return _BY_KEY.get(key)


def for_kind(kind):
    return [f for f in FORMATS if f.kind == kind]


def keys():
    return [f.key for f in FORMATS]
