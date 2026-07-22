import os
import re
import subprocess


def _nle_safe_format_selector() -> str:
    return (
        "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]"
        "/bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]"
        "/bestvideo[ext=mp4]+bestaudio[ext=m4a]"
        "/bestvideo+bestaudio"
        "/best"
    )


def ffprobe_get_height(path: str) -> int:
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=height",
            "-of", "csv=p=0",
            path,
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip()
        if out:
            line = out.splitlines()[0].strip()
            return int(line)
    except Exception:
        pass
    return 0


def _nle_ydl_opts(outtmpl: str, progress_hooks: list = None, cookies_file: str = None) -> dict:
    opts = {
        "format": _nle_safe_format_selector(),
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferredformat": "mp4"}
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
        "no_warnings": False,
        "ignoreerrors": False,
        "age_limit": 99,
        "no_color": True,
    }
    if progress_hooks:
        opts["progress_hooks"] = progress_hooks
    if cookies_file and os.path.isfile(cookies_file):
        opts["cookiefile"] = cookies_file
    return opts


def _ffmpeg_to_nle_mp4(input_path: str, output_path: str, scale_height: int = None) -> subprocess.CompletedProcess:
    vf = f"scale=-2:{scale_height}" if scale_height else "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    cmd = [
        "ffmpeg", "-i", input_path,
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
