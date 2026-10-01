import glob
import os
import shutil
import sys

_CACHE = {}


def _candidate_dirs():
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        dirs = []
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            pattern = os.path.join(
                local, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "**", "bin"
            )
            dirs.extend(glob.glob(pattern, recursive=True))
        program_data = os.environ.get("ProgramData", r"C:\ProgramData")
        dirs.extend(
            [
                os.path.join(program_data, "chocolatey", "bin"),
                os.path.join(home, "scoop", "shims"),
                r"C:\Program Files\ffmpeg\bin",
            ]
        )
        return dirs
    return ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/snap/bin"]


def _bundle_dir():
    """Directory of PyInstaller-bundled binaries, or the app dir when frozen.

    Empty string when not frozen and nothing is bundled in this checkout.
    """
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        return meipass
    here = os.path.dirname(os.path.abspath(__file__))
    if glob.glob(os.path.join(here, "ffmpeg*")):
        return here
    return ""


def find_ffmpeg(env=None, which=None, exists=None, candidate_dirs=None, bundle_dir=None):
    """Locate ffmpeg: bundled copy first, then env override, PATH, install dirs."""
    env = os.environ if env is None else env
    which = shutil.which if which is None else which
    exists = os.path.isfile if exists is None else exists

    if bundle_dir is None:
        bundle_dir = _bundle_dir()
    if bundle_dir:
        for name in ("ffmpeg", "ffmpeg.exe"):
            candidate = os.path.join(bundle_dir, name)
            if exists(candidate):
                return candidate

    override = env.get("SOCIALCLIP_FFMPEG") or env.get("FFMPEG_LOCATION")
    if override and exists(override):
        return override

    found = which("ffmpeg")
    if found:
        return found

    dirs = _candidate_dirs() if candidate_dirs is None else candidate_dirs
    for directory in dirs:
        for name in ("ffmpeg", "ffmpeg.exe"):
            candidate = os.path.join(directory, name)
            if exists(candidate):
                return candidate
    return ""


def ffmpeg_path():
    if "ffmpeg" not in _CACHE:
        _CACHE["ffmpeg"] = find_ffmpeg() or "ffmpeg"
    return _CACHE["ffmpeg"]


def ffprobe_path():
    directory = os.path.dirname(ffmpeg_path())
    if directory:
        for name in ("ffprobe", "ffprobe.exe"):
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate):
                return candidate
    return "ffprobe"


def reset_cache():
    _CACHE.clear()
