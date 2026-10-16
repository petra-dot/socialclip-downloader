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
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import List, Optional

from core.doctor import ffmpeg_version
from core.paths import data_dir, managed_dir
from core.version import __version__
from utils.ffmpeg import find_ffmpeg, reset_cache
from utils.ytdlp import find_js_runtime, is_stale, version_age_days

STATES = ("ok", "missing", "stale", "broken", "unknown")

# Repaired from a download. "app" self-updates through core/updater.py and
# "data-dir" is not a download at all.
REPAIRABLE = ("yt-dlp", "ffmpeg", "js-runtime")

ALLOWED_HOSTS = ("github.com", "api.github.com",
                 "objects.githubusercontent.com",
                 "release-assets.githubusercontent.com")

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
    """(version, sdist_url, sums_url) for the newest yt-dlp release.

    The release publishes no wheel - wheels live on PyPI - so the managed copy
    comes from the source tarball, which carries the same ``yt_dlp`` package.
    """
    data = _get_json(YTDLP_LATEST, opener=opener)
    tag = data.get("tag_name") or ""
    version = tag[1:] if tag.startswith("v") else tag
    sdist = sums = ""
    for asset in data.get("assets", []):
        name = asset.get("name") or ""
        url = asset.get("browser_download_url") or ""
        if name == "SHA2-256SUMS":
            sums = url
        elif name == "yt-dlp.tar.gz":
            sdist = url
    if not (version and sdist and sums):
        raise ValueError(
            "the yt-dlp release is missing its source tarball or checksums"
        )
    return version, sdist, sums


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


def _unpack_sdist(data: bytes, target: str) -> None:
    """Extract the ``yt_dlp`` package from the source tarball into `target`.

    The release tarball nests the package under a top-level ``yt-dlp/``
    directory (``yt-dlp/yt_dlp/...``); a tarball with the package at its root
    (``yt_dlp/...``) is accepted too. Either way the package lands at
    ``target/yt_dlp/``.
    """
    os.makedirs(target, exist_ok=True)
    written = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            parts = member.name.split("/")
            if "yt_dlp" not in parts:
                continue
            relative = parts[parts.index("yt_dlp"):]
            if os.path.isabs(member.name) or ".." in relative:
                raise ValueError(
                    "unsafe path in the source tarball: %s" % member.name
                )
            out = os.path.join(target, *relative)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with tf.extractfile(member) as src, open(out, "wb") as fh:
                shutil.copyfileobj(src, fh)
            written += 1
    if not written:
        raise ValueError(
            "the source tarball does not contain a yt_dlp package"
        )


def _swap(new_dir: str, dest: str) -> None:
    """Replace `dest` with `new_dir`, keeping the old copy as `dest + ".prev"`."""
    previous = dest + ".prev"
    if os.path.isdir(dest):
        if os.path.isdir(previous):
            shutil.rmtree(previous, ignore_errors=True)
        os.replace(dest, previous)
    os.replace(new_dir, dest)


def install_ytdlp(dest=None, opener=None) -> str:
    """Download, verify, and install the newest yt-dlp. Returns its version.

    The source tarball is unpacked into a temporary directory and only swapped
    in after its SHA-256 matches the release's checksum file, so a bad download
    never replaces a working copy. A copy that fails to import is rolled back.
    """
    dest = dest or managed_dir("yt-dlp")
    version, sdist_url, sums_url = latest_ytdlp(opener=opener)

    sums = _parse_sums(_get(sums_url, opener=opener).decode("utf-8"))
    name = sdist_url.rsplit("/", 1)[-1]
    expected = sums.get(name)
    if not expected:
        raise ValueError("no checksum published for %s" % name)

    data = _get(sdist_url, opener=opener)
    if not _verify_bytes(data, expected):
        raise ValueError("checksum mismatch for %s" % name)

    parent = os.path.dirname(dest) or "."
    os.makedirs(parent, exist_ok=True)
    temp = tempfile.mkdtemp(prefix="ytdlp-", dir=parent)
    try:
        _unpack_sdist(data, temp)
        _swap(temp, dest)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise

    # Make the freshly installed copy visible to this process: drop the cached
    # package and re-insert the managed directory, so a re-check (and any later
    # import) sees the new version instead of the one imported at startup.
    import importlib
    for name in [m for m in list(sys.modules)
                 if m == "yt_dlp" or m.startswith("yt_dlp.")]:
        del sys.modules[name]
    from utils.ytdlp import load
    load()
    importlib.invalidate_caches()

    try:
        import yt_dlp  # noqa: F401 - prove the new copy imports
        from yt_dlp.version import __version__ as installed
    except Exception as exc:
        previous = dest + ".prev"
        if os.path.isdir(previous):
            shutil.rmtree(dest, ignore_errors=True)
            os.replace(previous, dest)
            for name in [m for m in list(sys.modules)
                         if m == "yt_dlp" or m.startswith("yt_dlp.")]:
                del sys.modules[name]
        raise ValueError(
            "the installed yt-dlp failed to import (%s); rolled back" % exc
        )
    return installed


FFMPEG_BUILDS = "https://github.com/BtbN/FFmpeg-Builds/releases/latest"
DENO_RELEASE = "https://github.com/denoland/deno/releases/latest/download"

# A 64-character hex digest, anywhere in a checksum file.
_HEX64 = re.compile(r"[0-9a-fA-F]{64}")

# The names ffmpeg and ffprobe ship under, on either platform.
_FFMPEG_BINARIES = ("ffmpeg", "ffmpeg.exe", "ffprobe", "ffprobe.exe")


def _platform_tag() -> str:
    """BtbN's build tag for this platform."""
    if sys.platform == "win32":
        return "win64"
    if sys.platform == "darwin":
        return "macos64"
    return "linux64"


def _ffmpeg_asset() -> str:
    """BtbN's release asset for this platform, or "" when there is none.

    BtbN ships Windows as a .zip and Linux as a .tar.xz; it publishes no macOS
    build at all, so macOS has no verified source and the installer refuses.
    """
    tag = _platform_tag()
    if tag == "win64":
        return "ffmpeg-master-latest-win64-gpl.zip"
    if tag == "linux64":
        return "ffmpeg-master-latest-linux64-gpl.tar.xz"
    return ""


def _deno_asset() -> str:
    if sys.platform == "win32":
        return "deno-x86_64-pc-windows-msvc.zip"
    if sys.platform == "darwin":
        return "deno-x86_64-apple-darwin.zip"
    return "deno-x86_64-unknown-linux-gnu.zip"


def _digest_for(text: str, name: str) -> str:
    """The SHA-256 for `name` from a checksum file. Pure.

    Handles the sha256sum layout ("<hex>  <name>") and Windows certutil output
    ("Hash      : <HEX>"), which is what deno publishes for its Windows zip.
    Falls back to the first 64-hex token; "" when the file holds no digest.
    """
    found = _parse_sums(text).get(name)
    if found:
        return found
    match = _HEX64.search(text or "")
    return match.group(0).lower() if match else ""


def _make_executable(path: str) -> None:
    try:
        mode = os.stat(path).st_mode
        os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass


def _extract_ffmpeg(data: bytes, asset: str, temp: str) -> None:
    """Write ffmpeg and ffprobe from `data` (a zip or tar.xz) into `temp`."""
    written = []
    if asset.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if os.path.basename(name) not in _FFMPEG_BINARIES:
                    continue
                out = os.path.join(temp, os.path.basename(name))
                with zf.open(name) as src, open(out, "wb") as fh:
                    shutil.copyfileobj(src, fh)
                written.append(out)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                if os.path.basename(member.name) not in _FFMPEG_BINARIES:
                    continue
                out = os.path.join(temp, os.path.basename(member.name))
                src = tf.extractfile(member)
                with open(out, "wb") as fh:
                    shutil.copyfileobj(src, fh)
                written.append(out)
    if not written:
        raise ValueError("the ffmpeg build has no ffmpeg binary")
    for path in written:
        _make_executable(path)


def install_ffmpeg(dest=None, opener=None) -> str:
    """Download a static ffmpeg build, verify it, and install ffmpeg/ffprobe.

    Returns "installed". The archive is unpacked into a temporary directory and
    only swapped in after its SHA-256 matches BtbN's checksum file, so a bad
    download never replaces a working copy.
    """
    dest = dest or managed_dir("bin")
    asset = _ffmpeg_asset()
    if not asset:
        raise ValueError(
            "no verified ffmpeg build is available for macOS. Install ffmpeg "
            "with 'brew install ffmpeg', or point SOCIALCLIP_FFMPEG at one."
        )
    url = "%s/download/%s" % (FFMPEG_BUILDS, asset)
    sums_url = "%s/download/checksums.sha256" % FFMPEG_BUILDS

    expected = _parse_sums(_get(sums_url, opener=opener).decode("utf-8")).get(
        asset
    )
    if not expected:
        raise ValueError("no checksum published for %s" % asset)
    data = _get(url, opener=opener)
    if not _verify_bytes(data, expected):
        raise ValueError("checksum mismatch for %s" % asset)

    parent = os.path.dirname(dest) or "."
    os.makedirs(parent, exist_ok=True)
    temp = tempfile.mkdtemp(prefix="ffmpeg-", dir=parent)
    try:
        _extract_ffmpeg(data, asset, temp)
        os.makedirs(dest, exist_ok=True)
        for name in os.listdir(temp):
            os.replace(os.path.join(temp, name), os.path.join(dest, name))
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    reset_cache()
    return "installed"


def install_deno(dest=None, opener=None) -> str:
    """Download deno, verify it, and install it as the JS runtime."""
    dest = dest or managed_dir("bin")
    asset = _deno_asset()
    url = "%s/%s" % (DENO_RELEASE, asset)
    sums = _get(url + ".sha256sum", opener=opener).decode("utf-8")
    expected = _digest_for(sums, asset)
    if not expected:
        raise ValueError("no checksum published for %s" % asset)

    data = _get(url, opener=opener)
    if not _verify_bytes(data, expected):
        raise ValueError("checksum mismatch for %s" % asset)

    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        name = next(
            (n for n in zf.namelist() if os.path.basename(n).startswith("deno")),
            "",
        )
        if not name:
            raise ValueError("the deno archive has no binary")
        out = os.path.join(dest, os.path.basename(name))
        temp = out + ".tmp"
        try:
            with zf.open(name) as src, open(temp, "wb") as fh:
                shutil.copyfileobj(src, fh)
            _make_executable(temp)
            os.replace(temp, out)
        except Exception:
            if os.path.exists(temp):
                os.remove(temp)
            raise
    return "installed"
