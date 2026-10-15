"""Check GitHub for a newer release, download and verify the asset, and apply
it on Windows. Qt-free, standard library only."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

GITHUB_OWNER = "petra-dot"
REPO = "socialclip-downloader"
LATEST_API = "https://api.github.com/repos/%s/%s/releases/latest" % (GITHUB_OWNER, REPO)
RELEASE_PAGE = "https://github.com/%s/%s/releases/latest" % (GITHUB_OWNER, REPO)

ALLOWED_HOSTS = ("github.com", "objects.githubusercontent.com")

ASSET_BY_PLATFORM = {
    "win32": "socialclip-downloader-windows.exe",
    "darwin": "socialclip-downloader-macos",
    "linux": "socialclip-downloader-linux",
}


@dataclass
class AssetInfo:
    name: str
    download_url: str
    digest: Optional[str] = None


@dataclass
class ReleaseInfo:
    tag: str
    version: str
    page_url: str
    assets: List[AssetInfo] = field(default_factory=list)


def parse_version(text) -> tuple:
    """(0, 9, 2) from "v0.9.2"; trailing non-numeric parts are dropped."""
    if not text:
        return ()
    match = re.search(r"(\d+(?:\.\d+)*)", str(text))
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(latest, current) -> bool:
    a, b = parse_version(latest), parse_version(current)
    if not a or not b:
        return False
    return a > b


def release_from_json(data) -> ReleaseInfo:
    data = data or {}
    tag = data.get("tag_name") or ""
    assets: List[AssetInfo] = []
    for raw in data.get("assets") or []:
        name = raw.get("name") or ""
        url = raw.get("browser_download_url") or ""
        if not name or not url:
            continue
        digest = raw.get("digest") or ""
        hex_digest = digest.split(":", 1)[1] if digest.startswith("sha256:") else None
        assets.append(AssetInfo(name=name, download_url=url, digest=hex_digest))
    return ReleaseInfo(
        tag=tag,
        version=tag.lstrip("v"),
        page_url=data.get("html_url") or RELEASE_PAGE,
        assets=assets,
    )


def select_asset(assets, platform=None) -> Optional[AssetInfo]:
    wanted = ASSET_BY_PLATFORM.get(platform or sys.platform)
    if not wanted:
        return None
    for asset in assets:
        if asset.name == wanted:
            return asset
    return None


def _discard(path) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def verify_digest(path, expected_hex) -> bool:
    if not expected_hex:
        _discard(path)
        return False
    sha = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            sha.update(chunk)
    if sha.hexdigest().lower() == expected_hex.lower():
        return True
    _discard(path)
    return False


class DownloadCancelled(Exception):
    """Raised from the download loop when the caller requests cancellation."""


def fetch_latest_release(opener=None, timeout=10) -> ReleaseInfo:
    open_url = opener or urllib.request.urlopen
    request = urllib.request.Request(
        LATEST_API,
        headers={
            "User-Agent": "SocialClip-Downloader",
            "Accept": "application/vnd.github+json",
        },
    )
    with open_url(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return release_from_json(data)


def download_asset(asset, dest, progress=None, cancel=None, opener=None, timeout=30) -> str:
    open_url = opener or urllib.request.urlopen
    parsed = urllib.parse.urlparse(asset.download_url)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or host not in ALLOWED_HOSTS:
        raise ValueError(
            "refusing to download from %s"
            % (asset.download_url or "an unknown URL")
        )
    request = urllib.request.Request(
        asset.download_url, headers={"User-Agent": "SocialClip-Downloader"}
    )
    with open_url(request, timeout=timeout) as response, open(dest, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancel and cancel():
                raise DownloadCancelled()
            chunk = response.read(65536)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    return dest


@dataclass
class ApplyPlan:
    target: str
    source: str


def update_temp_path(version, temp_dir=None) -> str:
    temp_dir = temp_dir or tempfile.gettempdir()
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(version))
    return os.path.join(temp_dir, "socialclip-update-%s.exe" % safe)


def write_batch_fallback(plan, temp_dir=None) -> str:
    """Write a .bat that replaces target once it is unlocked, then relaunches."""
    temp_dir = temp_dir or tempfile.gettempdir()
    bat = os.path.join(temp_dir, "socialclip-apply-%d.bat" % os.getpid())
    script = (
        "@echo off\r\n"
        ":wait\r\n"
        'copy /y "%s" "%s" >nul 2>&1\r\n'
        "if errorlevel 1 (\r\n"
        "  timeout /t 1 /nobreak >nul\r\n"
        "  goto wait\r\n"
        ")\r\n"
        'start "" "%s"\r\n'
        'del "%%~f0"\r\n'
    ) % (plan.source, plan.target, plan.target)
    with open(bat, "w", encoding="ascii") as fh:
        fh.write(script)
    return bat


def _spawn_detached(cmd) -> None:
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) if os.name == "nt" else 0
    subprocess.Popen(cmd, creationflags=flags, close_fds=True)


def apply_update(target, timeout=30, sleep=time.sleep) -> int:
    """Run inside the newly downloaded exe: copy it over target, relaunch."""
    source = sys.executable
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            shutil.copy2(source, target)
            _spawn_detached([target])
            return 0
        except OSError:
            sleep(0.5)
    plan = ApplyPlan(target=target, source=source)
    _spawn_detached(["cmd", "/c", write_batch_fallback(plan)])
    return 0


def cleanup_update_temp(temp_dir=None, prefix="socialclip-update-") -> int:
    temp_dir = temp_dir or tempfile.gettempdir()
    removed = 0
    try:
        names = os.listdir(temp_dir)
    except OSError:
        return 0
    for name in names:
        if name.startswith(prefix) and name.endswith(".exe"):
            try:
                os.remove(os.path.join(temp_dir, name))
                removed += 1
            except OSError:
                pass
    return removed
