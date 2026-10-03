import os
import re
import subprocess
import sys

_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_HOSTISH = re.compile(r"^[\w-]+(\.[\w-]+)+(/\S*)?$")


def looks_like_url(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    if _SCHEME.match(text):
        return True
    return bool(_HOSTISH.match(text))


def reveal_command(path: str, platform: str = None) -> list:
    platform = platform or sys.platform
    if platform.startswith("win"):
        # explorer.exe parses its OWN argument line, not argv, so an unquoted
        # path with spaces (or a path it dislikes) makes it silently open the
        # default folder (Documents) instead of selecting the file. Quote it.
        native = path.replace("/", "\\")
        return ["explorer", '/select,"{}"'.format(native)]
    if platform == "darwin":
        return ["open", "-R", path]
    return ["xdg-open", os.path.dirname(path)]


def reveal_in_folder(path: str) -> None:
    """Reveal `path` in the file manager.

    If the file no longer exists, open its containing folder instead, so the
    user never lands in an unrelated default directory.
    """
    if path and not os.path.exists(path):
        parent = os.path.dirname(path)
        if parent and os.path.isdir(parent):
            path = parent
    try:
        cmd = reveal_command(path)
        if sys.platform.startswith("win") and not os.path.isfile(path):
            # Fall back to opening the directory when we cannot select a file.
            cmd = ["explorer", path.replace("/", "\\")]
        subprocess.run(cmd, check=False)
    except Exception:
        pass
