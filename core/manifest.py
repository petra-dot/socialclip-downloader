from dataclasses import asdict, dataclass
from typing import Optional

from sites.cookies import detect_platform

SCHEMA_VERSION = "1.0"


@dataclass
class DownloadResult:
    status: str = "ok"
    url: str = ""
    platform: str = ""
    title: str = ""
    path: Optional[str] = None
    extension: str = ""
    height: int = 0
    bytes: int = 0
    duration_seconds: int = 0
    error_category: Optional[str] = None
    message: Optional[str] = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["schema_version"] = SCHEMA_VERSION
        # schema_version first for stable, readable stdout
        return {"schema_version": data.pop("schema_version"), **data}


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def result_from_info(info: dict, path: str, url: str) -> DownloadResult:
    info = info or {}
    return DownloadResult(
        status="ok",
        url=url,
        platform=detect_platform(url) if url else "",
        title=info.get("title") or info.get("id") or "",
        path=path or "",
        extension=(info.get("ext") or "").lstrip("."),
        height=_as_int(info.get("height")),
        bytes=_as_int(info.get("filesize") or info.get("filesize_approx")),
        duration_seconds=_as_int(info.get("duration")),
        error_category=None,
        message=None,
    )


def error_result(category: str, message: str, url: str) -> DownloadResult:
    return DownloadResult(
        status="error",
        url=url,
        platform=detect_platform(url) if url else "",
        path=None,
        error_category=category,
        message=message,
    )
