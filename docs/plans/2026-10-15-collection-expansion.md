# Collection Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a pasted playlist, channel, or profile URL expand into its videos and enter the queue after the user confirms.

**Architecture:** A Qt-free platform classifier (`sites/collections.py`) and a Qt-free expansion engine (`core/collections.py`) that lists a collection with yt-dlp's `extract_flat` and no download. A `QThread` worker (`workers/expand_worker.py`) runs it for the GUI. The Queue tab owns the expand-then-confirm flow; the single Download tab hands collection URLs to the Queue through one signal.

**Tech Stack:** Python 3.8+, PyQt5 (GUI), yt-dlp (listing engine), pytest. No new dependencies.

**Spec:** `docs/specs/2026-10-15-collection-expansion-design.md`

## Global Constraints

- `core/` must not import PyQt5. Enforced by `tests/test_core_isolation.py`.
- `sites/` is Qt-free too; keep it that way.
- No new runtime dependencies. yt-dlp is the only listing engine.
- Error copy routes through `sites.errors.classify_error`; platform expectations through `sites.collections.collection_note`.
- Pure helpers get pytest tests. Network calls and Qt widgets do not (repo convention); verify those with the offscreen construction check.
- All existing tests must stay green throughout (`python -m pytest`).
- Lint: `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics` must print `0`.
- Conventional Commits. Never push without asking.

## File Structure

- `sites/collections.py` (new) — platform classification and honest per-platform notes. Pure.
- `core/collections.py` (new) — `CollectionEntry`, `ExpandResult`, `entries_from_info`, `new_entries` (pure) and `expand_collection` (network).
- `workers/expand_worker.py` (new) — `QThread` wrapper.
- `core/queue.py` (modify) — `QueueJob.title`, `Queue.add(title=...)`.
- `ui/dialogs.py` (modify) — `ExpandConfirmDialog`.
- `ui/batch_tab.py` (modify) — expansion flow, table shows title.
- `ui/single_tab.py` (modify) — `collection_requested` signal.
- `ui/main_window.py` (modify) — route the signal to the Queue tab.
- `cli.py` (modify) — `queue add --expand`.
- `tests/test_collections.py` (new), `tests/test_queue.py` (extend), `tests/test_ui_wiring.py` (extend).
- `README.md`, `CHANGELOG.md`, `AGENTS.md` (modify) — docs.

---

### Task 1: Platform classification

**Files:**
- Create: `sites/collections.py`
- Test: `tests/test_collections.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `classify_url(url: str) -> str` returning `"video"`, `"collection"`, or `"unknown"`; `collection_note(platform: str) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_collections.py`:

```python
import pytest

from sites.collections import classify_url, collection_note


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/playlist?list=PL123", "collection"),
        ("https://www.youtube.com/@somechannel", "collection"),
        ("https://www.youtube.com/@somechannel/videos", "collection"),
        ("https://www.youtube.com/channel/UCabc123", "collection"),
        ("https://www.youtube.com/c/SomeName", "collection"),
        ("https://www.youtube.com/watch?v=abc", "video"),
        ("https://www.youtube.com/watch?v=abc&list=PL123", "video"),
        ("https://youtu.be/abc", "unknown"),
        ("https://www.instagram.com/someuser/", "collection"),
        ("https://www.instagram.com/p/abc/", "video"),
        ("https://www.instagram.com/reel/abc/", "video"),
        ("https://www.tiktok.com/@user", "collection"),
        ("https://www.tiktok.com/@user/video/123", "video"),
        ("https://twitter.com/user", "collection"),
        ("https://twitter.com/user/status/123", "video"),
        ("https://x.com/user/status/123", "video"),
        ("https://www.facebook.com/somepage", "collection"),
        ("https://www.facebook.com/watch/?v=123", "video"),
        ("https://space.bilibili.com/12345", "collection"),
        ("https://www.bilibili.com/video/BV1xx", "video"),
        ("https://www.douyin.com/user/MS4wLjAB", "collection"),
        ("https://www.douyin.com/video/7123", "video"),
        ("https://example.com/whatever", "unknown"),
        ("", "unknown"),
    ],
)
def test_classify_url(url, expected):
    assert classify_url(url) == expected


def test_collection_note_youtube_is_empty():
    assert collection_note("youtube") == ""


def test_collection_note_instagram_mentions_posts():
    assert "post" in collection_note("instagram").lower()


def test_collection_note_unknown_is_empty():
    assert collection_note("nope") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_collections.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sites.collections'`

- [ ] **Step 3: Write minimal implementation**

Create `sites/collections.py`:

```python
"""Classify a URL as a single video or a collection (playlist, channel,
profile), and describe how reliable listing is per platform.

Pure: no network, no Qt. The listing itself lives in core/collections.py.
"""

import re
from urllib.parse import urlparse

# A URL that points at one video. Checked first, so a video URL that also
# carries a playlist parameter (watch?v=X&list=Y) stays a single video.
VIDEO_PATTERNS = (
    r"youtube\.com/watch",
    r"instagram\.com/(?:p|reel|tv)/",
    r"(?:twitter|x)\.com/[^/]+/status/",
    r"tiktok\.com/@[^/]+/video/",
    r"facebook\.com/(?:watch|reel|.*?/videos/)",
    r"bilibili\.com/video/",
    r"douyin\.com/video/",
)

# A URL that points at many videos, and the platform key it belongs to.
COLLECTION_PATTERNS = (
    (r"youtube\.com/playlist", "youtube"),
    (r"youtube\.com/(?:@[^/]+|channel/|c/|user/)", "youtube"),
    (r"instagram\.com/[^/]+/?$", "instagram"),
    (r"tiktok\.com/@[^/]+/?$", "tiktok"),
    (r"(?:twitter|x)\.com/[^/]+/?$", "twitter"),
    (r"facebook\.com/[^/]+/?$", "facebook"),
    (r"space\.bilibili\.com/\d+", "bilibili"),
    (r"bilibili\.com/space/", "bilibili"),
    (r"douyin\.com/user/", "douyin"),
)

_NOTES = {
    "instagram": "Instagram profile listing is best-effort and often returns "
                 "nothing. Paste individual post links instead.",
    "tiktok": "TikTok profile listing is best-effort and rate-limited. Try "
              "again later or paste individual video links.",
    "twitter": "Twitter/X timeline listing is best-effort and needs cookies. "
               "Try again or paste individual post links.",
    "facebook": "Facebook page listing rarely works. Paste individual video "
                "links instead.",
    "douyin": "Douyin profile listing is best-effort and often returns "
              "nothing. Paste individual video links instead.",
    "bilibili": "Bilibili channel listing may need cookies.",
}


def _target(url: str) -> str:
    """Host + path + query, lowercased, without the scheme."""
    if not url:
        return ""
    if "//" not in url:
        url = "//" + url
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    if not host:
        return ""
    path = (parsed.path or "").rstrip("/")
    target = host + path
    if parsed.query:
        target += "?" + parsed.query
    return target


def classify_url(url: str) -> str:
    """Return "video", "collection", or "unknown"."""
    target = _target(url)
    if not target:
        return "unknown"
    for pattern in VIDEO_PATTERNS:
        if re.search(pattern, target):
            return "video"
    for pattern, _platform in COLLECTION_PATTERNS:
        if re.search(pattern, target):
            return "collection"
    return "unknown"


def collection_note(platform: str) -> str:
    """Honest expectation text for listing this platform. Empty when reliable."""
    return _NOTES.get((platform or "").lower(), "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_collections.py -v`
Expected: PASS (all cases)

- [ ] **Step 5: Commit**

```bash
git add sites/collections.py tests/test_collections.py
git commit -m "feat(sites): classify video vs collection URLs and note per-platform listing"
```

---

### Task 2: Expansion data model and pure helpers

**Files:**
- Create: `core/collections.py`
- Test: `tests/test_collections.py` (extend)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `CollectionEntry(url: str, title: str = "", id: str = "")`
  - `ExpandResult(platform: str = "", entries: list = [], total: int = None, truncated: bool = False, error: str = None, category: str = None)`
  - `DEFAULT_LIMIT = 200`
  - `entries_from_info(info: dict, limit: int = 200, platform: str = "") -> (list[CollectionEntry], int | None, bool)`
  - `new_entries(entries, existing_urls) -> (list[CollectionEntry], int)`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_collections.py`:

```python
from core.collections import (
    DEFAULT_LIMIT,
    CollectionEntry,
    entries_from_info,
    new_entries,
)


def test_entries_from_info_basic():
    info = {
        "playlist_count": 3,
        "entries": [
            {"url": "https://www.youtube.com/watch?v=a", "title": "A", "id": "a"},
            {"url": "https://www.youtube.com/watch?v=b", "title": "B", "id": "b"},
        ],
    }
    entries, total, truncated = entries_from_info(info, 200, "youtube")
    assert [e.title for e in entries] == ["A", "B"]
    assert total == 3
    assert truncated is True


def test_entries_from_info_builds_youtube_url_from_bare_id():
    info = {"entries": [{"id": "abc123", "title": "T"}]}
    entries, total, truncated = entries_from_info(info, 200, "youtube")
    assert entries[0].url == "https://www.youtube.com/watch?v=abc123"
    assert total is None
    assert truncated is False


def test_entries_from_info_prefers_webpage_url():
    info = {"entries": [{"url": "https://x/y", "webpage_url": "https://x/z",
                         "id": "1", "title": "T"}]}
    entries, _, _ = entries_from_info(info, 200, "youtube")
    assert entries[0].url == "https://x/z"


def test_entries_from_info_respects_limit():
    info = {"entries": [{"id": str(i), "title": str(i)} for i in range(10)]}
    entries, _, _ = entries_from_info(info, 3, "youtube")
    assert len(entries) == 3


def test_entries_from_info_title_falls_back_to_id():
    info = {"entries": [{"id": "abc"}]}
    entries, _, _ = entries_from_info(info, 200, "youtube")
    assert entries[0].title == "abc"


def test_entries_from_info_empty():
    entries, total, truncated = entries_from_info({}, 200, "youtube")
    assert entries == []
    assert total is None
    assert truncated is False


def test_entries_from_info_skips_blank_entries():
    info = {"entries": [None, {}, {"id": "ok", "title": "T"}]}
    entries, _, _ = entries_from_info(info, 200, "youtube")
    assert len(entries) == 1


def test_new_entries_skips_existing_and_counts():
    entries = [CollectionEntry(url="a"), CollectionEntry(url="b"),
               CollectionEntry(url="c")]
    kept, skipped = new_entries(entries, ["b"])
    assert [e.url for e in kept] == ["a", "c"]
    assert skipped == 1


def test_new_entries_dedupes_within_the_batch():
    entries = [CollectionEntry(url="a"), CollectionEntry(url="a")]
    kept, skipped = new_entries(entries, [])
    assert [e.url for e in kept] == ["a"]
    assert skipped == 1


def test_default_limit_value():
    assert DEFAULT_LIMIT == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_collections.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.collections'`

- [ ] **Step 3: Write minimal implementation**

Create `core/collections.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_collections.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/collections.py tests/test_collections.py
git commit -m "feat(core): collection entry model and pure expansion helpers"
```

---

### Task 3: The expansion engine

**Files:**
- Modify: `core/collections.py`
- Test: `tests/test_collections.py` (extend)

**Interfaces:**
- Consumes: `CollectionEntry`, `ExpandResult`, `entries_from_info`, `DEFAULT_LIMIT` (Task 2); `classify_url`/`collection_note` (Task 1); `sites.cookies.detect_platform`; `sites.errors.classify_error`.
- Produces: `expand_collection(url: str, cookies_file: str = None, limit: int = DEFAULT_LIMIT) -> ExpandResult`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_collections.py`:

```python
from core.collections import expand_collection


class FakeListYDL:
    info = {"playlist_count": 2, "entries": [
        {"url": "https://www.youtube.com/watch?v=a", "title": "A", "id": "a"},
        {"url": "https://www.youtube.com/watch?v=b", "title": "B", "id": "b"},
    ]}
    last_opts = {}

    def __init__(self, opts):
        FakeListYDL.last_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True):
        return FakeListYDL.info


def test_expand_collection_lists_entries(monkeypatch):
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeListYDL)
    result = expand_collection("https://www.youtube.com/@x")
    assert result.platform == "youtube"
    assert [e.title for e in result.entries] == ["A", "B"]
    assert result.error is None
    # The listing must never download and must not be a noplaylist call.
    assert FakeListYDL.last_opts["skip_download"] is True
    assert FakeListYDL.last_opts["noplaylist"] is False
    assert FakeListYDL.last_opts["extract_flat"] == "in_playlist"


class FakeEmptyYDL(FakeListYDL):
    info = {"entries": []}


def test_expand_collection_empty_is_an_error(monkeypatch):
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeEmptyYDL)
    result = expand_collection("https://www.youtube.com/@x")
    assert result.entries == []
    assert result.error
    assert result.category == "not_found"


class FakeBoomYDL:
    def __init__(self, opts):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True):
        raise RuntimeError("Sign in to confirm you are not a bot")


def test_expand_collection_classifies_failure(monkeypatch):
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeBoomYDL)
    result = expand_collection("https://www.instagram.com/someuser/")
    assert result.category == "blocked"
    assert result.error
    # Instagram's honest note wins over the generic classify_error message.
    assert "post" in result.error.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_collections.py::test_expand_collection_lists_entries -v`
Expected: FAIL with `ImportError: cannot import name 'expand_collection'`

- [ ] **Step 3: Write minimal implementation**

Append to `core/collections.py`:

```python
def expand_collection(url, cookies_file=None, limit=DEFAULT_LIMIT) -> ExpandResult:
    """List a collection URL's videos. Never downloads. Never raises."""
    import os

    from sites.collections import collection_note
    from sites.cookies import detect_platform
    from sites.errors import classify_error

    platform = detect_platform(url)
    opts = {
        "extract_flat": "in_playlist",
        "skip_download": True,
        "noplaylist": False,
        "playlistend": limit,
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
        "no_color": True,
        "age_limit": 99,
    }
    if cookies_file and os.path.isfile(cookies_file):
        opts["cookiefile"] = cookies_file

    try:
        from yt_dlp import YoutubeDL

        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        category, message = classify_error(str(exc), url)
        note = collection_note(platform)
        return ExpandResult(
            platform=platform, error=note or message, category=category,
        )

    if not info:
        return ExpandResult(
            platform=platform,
            error="Found no videos. The profile may be private or the listing "
                  "may be unsupported for this site.",
            category="not_found",
        )

    entries, total, truncated = entries_from_info(info, limit, platform)
    if not entries:
        return ExpandResult(
            platform=platform, total=total,
            error="Found no videos. The profile may be private or the listing "
                  "may be unsupported for this site.",
            category="not_found",
        )
    return ExpandResult(
        platform=platform, entries=entries, total=total, truncated=truncated,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_collections.py -v`
Expected: PASS

- [ ] **Step 5: Verify core stays Qt-free**

Run: `python -m pytest tests/test_core_isolation.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core/collections.py tests/test_collections.py
git commit -m "feat(core): expand_collection lists a playlist or channel via yt-dlp"
```

---

### Task 4: Queue job titles

**Files:**
- Modify: `core/queue.py`
- Test: `tests/test_queue.py` (extend)

**Interfaces:**
- Consumes: nothing.
- Produces: `QueueJob.title: str = ""`; `Queue.add(url, options=None, title="") -> QueueJob`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_queue.py`:

```python
def test_job_title_defaults_to_empty():
    from core.queue import QueueJob
    assert QueueJob(url="u").title == ""


def test_add_accepts_a_title():
    from core.queue import Queue
    queue = Queue()
    job = queue.add("https://youtu.be/x", title="My Video")
    assert job.title == "My Video"


def test_store_round_trip_without_title_is_backward_compatible(tmp_path):
    import json
    from core.queue import QueueStore
    path = tmp_path / "queue.json"
    path.write_text(json.dumps({
        "version": 1, "paused": False,
        "jobs": [{"id": "a", "url": "https://youtu.be/x", "state": "pending"}],
    }))
    store = QueueStore(str(path))
    store.load()
    assert store.jobs[0].title == ""


def test_store_persists_title(tmp_path):
    from core.queue import Queue, QueueStore
    path = str(tmp_path / "queue.json")
    queue = Queue(QueueStore(path))
    queue.add("https://youtu.be/x", title="My Video")
    queue.store.save()
    again = QueueStore(path)
    again.load()
    assert again.jobs[0].title == "My Video"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_queue.py -v`
Expected: FAIL with `TypeError: add() got an unexpected keyword argument 'title'`

- [ ] **Step 3: Write minimal implementation**

In `core/queue.py`, add the field to `QueueJob` (after `url`):

```python
@dataclass
class QueueJob:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    url: str = ""
    title: str = ""
    state: str = "pending"
```

And change `Queue.add`:

```python
    def add(self, url: str, options: Optional[dict] = None,
            title: str = "") -> QueueJob:
        job = QueueJob(url=url, title=title, options=dict(options or {}))
        self.jobs.append(job)
        return job
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_queue.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/queue.py tests/test_queue.py
git commit -m "feat(queue): carry a job title through the store"
```

---

### Task 5: Expansion worker

**Files:**
- Create: `workers/expand_worker.py`
- Test: `tests/test_ui_wiring.py` (extend)

**Interfaces:**
- Consumes: `expand_collection` (Task 3).
- Produces: `ExpandWorker(QtCore.QThread)` with `done_signal = pyqtSignal(object)` and `error_signal = pyqtSignal(str)`; constructor `ExpandWorker(url, cookies_file=None, limit=200)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ui_wiring.py`:

```python
def test_expand_worker_exposes_its_signals():
    from workers.expand_worker import ExpandWorker

    assert hasattr(ExpandWorker, "done_signal")
    assert hasattr(ExpandWorker, "error_signal")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_wiring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'workers.expand_worker'`

- [ ] **Step 3: Write minimal implementation**

Create `workers/expand_worker.py`:

```python
from PyQt5 import QtCore


class ExpandWorker(QtCore.QThread):
    """List a collection URL off the UI thread."""

    done_signal = QtCore.pyqtSignal(object)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, url, cookies_file=None, limit=200):
        super().__init__()
        self.url = url
        self.cookies_file = cookies_file
        self.limit = limit

    def run(self):
        from core.collections import expand_collection

        try:
            result = expand_collection(
                self.url, cookies_file=self.cookies_file, limit=self.limit,
            )
        except Exception as exc:  # noqa: BLE001 - report, never crash the thread
            self.error_signal.emit(str(exc))
            return
        self.done_signal.emit(result)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_wiring.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add workers/expand_worker.py tests/test_ui_wiring.py
git commit -m "feat(workers): expand worker lists a collection off the UI thread"
```

---

### Task 6: Confirm dialog

**Files:**
- Modify: `ui/dialogs.py`

**Interfaces:**
- Consumes: `ExpandResult` (Task 2).
- Produces: `ExpandConfirmDialog(result, skipped_count=0, parent=None)` with `.chosen_limit() -> int` returning the number to add.

- [ ] **Step 1: Add the dialog**

Append to `ui/dialogs.py`:

```python
from sites.collections import collection_note


def _platform_label(platform: str) -> str:
    return (platform or "This site").capitalize()


class ExpandConfirmDialog(QtWidgets.QDialog):
    """Confirm how many videos of a found collection to queue."""

    def __init__(self, result, skipped_count=0, parent=None):
        super().__init__(parent)
        self.result = result
        total = result.total if result.total is not None else len(result.entries)
        self._max = max(1, total)
        self._default = min(200, len(result.entries) or self._max)

        self.setWindowTitle("Add collection to queue")
        self.resize(560, 420)
        layout = QtWidgets.QVBoxLayout(self)

        found = result.total if result.total is not None else len(result.entries)
        layout.addWidget(QtWidgets.QLabel(
            "%s: %d video(s) found." % (_platform_label(result.platform), found)
        ))

        note = collection_note(result.platform)
        if note:
            hint = QtWidgets.QLabel(note)
            hint.setWordWrap(True)
            layout.addWidget(hint)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Add first"))
        self.count_spin = QtWidgets.QSpinBox()
        self.count_spin.setRange(1, self._max)
        self.count_spin.setValue(self._default)
        row.addWidget(self.count_spin)
        row.addWidget(QtWidgets.QLabel("of %d" % found))
        row.addStretch(1)
        layout.addLayout(row)

        preview = QtWidgets.QListWidget()
        for entry in result.entries[:20]:
            preview.addItem(entry.title)
        if len(result.entries) > 20:
            preview.addItem("...and %d more" % (len(result.entries) - 20))
        layout.addWidget(preview)

        if skipped_count:
            layout.addWidget(QtWidgets.QLabel(
                "%d already in the queue will be skipped." % skipped_count
            ))

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chosen_limit(self) -> int:
        return self.count_spin.value()
```

- [ ] **Step 2: Verify it compiles and lints**

Run: `python -m py_compile ui/dialogs.py` then `python -m flake8 ui/dialogs.py --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: `0`

- [ ] **Step 3: Verify it constructs offscreen**

Run this one-off (expected to print `OK`):

```bash
python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PyQt5 import QtWidgets; app=QtWidgets.QApplication([]); from ui.dialogs import ExpandConfirmDialog; from core.collections import ExpandResult, CollectionEntry; d=ExpandConfirmDialog(ExpandResult(platform='youtube', entries=[CollectionEntry('u','T')], total=5), 2); print('OK', d.chosen_limit())"
```

Expected: `OK 1`

- [ ] **Step 4: Commit**

```bash
git add ui/dialogs.py
git commit -m "feat(ui): confirm dialog for a found collection"
```

---

### Task 7: Queue tab expansion flow

**Files:**
- Modify: `ui/batch_tab.py`

**Interfaces:**
- Consumes: `classify_url` (Task 1); `ExpandResult`, `new_entries` (Task 2); `ExpandWorker` (Task 5); `ExpandConfirmDialog` (Task 6).
- Produces: `QueueTab.expand_collection_url(url)`; the table shows `job.title or job.url`.

- [ ] **Step 1: Add the expansion flow**

In `ui/batch_tab.py`, add imports near the top:

```python
from sites.collections import classify_url
from ui.dialogs import ExpandConfirmDialog
from workers.expand_worker import ExpandWorker
```

Add `self._expand_worker = None` to `QueueTab.__init__` (next to `self.queue_worker = None`), then add a helper to collect queued URLs and the expansion entry point. Place after `_job_options`:

```python
    def _queued_urls(self):
        return [job.url for job in self.queue.jobs]

    def expand_collection_url(self, url):
        """List a collection URL and offer to enqueue its videos."""
        if self.queue_worker and self.queue_worker.isRunning():
            self.batch_log("Queue is running; finish or pause it first.")
            return
        self.add_urls_btn.setEnabled(False)
        self.paste_urls_btn.setEnabled(False)
        self.batch_log("Expanding %s ..." % (url,))
        cookies = self._batch_get_cookies_path()
        self._expand_worker = ExpandWorker(url, cookies_file=cookies)
        self._expand_worker.done_signal.connect(
            lambda result, u=url: self._on_expanded(u, result)
        )
        self._expand_worker.error_signal.connect(self._on_expand_error)
        self._expand_worker.start()

    def _on_expand_error(self, message):
        self._expand_re_enable()
        self.batch_log("Could not list the collection: %s" % message)

    def _expand_re_enable(self):
        self.add_urls_btn.setEnabled(True)
        self.paste_urls_btn.setEnabled(True)

    def _on_expanded(self, url, result):
        if result.error:
            self._expand_re_enable()
            self.batch_log(result.error)
            return
        kept, skipped = new_entries(result.entries, self._queued_urls())
        if not kept:
            self._expand_re_enable()
            self.batch_log("All %d found videos are already queued." % len(result.entries))
            return
        dialog = ExpandConfirmDialog(result, skipped, self)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            self._expand_re_enable()
            self.batch_log("Expansion cancelled.")
            return
        chosen = dialog.chosen_limit()
        if chosen > len(result.entries):
            self.batch_log("Fetching %d entries ..." % chosen)
            self._expand_worker = ExpandWorker(
                url, cookies_file=self._batch_get_cookies_path(), limit=chosen,
            )
            self._expand_worker.done_signal.connect(
                lambda more: self._add_expanded(more, chosen)
            )
            self._expand_worker.error_signal.connect(self._on_expand_error)
            self._expand_worker.start()
            return
        self._add_expanded(result, chosen)

    def _add_expanded(self, result, chosen):
        options = self._job_options()
        kept, _ = new_entries(result.entries[:chosen], self._queued_urls())
        for entry in kept:
            self.queue.add(entry.url, options, title=entry.title)
        self.queue.store.save()
        self.refresh_table()
        self._expand_re_enable()
        self.batch_log("Added %d video(s) to the queue." % len(kept))
```

- [ ] **Step 2: Route paste/add through classification**

Replace the body of `_add_jobs` so collections are expanded instead of added raw:

```python
    def _add_jobs(self, urls):
        singles = []
        collections = []
        skipped = 0
        for url in urls:
            if not looks_like_url(url):
                skipped += 1
            elif classify_url(url) == "collection":
                collections.append(url)
            else:
                singles.append(url)
        if singles:
            self.queue.add_many(singles, self._job_options())
            self.queue.store.save()
            self.refresh_table()
        if skipped:
            self.batch_log("Skipped %d line(s) that did not look like a URL." % skipped)
        for url in collections:
            self.expand_collection_url(url)
```

- [ ] **Step 3: Show the title in the table**

In `_insert_job_row`, change the URL cell to prefer the title:

```python
        url_item = QtWidgets.QTableWidgetItem(job.title or job.url)
        url_item.setToolTip(job.url)
        url_item.setIcon(icon_for_url(job.url))
```

- [ ] **Step 4: Verify it compiles and lints**

Run: `python -m py_compile ui/batch_tab.py` then `python -m flake8 ui/batch_tab.py --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: `0`

- [ ] **Step 5: Verify it constructs offscreen**

Run:

```bash
python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PyQt5 import QtWidgets, QtCore; app=QtWidgets.QApplication([]); QtCore.QSettings().setValue('first_run_done', True); from ui.batch_tab import QueueTab; t=QueueTab({'path':''}); print('OK', hasattr(t,'expand_collection_url'))"
```

Expected: `OK True`

- [ ] **Step 6: Commit**

```bash
git add ui/batch_tab.py
git commit -m "feat(queue): expand pasted collections into confirmed queue jobs"
```

---

### Task 8: Single-tab handoff

**Files:**
- Modify: `ui/single_tab.py`, `ui/main_window.py`

**Interfaces:**
- Consumes: `classify_url` (Task 1); `QueueTab.expand_collection_url` (Task 7).
- Produces: `SingleTab.collection_requested = QtCore.pyqtSignal(str)`.

- [ ] **Step 1: Add the signal and the guard**

In `ui/single_tab.py`, add the import and the signal:

```python
from sites.collections import classify_url
```

Inside `class SingleTab(QtWidgets.QWidget):`, above `__init__`:

```python
    collection_requested = QtCore.pyqtSignal(str)
```

At the top of `on_fetch_metadata`, after the empty check, add:

```python
        if classify_url(url) == "collection":
            self.show_hint("This is a playlist or channel; opening the Queue.")
            self.collection_requested.emit(url)
            return
```

Do the same at the top of `on_download`, after its empty check:

```python
        if classify_url(url) == "collection":
            self.collection_requested.emit(url)
            return
```

- [ ] **Step 2: Route the signal in the main window**

In `ui/main_window.py`, inside `init_ui` after the tabs are created:

```python
        self.single_tab.collection_requested.connect(self._route_collection)

    def _route_collection(self, url):
        self.tabs.setCurrentWidget(self.batch_tab)
        self.batch_tab.expand_collection_url(url)
```

- [ ] **Step 3: Verify it compiles and lints**

Run: `python -m py_compile ui/single_tab.py ui/main_window.py` then `python -m flake8 ui/single_tab.py ui/main_window.py --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: `0`

- [ ] **Step 4: Verify the handoff offscreen**

Run:

```bash
python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PyQt5 import QtWidgets, QtCore; app=QtWidgets.QApplication([]); QtCore.QSettings().setValue('first_run_done', True); from ui.main_window import MainWindow; w=MainWindow(); calls=[]; w.batch_tab.expand_collection_url=lambda u: calls.append(u); w.single_tab.url_input.setText('https://www.youtube.com/@x'); w.single_tab.on_fetch_metadata(); print('routed', calls==['https://www.youtube.com/@x'], 'tab', w.tabs.currentWidget() is w.batch_tab)"
```

Expected: `routed True tab True`

- [ ] **Step 5: Commit**

```bash
git add ui/single_tab.py ui/main_window.py
git commit -m "feat(ui): single tab hands collection URLs to the queue"
```

---

### Task 9: CLI `queue add --expand`

**Files:**
- Modify: `cli.py`
- Test: `tests/test_cli_queue.py` (extend)

**Interfaces:**
- Consumes: `expand_collection` (Task 3), `new_entries` (Task 2).
- Produces: `socialclip queue add --expand <url>`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_queue.py`:

```python
def test_queue_add_expand_lists_and_enqueues(monkeypatch, tmp_path):
    import cli
    from core.collections import CollectionEntry, ExpandResult

    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(tmp_path / "queue.json"))
    monkeypatch.setattr(
        cli, "_expand_for_cli",
        lambda url, cookies: ExpandResult(
            platform="youtube",
            entries=[CollectionEntry("https://www.youtube.com/watch?v=a", "A")],
        ),
    )
    rc = cli.main(["queue", "add", "--expand", "https://www.youtube.com/@x"])
    assert rc == 0

    from core.queue import QueueStore
    store = QueueStore(str(tmp_path / "queue.json"))
    store.load()
    assert [j.title for j in store.jobs] == ["A"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli_queue.py::test_queue_add_expand_lists_and_enqueues -v`
Expected: FAIL with `SystemExit` from argparse (unknown argument `--expand`)

- [ ] **Step 3: Write minimal implementation**

In `cli.py`, add the flag to the `queue add` parser (after line 288):

```python
    qa.add_argument("--expand", action="store_true")
    qa.add_argument("--cookies")
```

Add the injectable helper near `_cmd_queue`:

```python
def _expand_for_cli(url, cookies):
    from core.collections import expand_collection
    return expand_collection(url, cookies_file=cookies)


def _collect_expanded(urls, cookies, limit=200):
    from core.collections import new_entries
    from sites.cookies import get_cookie_path

    pairs = []
    for url in urls:
        cookie = cookies or get_cookie_path(url)
        result = _expand_for_cli(url, cookie)
        if result.error:
            print("warning: %s" % result.error, file=sys.stderr)
            continue
        kept, _ = new_entries(result.entries[:limit], [p[0] for p in pairs])
        pairs.extend((entry.url, entry.title) for entry in kept)
    return pairs
```

Replace the `add` branch of `_cmd_queue`:

```python
    if command == "add":
        if getattr(args, "expand", False):
            pairs = _collect_expanded(args.urls, args.cookies)
            for url, title in pairs:
                queue.add(url, title=title)
            queue.store.save()
            n = len(pairs)
        else:
            queue.add_many(args.urls)
            queue.store.save()
            n = len(args.urls)
        if args.json:
            print(json.dumps({"schema_version": SCHEMA_VERSION, "added": n}))
        else:
            print(f"added {n}")
        return EXIT_OK
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli_queue.py -v`
Expected: PASS

- [ ] **Step 5: Verify the whole suite and lint**

Run: `python -m pytest -q` then `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: all pass; `0`

- [ ] **Step 6: Commit**

```bash
git add cli.py tests/test_cli_queue.py
git commit -m "feat(cli): queue add --expand enqueues a whole collection"
```

---

### Task 10: Documentation

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `AGENTS.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing code-facing.

- [ ] **Step 1: README**

Add to the features list: paste a playlist, channel, or profile URL and the Queue offers to add its videos (best-effort off YouTube). Note the CLI `queue add --expand`.

- [ ] **Step 2: CHANGELOG**

Under a new unreleased heading, add an `### Added` entry for collection expansion and mention the `queue add --expand` flag.

- [ ] **Step 3: AGENTS.md**

Add to the layout list: `sites/collections.py`, `core/collections.py`, `workers/expand_worker.py`, and a one-line note that collection listing is yt-dlp `extract_flat` and best-effort off YouTube.

- [ ] **Step 4: Commit**

```bash
git add README.md CHANGELOG.md AGENTS.md
git commit -m "docs: collection expansion"
```

---

## Self-Review

- **Spec coverage:** classification (Task 1), engine + pure helpers (Tasks 2-3), title data model (Task 4), worker (Task 5), confirm dialog (Task 6), queue flow + table (Task 7), single-tab handoff (Task 8), CLI opt-in (Task 9), docs (Task 10). Every spec section maps to a task. The re-fetch path from the spec is Task 7 Step 1 (`chosen > len(entries)`).
- **Placeholder scan:** no TBD/TODO; every code step carries real code.
- **Type consistency:** `ExpandResult`/`CollectionEntry` fields are identical across Tasks 2, 3, 6, 7, 9; `new_entries(entries, existing_urls)` returns `(kept, skipped)` everywhere it is used; `ExpandWorker(url, cookies_file=, limit=)` matches Task 5.
