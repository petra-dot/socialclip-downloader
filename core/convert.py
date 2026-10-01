import os
import subprocess
from collections import namedtuple

from core.manifest import DownloadResult, error_result
from core.pipeline import plan_postprocess
from utils.ffmpeg import ffmpeg_path
from utils.ydl_opts import _ffmpeg_to_nle_mp4, ffprobe_get_height


ConvertPlan = namedtuple("ConvertPlan", "mode vcodec acodec container")


def plan_conversion(src_info, target, copy_streams=None):
    v = (src_info or {}).get("vcodec", "") or ""
    a = (src_info or {}).get("acodec", "") or ""

    if target.kind == "audio":
        if copy_streams is False or a not in target.remux_a:
            return ConvertPlan("transcode", "", target.acodec, target.container)
        return ConvertPlan("remux", "", "copy", target.container)

    v_ok = v in target.remux_v
    a_ok = a in target.remux_a
    if copy_streams is True:
        return ConvertPlan("remux", "copy", "copy", target.container)
    if copy_streams is None and v_ok and a_ok and target.remux_v:
        return ConvertPlan("remux", "copy", "copy", target.container)
    return ConvertPlan("transcode", target.vcodec, target.acodec, target.container)


def _extension(path: str) -> str:
    return os.path.splitext(path)[1].lstrip(".")


def convert_file(input_path: str, output_type: str,
                 target_resolution: int = None) -> DownloadResult:
    try:
        if not os.path.exists(input_path):
            return error_result("not_found", "Input file does not exist.", "")

        base = os.path.splitext(input_path)[0]

        if output_type in ("MP3", "WAV"):
            if output_type == "MP3":
                out_path = base + ".mp3"
                cmd = [
                    ffmpeg_path(), "-i", input_path,
                    "-q:a", "0", "-map", "a",
                    "-y", out_path,
                ]
            else:
                out_path = base + ".wav"
                cmd = [
                    ffmpeg_path(), "-i", input_path,
                    "-vn", "-acodec", "pcm_s16le",
                    "-ar", "44100", "-ac", "2",
                    "-y", out_path,
                ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                return error_result("ffmpeg", result.stderr.decode(errors="ignore"), "")
            return DownloadResult(status="ok", path=out_path, extension=output_type.lower())

        if output_type == "MP4":
            src_height = ffprobe_get_height(input_path)
            if src_height == 0:
                return error_result(
                    "other", "Conversion aborted: unknown source resolution.", ""
                )
            action = plan_postprocess("MP4", True, src_height, target_resolution)
            if action == "skip_low":
                return DownloadResult(
                    status="ok",
                    path=input_path,
                    extension=_extension(input_path),
                    message=(
                        f"Skipped conversion: source ({src_height}p) is lower than "
                        f"target ({target_resolution}p). No upscaling."
                    ),
                )
            if action == "skip_equal":
                return DownloadResult(
                    status="ok",
                    path=input_path,
                    extension=_extension(input_path),
                    message=(
                        f"Skipped conversion: source resolution equals target "
                        f"({src_height}p)."
                    ),
                )
            out_path = f"{base}_{target_resolution}p.mp4"
            result = _ffmpeg_to_nle_mp4(input_path, out_path, target_resolution)
            if result.returncode != 0:
                return error_result("ffmpeg", result.stderr.decode(errors="ignore"), "")
            return DownloadResult(status="ok", path=out_path, extension="mp4")

        return error_result("other", "Unknown conversion parameters.", "")

    except Exception as e:
        return error_result("other", f"Error during conversion: {e}", "")
