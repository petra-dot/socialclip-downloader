"""Every console child must be spawned without a console window.

A frozen ``--windowed`` build has no console of its own, so Windows allocates a
fresh one for every console child (ffmpeg, ffprobe, ``cmd.exe``) unless the
spawn suppresses it. That is the window that flashes after a download or a
conversion. yt-dlp already hides its own ffmpeg children via ``STARTUPINFO``;
the calls below are ours.
"""

import ast
import pathlib
import subprocess
import sys

from utils.proc import no_window_kwargs

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The updater relaunches the app with DETACHED_PROCESS, which already gives the
# child no console; CREATE_NO_WINDOW would fight that flag.
_ALLOWLIST = {"core/updater.py"}

_SPAWNERS = ("run", "Popen", "check_output", "call", "check_call")


def test_win32_suppresses_the_console_window():
    kwargs = no_window_kwargs("win32")
    assert kwargs["creationflags"] == 0x08000000
    if sys.platform == "win32":
        # A console that is created anyway must be hidden, not shown.
        assert kwargs["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW


def test_other_platforms_get_no_extra_flags():
    assert no_window_kwargs("linux") == {}
    assert no_window_kwargs("darwin") == {}


def _spawn_calls(tree):
    for node in ast.walk(tree):
        func = getattr(node, "func", None)
        if (isinstance(node, ast.Call) and isinstance(func, ast.Attribute)
                and func.attr in _SPAWNERS
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"):
            yield node


def _hides_the_window(call):
    for keyword in call.keywords:
        if keyword.arg is None and isinstance(keyword.value, ast.Call):
            func = keyword.value.func
            if isinstance(func, ast.Name) and func.id == "no_window_kwargs":
                return True
    return False


def test_every_console_child_is_spawned_without_a_window():
    offenders = []
    for directory in ("core", "utils"):
        for path in (ROOT / directory).glob("*.py"):
            relative = "%s/%s" % (directory, path.name)
            if relative in _ALLOWLIST:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for call in _spawn_calls(tree):
                if not _hides_the_window(call):
                    offenders.append("%s:%d" % (relative, call.lineno))
    assert not offenders, offenders
