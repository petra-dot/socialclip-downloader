"""Check GitHub for a newer release, download and verify the asset, and apply
it on Windows. Qt-free, standard library only."""

import hashlib
import os
import re
import sys
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


def verify_digest(path, expected_hex) -> bool:
    if not expected_hex:
        return False
    sha = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            sha.update(chunk)
    if sha.hexdigest().lower() == expected_hex.lower():
        return True
    try:
        os.remove(path)
    except OSError:
        pass
    return False
