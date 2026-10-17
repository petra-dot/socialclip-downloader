"""A persistent log of completed downloads.

Qt-free: the GUI and the CLI both use it. Recording happens in
core.download.download_one, so every caller records without duplicating logic.
"""

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from core.paths import history_path

STORE_VERSION = 1

STATUS_OK = "ok"
STATUS_MISSING = "missing"
STATUS_DELETED = "deleted"


@dataclass
class HistoryEntry:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    title: str = ""
    url: str = ""
    platform: str = ""
    path: str = ""
    bytes: int = 0
    extension: str = ""
    height: int = 0
    duration_seconds: int = 0
    source: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    removed_at: str = ""


def entry_from_result(result, source: str = "") -> HistoryEntry:
    """Map a core.manifest.DownloadResult to a HistoryEntry.

    The result already carries the title, platform, path, extension, height,
    bytes, and duration, so nothing is re-derived here.
    """
    return HistoryEntry(
        title=(getattr(result, "title", "") or "").strip(),
        url=getattr(result, "url", "") or "",
        platform=getattr(result, "platform", "") or "",
        path=getattr(result, "path", "") or "",
        bytes=_as_int(getattr(result, "bytes", 0)),
        extension=(getattr(result, "extension", "") or "").lstrip("."),
        height=_as_int(getattr(result, "height", 0)),
        duration_seconds=_as_int(getattr(result, "duration_seconds", 0)),
        source=source,
    )


def status_of(entry, exists=None) -> str:
    """ok / missing / deleted. `exists` is injectable so this stays pure."""
    if entry.removed_at:
        return STATUS_DELETED
    check = exists if exists is not None else os.path.isfile
    return STATUS_OK if entry.path and check(entry.path) else STATUS_MISSING


def search(entries, text: str) -> List[HistoryEntry]:
    """Case-insensitive substring match over the title."""
    needle = (text or "").strip().lower()
    if not needle:
        return list(entries)
    return [e for e in entries if needle in (e.title or "").lower()]


def filter_entries(entries, platform: Optional[str] = None,
                   extension: Optional[str] = None) -> List[HistoryEntry]:
    out = list(entries)
    if platform:
        out = [e for e in out if e.platform == platform]
    if extension:
        want = extension.lower().lstrip(".")
        out = [e for e in out if (e.extension or "").lower().lstrip(".") == want]
    return out


_STATUS_RANK = {STATUS_OK: 0, STATUS_MISSING: 1, STATUS_DELETED: 2}

_SORT_KEYS = {
    "title": lambda e, s: (e.title or "").lower(),
    "platform": lambda e, s: (e.platform or "").lower(),
    "extension": lambda e, s: (e.extension or "").lower(),
    "bytes": lambda e, s: _as_int(e.bytes),
    "created_at": lambda e, s: e.created_at or "",
    # ok, then missing, then deleted: a meaningful order, not alphabetical.
    "status": lambda e, s: _STATUS_RANK.get((s or {}).get(e.id, ""), 3),
}


def sort_entries(entries, key: str, descending: bool = False,
                 statuses: Optional[dict] = None) -> List[HistoryEntry]:
    getter = _SORT_KEYS.get(key, _SORT_KEYS["created_at"])
    return sorted(entries, key=lambda e: getter(e, statuses), reverse=descending)


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coerce_entries(raw) -> List[HistoryEntry]:
    """Rebuild entries, dropping unknown keys but never the entry."""
    if not isinstance(raw, list):
        return []
    known = HistoryEntry.__dataclass_fields__
    out: List[HistoryEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        clean = {k: v for k, v in item.items() if k in known}
        try:
            entry = HistoryEntry(**clean)
        except (TypeError, ValueError):
            continue
        for name in ("bytes", "height", "duration_seconds"):
            setattr(entry, name, _as_int(getattr(entry, name)))
        out.append(entry)
    return out


class HistoryStore:
    """The history file. Atomic write, tolerant load, never drops an entry."""

    def __init__(self, path: Optional[str] = None):
        self.path = path if path is not None else history_path()
        self._entries: List[HistoryEntry] = []

    def load(self) -> None:
        self._entries = []
        if not self.path:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict) or data.get("version") != STORE_VERSION:
            return
        self._entries.extend(_coerce_entries(data.get("entries")))

    def save(self) -> None:
        if not self.path:
            return
        data = {"version": STORE_VERSION,
                "entries": [asdict(e) for e in self._entries]}
        tmp = f"{self.path}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, self.path)

    def add(self, entry: HistoryEntry) -> HistoryEntry:
        # Load first: each download creates its own store, and appending to an
        # empty one would save a single-entry file over the whole history.
        self.load()
        self._entries.append(entry)
        self.save()
        return entry

    def remove(self, entry_id: str) -> bool:
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.id != entry_id]
        if len(self._entries) == before:
            return False
        self.save()
        return True

    def mark_deleted(self, entry_id: str) -> bool:
        for entry in self._entries:
            if entry.id == entry_id:
                entry.removed_at = datetime.now(timezone.utc).isoformat()
                self.save()
                return True
        return False

    def entries(self) -> List[HistoryEntry]:
        return list(self._entries)


def record(store, result, source: str = "") -> Optional[HistoryEntry]:
    """Append a result to a store, swallowing any failure.

    Losing a history line must never lose a download, so this never raises.
    """
    if store is None:
        return None
    try:
        return store.add(entry_from_result(result, source))
    except Exception:
        return None
