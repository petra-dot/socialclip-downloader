import os
import subprocess

from core.manifest import error_result, result_from_info
from core.pipeline import plan_postprocess
from sites.errors import classify_error
from utils.ffmpeg import ffmpeg_path
from utils.ydl_opts import (
    _ffmpeg_to_nle_mp4,
    _nle_ydl_opts,
    ffprobe_get_height,
    strip_ansi,
)


class DownloadCancelled(Exception):
    """Raised from the progress hook when the caller requests cancellation."""


def _cleanup_partial(path):
    """Remove the artifact and <base>*.part siblings this run created."""
    import glob
    if not path:
        return
    base, _ = os.path.splitext(path)
    for candidate in [path] + glob.glob(base + "*.part"):
        try:
            if os.path.isfile(candidate):
                os.remove(candidate)
        except OSError:
            pass


def download_one(url, outtmpl, output_type, convert, target_resolution,
                 cookies_file=None, progress=None, cancel=None,
                 subtitles=False, embed_thumbnail=False, format_id=None):
    in_flight = {"path": ""}
    try:
        from yt_dlp import YoutubeDL

        def hook(d):
            # yt-dlp puts the in-progress filename in the progress dict.
            if d.get("filename"):
                in_flight["path"] = d["filename"]
            if cancel and cancel():
                raise DownloadCancelled()
            if progress:
                if d.get("status") == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate")
                    if total:
                        progress(int(d.get("downloaded_bytes", 0) / total * 100))
                elif d.get("status") == "finished":
                    progress(100)

        hooks = [hook] if (progress or cancel) else []

        ydl_opts = _nle_ydl_opts(
            outtmpl=outtmpl, progress_hooks=hooks, cookies_file=cookies_file
        )
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return error_result(
                    "not_found",
                    "Could not extract video info. The video may be private, "
                    "deleted, or region-locked.",
                    url,
                )
            downloaded_file = ydl.prepare_filename(info)

        if not os.path.exists(downloaded_file):
            base = os.path.splitext(downloaded_file)[0]
            if os.path.exists(base + ".mp4"):
                downloaded_file = base + ".mp4"

        final_height = info.get("height") or ffprobe_get_height(downloaded_file)
        action = plan_postprocess(output_type, convert, final_height, target_resolution)
        final_path = downloaded_file

        if action == "audio":
            mp3_path = os.path.splitext(downloaded_file)[0] + ".mp3"
            cmd = [ffmpeg_path(), "-i", downloaded_file, "-q:a", "0", "-map", "a",
                   "-y", mp3_path]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                return error_result(
                    "ffmpeg",
                    result.stderr.decode(errors="ignore"),
                    url,
                )
            os.remove(downloaded_file)
            final_path = mp3_path
        elif action == "convert":
            base, _ = os.path.splitext(downloaded_file)
            out_file = f"{base}_{target_resolution}p.mp4"
            result = _ffmpeg_to_nle_mp4(downloaded_file, out_file, target_resolution)
            if result.returncode != 0:
                return error_result("ffmpeg", result.stderr.decode(errors="ignore"), url)
            os.remove(downloaded_file)
            final_path = out_file

        if action == "skip_low":
            message = (f"Skipped conversion: source ({final_height}p) is lower than "
                       f"target ({target_resolution}p). No upscaling.")
        elif action == "skip_equal":
            message = (f"Skipped conversion: source resolution equals target "
                       f"({final_height}p).")
        elif action == "audio":
            message = f"MP3 saved: {final_path}"
        elif action == "convert":
            message = f"Conversion completed: {final_path}"
        else:
            message = f"Download finished: {final_path}"

        manifest = result_from_info(info, final_path, url)
        manifest.message = message
        # Extension must describe the artifact we actually hand back, not the
        # container yt-dlp extracted (e.g. MP3 output keeps info["ext"] == "mp4").
        manifest.extension = os.path.splitext(final_path)[1].lstrip(".")
        manifest.height = final_height or manifest.height
        manifest.bytes = os.path.getsize(final_path) if os.path.isfile(final_path) else 0
        return manifest

    except DownloadCancelled:
        _cleanup_partial(in_flight["path"])
        return error_result("cancelled", "Cancelled.", url)
    except Exception as e:
        _cleanup_partial(in_flight["path"])
        category, message = classify_error(strip_ansi(str(e)), url)
        return error_result(category, message, url)
