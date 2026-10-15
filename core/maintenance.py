"""Check the app's components and repair the ones that rot.

yt-dlp's extractors break in weeks, and YouTube needs a JavaScript runtime that
is not bundled. This module reports each component's state and installs a
verified replacement into the per-user data directory.

Qt-free. Network access is injectable so the checks and installers are testable.
"""

import hashlib
import io
import json
import os
import shutil
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import List, Optional

from core.doctor import ffmpeg_version
from core.paths import data_dir, managed_dir
from core.version import __version__
from utils.ffmpeg import find_ffmpeg
from utils.ytdlp import find_js_runtime, is_stale, version_age_days

STATES = ("ok", "missing", "stale", "broken", "unknown")

# Repaired from a download. "app" self-updates through core/updater.py and
# "data-dir" is not a download at all.
REPAIRABLE = ("yt-dlp", "ffmpeg", "js-runtime")

ALLOWED_HOSTS = ("github.com", "api.github.com",
                 "objects.githubusercontent.com")

YTDLP_LATEST = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"

USER_AGENT = "SocialClip-Downloader"


@dataclass
class Component:
    key: str
    label: str
    state: str
    version: str = ""
    detail: str = ""
    action: str = "none"


def _ytdlp_version() -> str:
    from utils.ytdlp import ytdlp_version
    return ytdlp_version()


def _require_allowed(url: str) -> None:
    """Raise unless `url` is HTTPS on an allow-listed host."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "") not in ALLOWED_HOSTS:
        raise ValueError("refusing to fetch %s" % (url or "an unknown URL"))


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse a redirect to a host or scheme the allow-list does not cover.

    urllib follows 3xx transparently, so without this the initial-URL check
    would be the only one, and a redirect could hand us an arbitrary host.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _require_allowed(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_ValidatingRedirectHandler)


def _get(url: str, opener=None, timeout: int = 30) -> bytes:
    """Fetch a URL. HTTPS and an allow-listed host are required, on every hop."""
    _require_allowed(url)
    open_url = opener or _OPENER.open
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with open_url(request, timeout=timeout) as response:
        _require_allowed(response.geturl())
        return response.read()


def _get_json(url: str, opener=None) -> dict:
    return json.loads(_get(url, opener=opener).decode("utf-8"))


def check_all(which=None, exists=None, runner=None) -> List[Component]:
    """Every component's state from local information only. Never raises."""
    components = []

    components.append(
        Component("app", "App", "ok", version=__version__)
    )

    version = ""
    try:
        version = _ytdlp_version()
        stale = is_stale(version)
        age = version_age_days(version)
    except Exception:
        version = ""
        stale = False
        age = None
    if not version:
        ytdlp = Component(
            "yt-dlp", "yt-dlp", "missing", detail="not installed",
            action="install",
        )
    elif stale:
        ytdlp = Component(
            "yt-dlp", "yt-dlp", "stale", version=version,
            detail="%s days old" % age, action="update",
        )
    else:
        ytdlp = Component("yt-dlp", "yt-dlp", "ok", version=version)
    components.append(ytdlp)

    try:
        path = find_ffmpeg(which=which, exists=exists) or ""
    except Exception:
        path = ""
    if path:
        text = ""
        try:
            text = ffmpeg_version(path, runner=runner) or ""
        except Exception:
            text = ""
        components.append(
            Component("ffmpeg", "ffmpeg", "ok", version=text or "present")
        )
    else:
        components.append(
            Component("ffmpeg", "ffmpeg", "missing", detail="not found",
                      action="install")
        )

    try:
        name, runtime_path = find_js_runtime(which=which)
    except Exception:
        name, runtime_path = "", ""
    if name:
        components.append(
            Component("js-runtime", "JavaScript runtime", "ok",
                      version="%s (%s)" % (name, runtime_path))
        )
    else:
        components.append(
            Component("js-runtime", "JavaScript runtime", "missing",
                      detail="YouTube needs deno or node", action="install")
        )

    try:
        from core.paths import data_dir_writable
        writable = data_dir_writable()
    except Exception:
        writable = False
    components.append(
        Component(
            "data-dir", "Data directory",
            "ok" if writable else "broken",
            version=data_dir(),
            detail="" if writable else "not writable",
        )
    )
    return components


def plan_repairs(components) -> List[str]:
    """Component keys that should be repaired now. Pure.

    Only missing, stale, and broken components are repaired, and only the
    repairable ones. Unknown stays unknown: better to say nothing than to
    reinstall over a working copy.
    """
    keys = []
    for component in components:
        if component.key not in REPAIRABLE:
            continue
        if component.state in ("missing", "stale", "broken"):
            keys.append(component.key)
    return keys


def latest_ytdlp(opener=None):
    """(version, wheel_url, sums_url) for the newest yt-dlp release."""
    data = _get_json(YTDLP_LATEST, opener=opener)
    tag = data.get("tag_name") or ""
    version = tag[1:] if tag.startswith("v") else tag
    wheel = sums = ""
    for asset in data.get("assets", []):
        name = asset.get("name") or ""
        url = asset.get("browser_download_url") or ""
        if name == "SHA2-256SUMS":
            sums = url
        elif name.endswith(".whl"):
            wheel = url
    if not (version and wheel and sums):
        raise ValueError("the yt-dlp release is missing a wheel or its checksums")
    return version, wheel, sums


def _parse_sums(text: str) -> dict:
    """name -> hex digest, from a sha256sums-style file. Pure."""
    sums = {}
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            sums[parts[-1].lstrip("*")] = parts[0].lower()
    return sums


def _verify_bytes(data: bytes, expected_hex: str) -> bool:
    return hashlib.sha256(data).hexdigest().lower() == (expected_hex or "").lower()


def _unpack_wheel(data: bytes, target: str) -> None:
    """Extract a wheel's ``yt_dlp`` package into `target`."""
    os.makedirs(target, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = [n for n in zf.namelist() if n.startswith("yt_dlp/")]
        if not names:
            raise ValueError("the wheel does not contain a yt_dlp package")
        zf.extractall(target, members=names)


def _swap(new_dir: str, dest: str, keep_previous: bool) -> None:
    """Replace `dest` with `new_dir`, keeping the old copy when asked."""
    previous = dest + ".prev"
    if keep_previous and os.path.isdir(dest):
        if os.path.isdir(previous):
            shutil.rmtree(previous, ignore_errors=True)
        os.replace(dest, previous)
    elif os.path.isdir(dest):
        shutil.rmtree(dest, ignore_errors=True)
    os.replace(new_dir, dest)


def install_ytdlp(dest=None, opener=None) -> str:
    """Download, verify, and install the newest yt-dlp. Returns its version.

    The wheel is unpacked into a temporary directory and only swapped in after
    its SHA-256 matches the release's checksum file, so a bad download never
    replaces a working copy.
    """
    dest = dest or managed_dir("yt-dlp")
    version, wheel_url, sums_url = latest_ytdlp(opener=opener)

    sums = _parse_sums(_get(sums_url, opener=opener).decode("utf-8"))
    name = wheel_url.rsplit("/", 1)[-1]
    expected = sums.get(name)
    if not expected:
        raise ValueError("no checksum published for %s" % name)

    data = _get(wheel_url, opener=opener)
    if not _verify_bytes(data, expected):
        raise ValueError("checksum mismatch for %s" % name)

    parent = os.path.dirname(dest) or "."
    os.makedirs(parent, exist_ok=True)
    temp = tempfile.mkdtemp(prefix="ytdlp-", dir=parent)
    try:
        _unpack_wheel(data, temp)
        _swap(temp, dest, keep_previous=True)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return version
