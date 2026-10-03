import os
import subprocess
from collections import namedtuple

from core.formats import EDITOR_SAFE_A, get
from core.manifest import DownloadResult, error_result
from core.pipeline import plan_postprocess
from core.probe import probe_media
from utils.ffmpeg import ffmpeg_path
from utils.ydl_opts import _ffmpeg_to_nle_mp4, ffprobe_get_height


ConvertPlan = namedtuple("ConvertPlan", "mode vcodec acodec container")


def plan_conversion(src_info, target, copy_streams=None):
    v = (src_info or {}).get("vcodec", "") or ""
    a = (src_info or {}).get("acodec", "") or ""
    is_video = target.kind == "video"

    # A forced copy is only honoured for editor-safe streams. Copying a VP9 or
    # Opus source produces a file the editor rejects, so it is upgraded to a
    # transcode even when the caller asked for a copy.
    if copy_streams is True:
        v_copy = v == "h264" if is_video else True
        a_copy = a in EDITOR_SAFE_A
        if v_copy and a_copy:
            return ConvertPlan(
                "remux", "copy" if is_video else "", "copy", target.container
            )
        return ConvertPlan("transcode", target.vcodec, target.acodec, target.container)

    if not is_video:
        if copy_streams is False or a not in target.remux_a:
            return ConvertPlan("transcode", "", target.acodec, target.container)
        return ConvertPlan("remux", "", "copy", target.container)

    v_ok = v in target.remux_v
    a_ok = a in target.remux_a
    if copy_streams is None and v_ok and a_ok and target.remux_v:
        return ConvertPlan("remux", "copy", "copy", target.container)
    return ConvertPlan("transcode", target.vcodec, target.acodec, target.container)


def _extension(path: str) -> str:
    return os.path.splitext(path)[1].lstrip(".")


def _scale_filter(fmt, src_info, target_resolution):
    if fmt.kind != "video" or not target_resolution:
        return None
    src_height = (src_info or {}).get("height", 0) or 0
    if src_height and target_resolution < src_height:
        return f"scale=-2:{int(target_resolution)}"
    return None


def _convert_to_format(input_path, fmt, copy_streams, target_resolution=None,
                       runner=None):
    src_info = probe_media(input_path)
    plan = plan_conversion(src_info, fmt, copy_streams)
    out_path = os.path.splitext(input_path)[0] + "." + fmt.extension

    if fmt.key == "gif":
        # GIF carries no audio: `-an` drops the audio stream. The palette filter
        # is the whole video recipe; no `-c:v`/`-c:a` flags are emitted here.
        vf = (
            "fps=15,scale=320:-1:flags=lanczos,split[a][b];"
            "[a]palettegen[p];[b][p]paletteuse"
        )
        cmd = [ffmpeg_path(), "-i", input_path, "-vf", vf, "-an", "-y", out_path]
    else:
        vf = _scale_filter(fmt, src_info, target_resolution)
        cmd = [ffmpeg_path(), "-i", input_path]
        vcodec = plan.vcodec
        if vcodec == "":
            cmd.append("-vn")
        else:
            if vf and vcodec == "copy":
                # Scaling needs a re-encode; a stream copy + filter is invalid.
                vcodec = fmt.vcodec
            cmd += ["-c:v", vcodec]
        if vf:
            cmd += ["-vf", vf]
        if plan.acodec:
            cmd += ["-c:a", plan.acodec]
        cmd += ["-f", plan.container, "-y", out_path]

    run = subprocess.run if runner is None else runner
    result = run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        # ffmpeg may have written a partial output before failing; never leave
        # a corrupt file behind under the target extension.
        try:
            if os.path.isfile(out_path):
                os.remove(out_path)
        except OSError:
            pass
        return error_result("ffmpeg", result.stderr.decode(errors="ignore"), "")

    if plan.mode == "transcode" and copy_streams is True:
        # The caller asked to copy streams, but the source codec is editor
        # hostile, so plan_conversion upgraded it to a transcode. Say so.
        message = f"Re-encoded for editor compatibility: {out_path}"
    elif plan.mode == "remux" and not vf:
        message = f"Remuxed to {out_path}"
    else:
        message = f"Converted to {out_path}"
    return DownloadResult(
        status="ok",
        path=out_path,
        extension=fmt.extension,
        message=message,
    )


def convert_file(input_path: str, output_type: str = None,
                 target_resolution: int = None, target_format: str = None,
                 copy_streams: bool = None) -> DownloadResult:
    try:
        if not os.path.exists(input_path):
            return error_result("not_found", "Input file does not exist.", "")

        if target_format is not None:
            fmt = get(target_format)
            if fmt is None:
                return error_result(
                    "format", f"Unknown target format: {target_format}", ""
                )
            return _convert_to_format(
                input_path, fmt, copy_streams, target_resolution=target_resolution
            )

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
