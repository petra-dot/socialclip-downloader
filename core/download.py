import os
import subprocess

from core.formats import EDITOR_SAFE_A
from core.manifest import error_result, result_from_info
from core.pipeline import plan_postprocess
from core.probe import probe_media
from sites.errors import classify_error
from utils.ffmpeg import ffmpeg_path
from utils.ydl_opts import (
    _ffmpeg_to_nle_mp4,
    _nle_ydl_opts,
    ffprobe_get_height,
    strip_ansi,
)


def needs_universal_reencode(src_info: dict) -> bool:
    """True when a saved MP4 is not H.264 video + editor-safe audio.

    WhatsApp and Facebook reject VP9/AV1/HEVC videos and editors reject
    Opus/Vorbis audio inside MP4. Sites such as Instagram serve those, so
    after downloading we re-encode to guarantee the file is universally
    playable. An unconfirmed codec re-encodes too: a needless re-encode is
    better than a file that uploads nowhere.
    """
    info = src_info or {}
    vcodec = (info.get("vcodec") or "").lower()
    acodec = (info.get("acodec") or "").lower()
    if vcodec != "h264":
        return True
    # An absent audio codec is fine (silent video); a present hostile one is not.
    if acodec and acodec not in EDITOR_SAFE_A:
        return True
    return False


class DownloadCancelled(Exception):
    """Raised from the progress hook when the caller requests cancellation."""


def _cleanup_partial(created_paths):
    """Remove only the files this run wrote.

    ``created_paths`` is the set of in-flight paths the yt-dlp progress hook
    reported. For each, remove the artifact and its exact temp sibling
    (``path + ".part"``). Never glob a shared base: a same-base ``.part`` left
    by an earlier run or another program is not ours to delete.
    """
    for path in created_paths:
        if not path:
            continue
        for candidate in (path, path + ".part"):
            try:
                if os.path.isfile(candidate):
                    os.remove(candidate)
            except OSError:
                pass


def download_one(url, outtmpl, output_type, convert, target_resolution,
                 cookies_file=None, progress=None, cancel=None,
                 subtitles=False, embed_thumbnail=False, format_id=None):
    in_flight = {"created": set()}
    try:
        from yt_dlp import YoutubeDL

        def hook(d):
            # yt-dlp reports the target in `filename` and the temp file it is
            # actually writing in `tmpfilename` (normally `<filename>.part`).
            if d.get("filename"):
                in_flight["created"].add(d["filename"])
            if d.get("tmpfilename"):
                in_flight["created"].add(d["tmpfilename"])
            if cancel and cancel():
                raise DownloadCancelled()
            if progress:
                if d.get("status") == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate")
                    if total:
                        progress(int(d.get("downloaded_bytes", 0) / total * 100))
                elif d.get("status") == "finished":
                    progress(100)

        hooks = [hook]

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

        # Universal-playability guarantee: some sites (Instagram) serve only
        # VP9/AV1. A plain MP4 download can therefore contain a codec that
        # WhatsApp and Facebook reject, so re-encode an H.264-less MP4.
        if action == "keep" and output_type == "MP4" and os.path.isfile(final_path):
            src_info = probe_media(final_path)
            if needs_universal_reencode(src_info):
                base, _ = os.path.splitext(final_path)
                out_file = f"{base}_h264.mp4"
                result = _ffmpeg_to_nle_mp4(final_path, out_file, None)
                if result.returncode != 0:
                    return error_result(
                        "ffmpeg", result.stderr.decode(errors="ignore"), url
                    )
                os.remove(final_path)
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
        elif action == "keep" and final_path != downloaded_file:
            message = f"Re-encoded to H.264: {final_path}"
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
        _cleanup_partial(in_flight["created"])
        return error_result("cancelled", "Cancelled.", url)
    except Exception as e:
        _cleanup_partial(in_flight["created"])
        category, message = classify_error(strip_ansi(str(e)), url)
        return error_result(category, message, url)
