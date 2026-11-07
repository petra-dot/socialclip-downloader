"""The browser extension this app ships and the folder it lives in.

The manifest carries a fixed key so Chrome derives the same extension id
everywhere, which is what lets the native host be registered without asking
the user to copy anything. The id below must match that key; a test pins it.
"""

import base64
import filecmp
import hashlib
import os
import shutil
import sys

CHROMIUM_EXTENSION_ID = "boopfllemcgelnnbhbaekongecmdfjnf"

MANIFESTS = ("manifest.chromium.json", "manifest.firefox.json")


def chrome_id_from_key(key_b64: str) -> str:
    """Chrome's id: the first 16 bytes of sha256(key), each nibble as a-p."""
    digest = hashlib.sha256(base64.b64decode(key_b64)).hexdigest()[:32]
    return "".join(chr(ord("a") + int(char, 16)) for char in digest)


def source_dir() -> str:
    """Where the extension files are: the bundle, else the repo folder."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        candidate = os.path.join(bundled, "extension")
        if os.path.isdir(candidate):
            return candidate
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "extension")


def installed_dir() -> str:
    """A stable path: the unpacked extension must outlive every launch."""
    from core.paths import data_dir

    return os.path.join(data_dir(), "extension")


def copy_tree(source: str, dest: str) -> str:
    """Copy files that are missing or changed; leave identical ones alone."""
    os.makedirs(dest, exist_ok=True)
    for name in os.listdir(source):
        src = os.path.join(source, name)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(dest, name)
        if os.path.isfile(dst) and filecmp.cmp(src, dst, shallow=False):
            continue
        shutil.copy2(src, dst)
    return dest


def ensure_installed() -> str:
    """Put the shipped extension in the data folder and return that path."""
    return copy_tree(source_dir(), installed_dir())
