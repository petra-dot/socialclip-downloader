"""Detect whether the OS prefers a dark or light interface.

Qt 5 has no portable API for this, so each platform is read directly. Never
raises: an unknown or unreadable answer is "light". Qt-free and injectable.
"""

import subprocess
import sys

from utils.proc import no_window_kwargs


def _default_runner(cmd: str) -> str:
    result = subprocess.run(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, **no_window_kwargs(),
    )
    return result.stdout or ""


def _windows_is_dark() -> str:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        try:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        finally:
            winreg.CloseKey(key)
        return "light" if int(value) else "dark"
    except Exception:
        return ""


def _windows_answer(run) -> str:
    if run is not _default_runner:
        # Tests inject a runner; treat its output like the registry value.
        raw = (run("AppsUseLightTheme") or "").strip()
        return "light" if raw == "1" else ("dark" if raw == "0" else "")
    return _windows_is_dark()


def detect(runner=None, platform=None) -> str:
    """'dark' or 'light' for the OS preference."""
    platform = sys.platform if platform is None else platform
    run = _default_runner if runner is None else runner
    try:
        if platform.startswith("win"):
            answer = _windows_answer(run)
        elif platform == "darwin":
            answer = "dark" if "dark" in run(
                "defaults read -g AppleInterfaceStyle").lower() else "light"
        elif platform.startswith("linux"):
            answer = "dark" if "dark" in run(
                "gsettings get org.gnome.desktop.interface color-scheme").lower() \
                else "light"
        else:
            answer = ""
    except Exception:
        answer = ""
    return answer if answer in ("dark", "light") else "light"
