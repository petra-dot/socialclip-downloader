import os
import re
import subprocess

from utils.ffmpeg import ffmpeg_path, ffprobe_path


def _nle_safe_format_selector() -> str:
    """Prefer H.264 + AAC, but accept whatever the site actually offers.

    Preferring H.264 avoids a needless re-encode in the common case, but some
    sites (Instagram Reels among them) serve only VP9/AV1. An H.264-only
    selector fails on those with "Requested format is not available", so the
    fallbacks stay open and a post-download step guarantees the final MP4 is
    H.264/AAC for platforms that require it (WhatsApp, Facebook).
    """
    return (
        "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]"
        "/bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]"
        "/bestvideo[ext=mp4]+bestaudio[ext=m4a]"
        "/bestvideo+bestaudio"
        "/best"
    )


def _ffprobe_height(path: str) -> int:
    cmd = [
        ffprobe_path(), "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=height",
        "-of", "csv=p=0",
        path,
    ]
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip()
    if out:
        return int(out.splitlines()[0].strip())
    return 0


def _ffmpeg_height(path: str) -> int:
    # Fallback for when ffprobe is unavailable (bundled builds ship only ffmpeg).
    cmd = [ffmpeg_path(), "-i", path]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    match = re.search(rb"Video:.*?(\d{2,5})x(\d{2,5})", proc.stderr)
    if match:
        return int(match.group(2))
    return 0


def ffprobe_get_height(path: str) -> int:
    for probe in (_ffprobe_height, _ffmpeg_height):
        try:
            height = probe(path)
            if height:
                return height
        except Exception:
            continue
    return 0


def _nle_ydl_opts(outtmpl: str, progress_hooks: list = None, cookies_file: str = None) -> dict:
    opts = {
        "format": _nle_safe_format_selector(),
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}
        ],
        "postprocessor_args": {
            "ffmpegvideoconvertor": [
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
            ]
        },
        "noplaylist": True,
        "updatetime": False,
        # Silence yt-dlp's own console output so callers own stdout; progress
        # hooks still fire, so the GUI progress bar keeps working.
        "quiet": True,
        "noprogress": True,
        "no_warnings": False,
        "ignoreerrors": False,
        "age_limit": 99,
        "no_color": True,
    }
    resolved_ffmpeg = ffmpeg_path()
    if resolved_ffmpeg != "ffmpeg" and os.path.isfile(resolved_ffmpeg):
        opts["ffmpeg_location"] = resolved_ffmpeg
    if progress_hooks:
        opts["progress_hooks"] = progress_hooks
    if cookies_file and os.path.isfile(cookies_file):
        opts["cookiefile"] = cookies_file
    return opts


def _ffmpeg_to_nle_mp4(input_path: str, output_path: str, scale_height: int = None) -> subprocess.CompletedProcess:
    vf = f"scale=-2:{scale_height}" if scale_height else "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    cmd = [
        ffmpeg_path(), "-i", input_path,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-vf", vf,
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        "-y", output_path,
    ]
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)
