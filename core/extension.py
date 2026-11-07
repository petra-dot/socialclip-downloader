"""The browser extension this app ships and the folder it lives in.

The manifest carries a fixed key so Chrome derives the same extension id
everywhere, which is what lets the native host be registered without asking
the user to copy anything. The id below must match that key; a test pins it.
"""

import base64
import filecmp
import hashlib
import json
import os
import shutil
import sys

CHROMIUM_EXTENSION_ID = "boopfllemcgelnnbhbaekongecmdfjnf"

MANIFESTS = ("manifest.json", "manifest.firefox.json")


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


def installed_dir(variant: str = "chromium") -> str:
    """A stable path: the unpacked extension must outlive every launch.

    Each browser gets its own folder, because both insist on a file named
    exactly ``manifest.json`` and the two manifests differ.
    """
    from core.paths import data_dir

    folder = "extension" if variant == "chromium" else "extension-firefox"
    return os.path.join(data_dir(), folder)


def copy_tree(source: str, dest: str, skip=()) -> str:
    """Copy files that are missing or changed; leave identical ones alone.

    A skipped name is also deleted from ``dest``: an older copy of the folder
    must not keep a manifest the browser would refuse to read.
    """
    os.makedirs(dest, exist_ok=True)
    for name in skip:
        stale = os.path.join(dest, name)
        if os.path.isfile(stale):
            os.remove(stale)
    for name in os.listdir(source):
        if name in skip:
            continue
        src = os.path.join(source, name)
        dst = os.path.join(dest, name)
        if os.path.isdir(src):
            copy_tree(src, dst, skip)
            continue
        if not os.path.isfile(src):
            continue
        if os.path.isfile(dst) and filecmp.cmp(src, dst, shallow=False):
            continue
        shutil.copy2(src, dst)
    return dest


def build_package(dest: str, variant: str = "chromium") -> str:
    """Write a loadable folder for one browser into an arbitrary path.

    The manifest carries the app version: AMO refuses a repeated add-on
    version, so every release must ship a new one.
    """
    from core.version import __version__

    source = source_dir()
    copy_tree(source, dest, skip=MANIFESTS)
    manifest = "manifest.json" if variant == "chromium" else "manifest.firefox.json"
    with open(os.path.join(source, manifest), "r", encoding="utf-8") as handle:
        data = json.load(handle)
    data["version"] = __version__
    with open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    return dest


def ensure_installed() -> dict:
    """Put a loadable copy of the extension in the data folder.

    Returns ``{"chromium": path, "firefox": path}``. Chrome, Edge and Brave
    load the first; Firefox loads the second.
    """
    return {
        "chromium": build_package(installed_dir("chromium"), "chromium"),
        "firefox": build_package(installed_dir("firefox"), "firefox"),
    }


FIREFOX_XPI_NAME = "socialclip-firefox.xpi"


def firefox_xpi_url(version: str) -> str:
    """The signed add-on attached to this version's GitHub release."""
    from core.updater import GITHUB_OWNER, REPO

    return "https://github.com/%s/%s/releases/download/v%s/%s" % (
        GITHUB_OWNER,
        REPO,
        version,
        FIREFOX_XPI_NAME,
    )


def fetch_firefox_xpi(version: str, dest_dir: str = None, opener=None) -> str:
    """Download the signed add-on. A signed XPI is a ZIP, so it must start PK."""
    import urllib.request

    target_dir = dest_dir or installed_dir("firefox")
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, FIREFOX_XPI_NAME)
    open_url = opener or (lambda url: urllib.request.urlopen(url, timeout=20))
    with open_url(firefox_xpi_url(version)) as response:
        data = response.read()
    if not data.startswith(b"PK"):
        raise ValueError("the release asset is not an add-on file")
    with open(path, "wb") as handle:
        handle.write(data)
    return path
