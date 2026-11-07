"""Native-messaging protocol shared by the browser host and the app.

The transport is the browser's stdin/stdout framing: a 4-byte little-endian
length, then that many bytes of UTF-8 JSON. Everything here is pure so the
host, the GUI and the tests can share it without Qt.
"""

import json
import struct
from typing import List
from urllib.parse import parse_qsl, urlencode, urlsplit

from core.queue import Queue
from core.version import __version__
from sites.cookies import PLATFORM_NAMES, PLATFORM_PATTERNS
from utils.file_utils import RESOLUTIONS

HOST_NAME = "com.petra_dot.socialclip"
PROTOCOL_VERSION = 1
MAX_SCAN_LINKS = 200
OUTPUTS = ("MP4", "MP3")

# A job in one of these states is still work the user is waiting on.
ACTIVE_STATES = ("pending", "running", "paused")

# Query parameters that track where a link was clicked. Everything else in a
# query is treated as part of the link's identity, because YouTube's `v` and a
# playlist's `list` are what make two links different videos.
TRACKING_PARAMS = frozenset((
    "s", "stack_idx", "t", "si", "feature", "fbclid", "gclid", "igsh",
    "igshid", "ref", "ref_src", "ref_url", "share_id", "mibextid", "_rdr",
))
TRACKING_PREFIXES = ("utm_",)


class ProtocolError(Exception):
    """The byte stream is not a well-formed native message."""


def _read_exact(stream, count: int) -> bytes:
    chunks = []
    remaining = count
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise ProtocolError("short frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def encode_message(payload: dict) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    return struct.pack("<I", len(body)) + body


def read_message(stream) -> dict:
    (length,) = struct.unpack("<I", _read_exact(stream, 4))
    try:
        data = json.loads(_read_exact(stream, length).decode("utf-8"))
    except ValueError as exc:
        raise ProtocolError(str(exc))
    if not isinstance(data, dict):
        raise ProtocolError("message must be a JSON object")
    return data


def normalize_url(url: str) -> str:
    """A URL's identity for duplicate checks.

    Tracking parameters are dropped, but parameters that name the video
    (YouTube's ``v``, a playlist's ``list``) are what distinguish two links,
    so they stay.
    """
    if not isinstance(url, str):
        return ""
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return ""
    kept = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if name not in TRACKING_PARAMS
        and not name.lower().startswith(TRACKING_PREFIXES)
    ]
    kept.sort()
    identity = "%s://%s%s" % (
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path.rstrip("/"),
    )
    if kept:
        identity += "?" + urlencode(kept)
    return identity


def already_known(urls, jobs, entries) -> dict:
    """Which of these URLs the queue or the history already holds.

    A queued URL is reported once, as queued; history only answers for URLs
    the queue does not already hold.
    """
    queued = {
        normalize_url(job.url) for job in jobs if job.state in ACTIVE_STATES
    }
    recorded = {
        normalize_url(entry.url)
        for entry in entries
        if not getattr(entry, "removed_at", "")
    }
    in_queue: List[str] = []
    in_history: List[str] = []
    seen = set()
    for url in urls:
        key = normalize_url(url)
        if not key or key in seen:
            continue
        seen.add(key)
        if key in queued:
            in_queue.append(url)
        elif key in recorded:
            in_history.append(url)
    return {"in_queue": in_queue, "in_history": in_history}


def supported_sites() -> List[dict]:
    """The platforms the app already knows, for the extension's page scanner."""
    return [
        {
            "pattern": pattern,
            "platform": platform,
            "name": PLATFORM_NAMES.get(platform, platform),
        }
        for pattern, platform in PLATFORM_PATTERNS
    ]


def download_choices() -> dict:
    """What the popup may offer: the download path's two types and a resolution."""
    return {"outputs": list(OUTPUTS), "resolutions": list(RESOLUTIONS)}


def handle_message(msg: dict, store, history, options: dict) -> dict:
    """Answer one host message. Always returns a reply dict, never raises."""
    cmd = msg.get("cmd")
    if cmd == "ping":
        return {"ok": True, "version": __version__, "protocol": PROTOCOL_VERSION}
    if cmd == "sites":
        return {"ok": True, "sites": supported_sites()}
    if cmd == "formats":
        reply = {"ok": True}
        reply.update(download_choices())
        return reply
    if cmd in ("check", "add"):
        urls = msg.get("urls")
        if not isinstance(urls, list):
            return {"ok": False, "error": "urls must be a list"}
        clean = [u for u in urls if isinstance(u, str) and u.strip()]
        if cmd == "check":
            history.load()
            reply = {"ok": True}
            reply.update(already_known(clean, store.jobs, history.entries()))
            return reply
        Queue(store).add_many(clean, options)
        store.save()
        return {"ok": True, "added": len(clean)}
    return {"ok": False, "error": "unknown command"}
