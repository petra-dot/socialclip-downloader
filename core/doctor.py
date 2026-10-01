import socket
import subprocess

from sites.cookies import PLATFORM_NAMES, cookie_file_for, default_cookie_dir
from utils.ffmpeg import find_ffmpeg

DOCTOR_SCHEMA_VERSION = "1.1"


def _default_probe():
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=3).close()
        return True, "reachable"
    except OSError as exc:
        return False, str(exc) or "unreachable"


def ffmpeg_version(path, runner=None):
    """First line of `ffmpeg -version`, or "" when unavailable."""
    if not path:
        return ""
    run = runner
    if run is None:
        def run(cmd):
            return subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
    try:
        proc = run([path, "-version"])
        if getattr(proc, "returncode", 0) != 0:
            return ""
        out = getattr(proc, "stdout", "") or ""
        return out.strip().splitlines()[0] if out.strip() else ""
    except Exception:
        return ""


def run_checks(env=None, which=None, exists=None, probe=None, runner=None,
               candidate_dirs=None):
    """Never raises. Every check degrades to false/null with a detail string."""
    try:
        ffmpeg_path = find_ffmpeg(
            env=env, which=which, exists=exists, candidate_dirs=candidate_dirs
        )
    except Exception:
        ffmpeg_path = ""

    ffmpeg = {"found": bool(ffmpeg_path), "path": ffmpeg_path or None, "version": None}
    if ffmpeg_path:
        ffmpeg["version"] = ffmpeg_version(ffmpeg_path, runner=runner) or None

    try:
        cookie_dir = default_cookie_dir()
    except Exception:
        cookie_dir = None

    cookies = []
    for platform in PLATFORM_NAMES:
        try:
            path = cookie_file_for(platform, cookie_dir) if cookie_dir else ""
        except Exception:
            path = ""
        cookies.append(
            {"platform": platform, "found": bool(path), "path": path or None}
        )

    if probe is None:
        probe = _default_probe
    try:
        ok, detail = probe()
    except Exception as exc:
        ok, detail = None, str(exc)

    return {
        "schema_version": DOCTOR_SCHEMA_VERSION,
        "ffmpeg": ffmpeg,
        "cookies": cookies,
        "network": {"ok": ok, "detail": str(detail)},
    }
