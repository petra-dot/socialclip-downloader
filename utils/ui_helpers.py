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
    """Build the command that reveals `path` in the OS file manager.

    `path` may be a file (select it) or a directory (open it).
    """
    platform = platform or sys.platform
    is_dir = os.path.isdir(path)
    if platform.startswith("win"):
        native = path.replace("/", "\\")
        if is_dir:
            return ["explorer", '"{}"'.format(native)]
        # explorer.exe parses its OWN argument line, not argv, so an unquoted
        # /select,<path> (especially with spaces) silently opens the default
        # folder (Documents) instead of selecting the file. Quote it.
        return ["explorer", '/select,"{}"'.format(native)]
    if platform == "darwin":
        return ["open", "-R", path]
    # Linux: xdg-open opens a directory directly; for a file, open its parent.
    return ["xdg-open", path if is_dir else os.path.dirname(path)]


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
        subprocess.run(reveal_command(path), check=False)
    except Exception:
        pass
