"""Expand a collection URL (playlist, channel, profile) into video entries.

Qt-free. The pure helpers (entries_from_info, new_entries) carry the tests;
expand_collection does the network work through yt-dlp.
"""

from dataclasses import dataclass, field
from typing import List, Optional

DEFAULT_LIMIT = 200


@dataclass
class CollectionEntry:
    url: str
    title: str = ""
    id: str = ""


@dataclass
class ExpandResult:
    platform: str = ""
    entries: List[CollectionEntry] = field(default_factory=list)
    total: Optional[int] = None
    truncated: bool = False
    error: Optional[str] = None
    category: Optional[str] = None


def _entry_url(entry: dict, platform: str) -> str:
    url = entry.get("webpage_url") or entry.get("url") or ""
    if url and "://" in url:
        return url
    # A bare id (some extractors put the id in `url`).
    ident = entry.get("id") or url
    if ident and platform == "youtube":
        return "https://www.youtube.com/watch?v=%s" % ident
    return url


def entries_from_info(info, limit: int = DEFAULT_LIMIT, platform: str = ""):
    """(entries, total, truncated) from a yt-dlp flat-extraction info dict."""
    info = info or {}
    entries: List[CollectionEntry] = []
    for item in info.get("entries") or []:
        if not item:
            continue
        url = _entry_url(item, platform)
        if not url:
            continue
        entries.append(CollectionEntry(
            url=url,
            title=item.get("title") or item.get("id") or url,
            id=str(item.get("id") or ""),
        ))
        if len(entries) >= limit:
            break
    total = info.get("playlist_count") or info.get("n_entries")
    if total is not None:
        try:
            total = int(total)
        except (TypeError, ValueError):
            total = None
    truncated = total is not None and total > len(entries)
    return entries, total, truncated


def new_entries(entries, existing_urls):
    """(kept, skipped): drop URLs already present, preserving order."""
    existing = set(existing_urls or [])
    kept: List[CollectionEntry] = []
    skipped = 0
    for entry in entries:
        if entry.url in existing:
            skipped += 1
            continue
        kept.append(entry)
        existing.add(entry.url)
    return kept, skipped
