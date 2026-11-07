"""Native-messaging protocol shared by the browser host and the app.

The transport is the browser's stdin/stdout framing: a 4-byte little-endian
length, then that many bytes of UTF-8 JSON. Everything here is pure so the
host, the GUI and the tests can share it without Qt.
"""

import json
import struct
from typing import List
from urllib.parse import urlsplit

from core.version import __version__

HOST_NAME = "com.petra_dot.socialclip"
PROTOCOL_VERSION = 1
MAX_SCAN_LINKS = 200

# A job in one of these states is still work the user is waiting on.
ACTIVE_STATES = ("pending", "running", "paused")


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
    """A URL's identity for duplicate checks: no query, no fragment, no slash."""
    if not isinstance(url, str):
        return ""
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return ""
    return "%s://%s%s" % (
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path.rstrip("/"),
    )


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
