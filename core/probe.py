import json
import subprocess

from utils.ffmpeg import ffprobe_path

_EMPTY = {"vcodec": "", "acodec": "", "height": 0, "container": ""}


def _default_runner(cmd):
    return subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
    )


def probe_media(path, runner=None):
    probe = _default_runner if runner is None else runner
    try:
        cmd = [
            ffprobe_path(), "-v", "error",
            "-show_streams", "-show_format", "-of", "json", path,
        ]
        proc = probe(cmd)
        if proc.returncode != 0:
            return dict(_EMPTY)

        data = json.loads(proc.stdout)
        info = dict(_EMPTY)
        seen_video = seen_audio = False
        for stream in data.get("streams", []):
            kind = stream.get("codec_type")
            if kind == "video" and not seen_video:
                info["vcodec"] = stream.get("codec_name") or ""
                info["height"] = int(stream.get("height") or 0)
                seen_video = True
            elif kind == "audio" and not seen_audio:
                info["acodec"] = stream.get("codec_name") or ""
                seen_audio = True
        info["container"] = (data.get("format") or {}).get("format_name") or ""
        return info
    except Exception:
        return dict(_EMPTY)
