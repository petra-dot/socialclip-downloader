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
        return ["explorer", "/select," + path.replace("/", "\\")]
    if platform == "darwin":
        return ["open", "-R", path]
    return ["xdg-open", os.path.dirname(path)]


def reveal_in_folder(path: str) -> None:
    try:
        subprocess.run(reveal_command(path), check=False)
    except Exception:
        pass
