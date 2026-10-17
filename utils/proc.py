"""Spawn a console child without flashing a console window on Windows.

A frozen ``--windowed`` build has no console of its own, so Windows allocates a
fresh one for every console child (ffmpeg, ffprobe, ``cmd.exe``) and it pops up
over the app. Two things stop that: ``CREATE_NO_WINDOW`` suppresses the console
allocation, and a ``STARTUPINFO`` with ``STARTF_USESHOWWINDOW`` hides a console
that is created anyway. The second is the mechanism yt-dlp uses for its own
ffmpeg children; both together cover every child. Off Windows this is a no-op.
"""

import subprocess
import sys

# Windows-only attributes; the literals are the documented values so this
# module still imports where subprocess does not define them.
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
_STARTF_USESHOWWINDOW = getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
_STARTUPINFO = getattr(subprocess, "STARTUPINFO", None)


def _hidden_startupinfo():
    if _STARTUPINFO is None:
        return None
    info = _STARTUPINFO()
    info.dwFlags |= _STARTF_USESHOWWINDOW
    return info


def no_window_kwargs(platform: str = None) -> dict:
    """Subprocess kwargs that keep a console child from showing a window.

    `platform` is injectable so both branches stay testable off Windows.
    """
    platform = sys.platform if platform is None else platform
    if not platform.startswith("win"):
        return {}
    kwargs = {"creationflags": _CREATE_NO_WINDOW}
    info = _hidden_startupinfo()
    if info is not None:
        kwargs["startupinfo"] = info
    return kwargs
