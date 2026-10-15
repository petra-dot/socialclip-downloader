# In-App Updater Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The app checks GitHub for a newer release, shows a top-right indicator, and on Windows downloads, digest-verifies, and installs it with a restart; elsewhere it opens the release page.

**Architecture:** A Qt-free `core/updater.py` (stdlib only) does the version compare, GitHub fetch, asset select, download, digest verify, and the Windows apply. Two `QThread`s in `workers/update_worker.py` run check and download off the UI thread. `ui/update_indicator.py` is a dumb stateful button; `ui/main_window.py` owns the state machine and wires the workers.

**Tech Stack:** Python 3.8+, PyQt5, stdlib `urllib`/`hashlib`/`json`/`subprocess`, pytest. No new dependencies.

**Spec:** `docs/specs/2026-10-15-in-app-updater-design.md`

## Global Constraints

- `core/` must not import PyQt5. Enforced by `tests/test_core_isolation.py`.
- No new runtime dependencies; stdlib only in `core/updater.py`.
- The download host must be `github.com` or `objects.githubusercontent.com`; anything else is refused.
- The SHA-256 must be verified against the release API digest before any install.
- Windows self-updates; macOS/Linux and source runs notify and open the release page.
- The startup check is cached to at most once per 24h (`QSettings`); the manual menu item bypasses it.
- All existing tests stay green (`python -m pytest -q`); flake8 `--select=E9,F63,F7,F82` prints `0`.
- Conventional Commits. Never push without asking.

## File Structure

- `core/updater.py` (new) — version/release/asset/digest helpers (pure), fetch, download, apply, fallback, cleanup.
- `workers/update_worker.py` (new) — `UpdateCheckWorker`, `UpdateDownloadWorker`.
- `ui/update_indicator.py` (new) — `UpdateButton`.
- `ui/dialogs.py` (modify) — `show_update_ready`.
- `ui/main_window.py` (modify) — header row, Help menu item, state machine.
- `socialclip_downloader.py` (modify) — `--apply-update` branch.
- `tests/test_updater.py` (new), `tests/test_ui_wiring.py` (extend).
- `README.md`, `CHANGELOG.md`, `AGENTS.md` (modify).

---

### Task 1: Version, release, asset, and digest helpers

**Files:**
- Create: `core/updater.py`
- Test: `tests/test_updater.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `parse_version(text) -> tuple`; `is_newer(latest, current) -> bool`; `AssetInfo(name, download_url, digest=None)`; `ReleaseInfo(tag, version, page_url, assets)`; `release_from_json(data) -> ReleaseInfo`; `select_asset(assets, platform=None) -> AssetInfo | None`; `verify_digest(path, expected_hex) -> bool`; constants `GITHUB_OWNER`, `REPO`, `LATEST_API`, `RELEASE_PAGE`, `ASSET_BY_PLATFORM`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_updater.py`:

```python
import pytest

from core.updater import (
    AssetInfo,
    is_newer,
    parse_version,
    release_from_json,
    select_asset,
    verify_digest,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("v0.9.2", (0, 9, 2)),
        ("0.9.2", (0, 9, 2)),
        ("v0.10.0", (0, 10, 0)),
        ("1.2", (1, 2)),
        ("", ()),
        ("nonsense", ()),
        ("v0.9.2-beta", (0, 9, 2)),
    ],
)
def test_parse_version(text, expected):
    assert parse_version(text) == expected


@pytest.mark.parametrize(
    "latest,current,expected",
    [
        ("v0.10.0", "0.9.2", True),
        ("v0.9.2", "0.9.2", False),
        ("v0.9.1", "0.9.2", False),
        ("v0.9.10", "0.9.2", True),
        ("", "0.9.2", False),
    ],
)
def test_is_newer(latest, current, expected):
    assert is_newer(latest, current) is expected


def test_release_from_json_full():
    data = {
        "tag_name": "v0.10.0",
        "html_url": "https://github.com/petra-dot/socialclip-downloader/releases/tag/v0.10.0",
        "assets": [
            {"name": "socialclip-downloader-windows.exe",
             "browser_download_url": "https://github.com/x/a.exe",
             "digest": "sha256:abc123"},
            {"name": "socialclip-windows.exe",
             "browser_download_url": "https://github.com/x/cli.exe"},
        ],
    }
    release = release_from_json(data)
    assert release.tag == "v0.10.0"
    assert release.version == "0.10.0"
    assert release.assets[0].digest == "abc123"
    assert release.assets[1].digest is None


def test_release_from_json_missing_fields():
    release = release_from_json({"tag_name": "v1.0.0"})
    assert release.assets == []
    assert release.page_url


def test_release_from_json_drops_incomplete_assets():
    data = {"tag_name": "v1", "assets": [{"name": "x"}, {"browser_download_url": "u"}]}
    assert release_from_json(data).assets == []


def test_select_asset_by_platform():
    assets = [
        AssetInfo("socialclip-downloader-windows.exe", "u1", "d1"),
        AssetInfo("socialclip-downloader-macos", "u2", "d2"),
    ]
    assert select_asset(assets, "win32").name.endswith("windows.exe")
    assert select_asset(assets, "darwin").name.endswith("macos")
    assert select_asset(assets, "linux") is None


def test_verify_digest_match_and_mismatch(tmp_path):
    import hashlib
    path = tmp_path / "f.bin"
    path.write_bytes(b"hello")
    good = hashlib.sha256(b"hello").hexdigest()
    assert verify_digest(str(path), good) is True
    assert verify_digest(str(path), "deadbeef") is False
    assert not path.exists()  # mismatch deletes the file


def test_verify_digest_no_expected_returns_false(tmp_path):
    path = tmp_path / "f.bin"
    path.write_bytes(b"hello")
    assert verify_digest(str(path), None) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_updater.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.updater'`

- [ ] **Step 3: Write minimal implementation**

Create `core/updater.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_updater.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/updater.py tests/test_updater.py
git commit -m "feat(updater): version, release, asset and digest helpers"
```

---

### Task 2: Fetch and download

**Files:**
- Modify: `core/updater.py`
- Test: `tests/test_updater.py` (extend)

**Interfaces:**
- Consumes: Task 1 (`ReleaseInfo`, `AssetInfo`, `release_from_json`).
- Produces: `fetch_latest_release(opener=None, timeout=10) -> ReleaseInfo`; `download_asset(asset, dest, progress=None, cancel=None, opener=None) -> str`; `DownloadCancelled` (exception).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_updater.py`:

```python
from core.updater import DownloadCancelled, download_asset, fetch_latest_release


class _FakeResponse:
    def __init__(self, body, headers=None):
        self._body = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, size=-1):
        if size is None or size < 0:
            data, self._body = self._body, b""
            return data
        data, self._body = self._body[:size], self._body[size:]
        return data


def test_fetch_latest_release_parses(monkeypatch):
    payload = b'{"tag_name": "v0.10.0", "assets": []}'
    monkeypatch.setattr(
        "core.updater.urllib.request.urlopen",
        lambda req, timeout=None: _FakeResponse(payload),
    )
    release = fetch_latest_release()
    assert release.tag == "v0.10.0"


def test_download_asset_writes_and_reports_progress(tmp_path):
    asset = AssetInfo("x", "https://github.com/petra-dot/socialclip-downloader/releases/x", None)
    seen = []
    dest = str(tmp_path / "out.bin")
    body = b"abcdef" * 20000
    download_asset(
        asset, dest, progress=lambda done, total: seen.append(done),
        opener=lambda req, timeout=None: _FakeResponse(body, {"Content-Length": str(len(body))}),
    )
    assert open(dest, "rb").read() == body
    assert seen and seen[-1] == len(body)


def test_download_asset_refuses_foreign_host(tmp_path):
    asset = AssetInfo("x", "https://evil.example.com/x", None)
    with pytest.raises(ValueError):
        download_asset(asset, str(tmp_path / "o"), opener=lambda *a, **k: _FakeResponse(b""))


def test_download_asset_honors_cancel(tmp_path):
    asset = AssetInfo("x", "https://github.com/petra-dot/socialclip-downloader/releases/x", None)
    with pytest.raises(DownloadCancelled):
        download_asset(
            asset, str(tmp_path / "o"), cancel=lambda: True,
            opener=lambda req, timeout=None: _FakeResponse(b"x" * 10, {}),
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_updater.py -v`
Expected: FAIL with `ImportError: cannot import name 'download_asset'`

- [ ] **Step 3: Write minimal implementation**

Append to `core/updater.py`:

```python
import json
import urllib.parse
import urllib.request


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


def download_asset(asset, dest, progress=None, cancel=None, opener=None) -> str:
    open_url = opener or urllib.request.urlopen
    host = urllib.parse.urlparse(asset.download_url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise ValueError("refusing to download from %s" % (host or "an unknown host"))
    request = urllib.request.Request(
        asset.download_url, headers={"User-Agent": "SocialClip-Downloader"}
    )
    with open_url(request) as response, open(dest, "wb") as out:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_updater.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/updater.py tests/test_updater.py
git commit -m "feat(updater): fetch the latest release and download the asset"
```

---

### Task 3: Apply, batch fallback, and cleanup

**Files:**
- Modify: `core/updater.py`
- Test: `tests/test_updater.py` (extend)

**Interfaces:**
- Consumes: Task 1-2.
- Produces: `ApplyPlan(target, source, wait_pid)`; `write_batch_fallback(plan, temp_dir=None) -> str`; `apply_update(target, wait_pid, timeout=30, sleep=time.sleep) -> int`; `cleanup_update_temp(temp_dir=None, prefix="socialclip-update-") -> int`; `update_temp_path(version, temp_dir=None) -> str`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_updater.py`:

```python
from core.updater import ApplyPlan, cleanup_update_temp, update_temp_path, write_batch_fallback


def test_update_temp_path_is_prefixed():
    path = update_temp_path("0.10.0")
    assert "socialclip-update-0.10.0" in path


def test_write_batch_fallback_names_source_and_target(tmp_path):
    plan = ApplyPlan(target="C:/app/old.exe", source="C:/tmp/new.exe", wait_pid=123)
    bat = write_batch_fallback(plan, temp_dir=str(tmp_path))
    assert bat.endswith(".bat")
    text = open(bat, encoding="ascii").read()
    assert "C:/app/old.exe" in text
    assert "C:/tmp/new.exe" in text
    assert "start" in text


def test_cleanup_update_temp_removes_leftovers(tmp_path):
    (tmp_path / "socialclip-update-0.10.0.exe").write_bytes(b"x")
    (tmp_path / "unrelated.exe").write_bytes(b"x")
    removed = cleanup_update_temp(temp_dir=str(tmp_path))
    assert removed == 1
    assert not (tmp_path / "socialclip-update-0.10.0.exe").exists()
    assert (tmp_path / "unrelated.exe").exists()


def test_apply_update_retries_then_succeeds(monkeypatch, tmp_path):
    import core.updater as updater
    source = tmp_path / "src.exe"
    source.write_bytes(b"new")
    target = tmp_path / "tgt.exe"
    target.write_bytes(b"old")
    monkeypatch.setattr(updater.sys, "executable", str(source))
    monkeypatch.setattr(updater, "_spawn_detached", lambda cmd: None)
    calls = {"n": 0}
    real_copy = updater.shutil.copy2

    def flaky_copy(a, b):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("locked")
        return real_copy(a, b)

    monkeypatch.setattr(updater.shutil, "copy2", flaky_copy)
    rc = updater.apply_update(str(target), wait_pid=1, timeout=5, sleep=lambda s: None)
    assert rc == 0
    assert target.read_bytes() == b"new"
    assert calls["n"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_updater.py -v`
Expected: FAIL with `ImportError: cannot import name 'ApplyPlan'`

- [ ] **Step 3: Write minimal implementation**

Append to `core/updater.py`:

```python
import shutil
import subprocess
import tempfile
import time


@dataclass
class ApplyPlan:
    target: str
    source: str
    wait_pid: int


def update_temp_path(version, temp_dir=None) -> str:
    temp_dir = temp_dir or tempfile.gettempdir()
    return os.path.join(temp_dir, "socialclip-update-%s.exe" % version)


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


def apply_update(target, wait_pid, timeout=30, sleep=time.sleep) -> int:
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
    plan = ApplyPlan(target=target, source=source, wait_pid=wait_pid)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_updater.py -v`
Expected: PASS

- [ ] **Step 5: Verify core stays Qt-free**

Run: `python -m pytest tests/test_core_isolation.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core/updater.py tests/test_updater.py
git commit -m "feat(updater): windows apply, batch fallback and temp cleanup"
```

---

### Task 4: Update workers

**Files:**
- Create: `workers/update_worker.py`
- Test: `tests/test_ui_wiring.py` (extend)

**Interfaces:**
- Consumes: Task 2-3 (`fetch_latest_release`, `download_asset`).
- Produces: `UpdateCheckWorker(current_version)` with `done_signal(object)` / `error_signal(str)`; `UpdateDownloadWorker(asset, dest)` with `progress_signal(int)` / `done_signal(str)` / `error_signal(str)` and a `cancel()` method.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ui_wiring.py`:

```python
def test_update_workers_expose_their_signals():
    from workers.update_worker import UpdateCheckWorker, UpdateDownloadWorker

    assert hasattr(UpdateCheckWorker, "done_signal")
    assert hasattr(UpdateCheckWorker, "error_signal")
    assert hasattr(UpdateDownloadWorker, "progress_signal")
    assert hasattr(UpdateDownloadWorker, "done_signal")
    assert hasattr(UpdateDownloadWorker, "error_signal")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_wiring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'workers.update_worker'`

- [ ] **Step 3: Write minimal implementation**

Create `workers/update_worker.py`:

```python
from PyQt5 import QtCore


class UpdateCheckWorker(QtCore.QThread):
    """Ask GitHub for the latest release, off the UI thread."""

    done_signal = QtCore.pyqtSignal(object)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, current_version):
        super().__init__()
        self.current_version = current_version

    def run(self):
        from core.updater import fetch_latest_release, is_newer

        try:
            release = fetch_latest_release()
        except Exception as exc:  # noqa: BLE001 - report, never crash the thread
            self.error_signal.emit(str(exc))
            return
        if is_newer(release.version, self.current_version):
            self.done_signal.emit(release)
        else:
            self.done_signal.emit(None)


class UpdateDownloadWorker(QtCore.QThread):
    """Download and digest-verify an update asset, off the UI thread."""

    progress_signal = QtCore.pyqtSignal(int)
    done_signal = QtCore.pyqtSignal(str)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, asset, dest):
        super().__init__()
        self.asset = asset
        self.dest = dest
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        from core.updater import DownloadCancelled, download_asset, verify_digest

        def on_progress(done, total):
            if total:
                self.progress_signal.emit(int(done / total * 100))

        try:
            download_asset(
                self.asset, self.dest, progress=on_progress,
                cancel=lambda: self._cancelled,
            )
            if not verify_digest(self.dest, self.asset.digest):
                self.error_signal.emit(
                    "Download failed verification. The file was deleted."
                )
                return
        except DownloadCancelled:
            return  # a cancelled download emits nothing; the UI restores its own state
        except Exception as exc:  # noqa: BLE001
            self.error_signal.emit(str(exc))
            return
        self.done_signal.emit(self.dest)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_wiring.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add workers/update_worker.py tests/test_ui_wiring.py
git commit -m "feat(workers): update check and download threads"
```

---

### Task 5: `--apply-update` entry point

**Files:**
- Modify: `socialclip_downloader.py`

**Interfaces:**
- Consumes: Task 3 (`apply_update`).
- Produces: `main()` handles `--apply-update --target <path> --wait-pid <pid>` before any Qt.

- [ ] **Step 1: Add the early branch**

In `socialclip_downloader.py`, at the very top of `main()`, before the dependency checks, add the apply branch. The whole new `main()` head reads:

```python
def main():
    if "--apply-update" in sys.argv:
        from core.updater import apply_update

        argv = sys.argv
        target = None
        pid = None
        if "--target" in argv:
            target = argv[argv.index("--target") + 1]
        if "--wait-pid" in argv:
            try:
                pid = int(argv[argv.index("--wait-pid") + 1])
            except (IndexError, ValueError):
                pid = None
        if not target or pid is None:
            print("usage: --apply-update --target PATH --wait-pid PID")
            return 2
        return apply_update(target, pid)

    missing = []
```

Keep the rest of `main()` (the dependency checks onward) exactly as it is.

- [ ] **Step 2: Verify it compiles and lints**

Run: `python -m py_compile socialclip_downloader.py` then `python -m flake8 socialclip_downloader.py --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: `0`

- [ ] **Step 3: Verify the branch is reachable without Qt**

Run:

```bash
python -c "import socialclip_downloader as s; print('usage ok', s.main(['--apply-update']) if False else 'skip')"
```

Then run the real entry point with no args (must still refuse cleanly):

```bash
python socialclip_downloader.py --apply-update
```

Expected: prints `usage: --apply-update --target PATH --wait-pid PID` and exits 2, without opening a window.

- [ ] **Step 4: Run the suite**

Run: `python -m pytest -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add socialclip_downloader.py
git commit -m "feat(app): --apply-update entry point for the updater"
```

---

### Task 6: The indicator button

**Files:**
- Create: `ui/update_indicator.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `UpdateButton(QtWidgets.QToolButton)` with `set_state(state, version="", detail="")` and the standard `clicked` signal; states `"hidden"`, `"available"`, `"downloading"`, `"ready"`, `"error"`.

- [ ] **Step 1: Add the button**

Create `ui/update_indicator.py`:

```python
"""A small top-right button that shows update state and emits clicks."""

from PyQt5 import QtWidgets, QtCore, QtGui


class UpdateButton(QtWidgets.QToolButton):
    STATES = ("hidden", "available", "downloading", "ready", "error")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoRaise(True)
        self.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.setAccessibleName("Update status")
        self._state = "hidden"
        self.set_state("hidden")

    def state(self) -> str:
        return self._state

    def set_state(self, state: str, version: str = "", detail: str = ""):
        if state not in self.STATES:
            state = "hidden"
        self._state = state
        self.setVisible(state != "hidden")
        if state == "hidden":
            self.setToolTip("")
            self.setText("")
            return
        if state == "available":
            self.setText("Update")
            self.setToolTip("Update %s available" % (version or ""))
        elif state == "downloading":
            self.setText(detail or "Downloading")
            self.setToolTip("Downloading the update. Click to cancel.")
        elif state == "ready":
            self.setText("Restart")
            self.setToolTip("Update %s ready to install" % (version or ""))
        elif state == "error":
            self.setText("Retry")
            self.setToolTip(detail or "Update check failed")
```

- [ ] **Step 2: Verify it compiles and lints**

Run: `python -m py_compile ui/update_indicator.py` then `python -m flake8 ui/update_indicator.py --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: `0`

- [ ] **Step 3: Verify it constructs offscreen**

Run:

```bash
python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PyQt5 import QtWidgets; app=QtWidgets.QApplication([]); from ui.update_indicator import UpdateButton; b=UpdateButton(); b.set_state('available', version='0.10.0'); print('state', b.state(), 'visible', not b.isHidden())"
```

Expected: `state available visible True`

- [ ] **Step 4: Commit**

```bash
git add ui/update_indicator.py
git commit -m "feat(ui): update indicator button"
```

---

### Task 7: The install-ready dialog

**Files:**
- Modify: `ui/dialogs.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `show_update_ready(parent, version) -> bool` (True = install and restart).

- [ ] **Step 1: Add the dialog**

Append to `ui/dialogs.py`:

```python
def show_update_ready(parent, version: str) -> bool:
    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle("Update ready")
    box.setText(
        "SocialClip Downloader %s was downloaded and verified.\n\n"
        "Install it now and restart?" % (version or "")
    )
    install = box.addButton("Install and restart", QtWidgets.QMessageBox.AcceptRole)
    box.addButton("Later", QtWidgets.QMessageBox.RejectRole)
    box.exec_()
    return box.clickedButton() is install
```

- [ ] **Step 2: Verify it compiles and lints**

Run: `python -m py_compile ui/dialogs.py` then `python -m flake8 ui/dialogs.py --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: `0`

- [ ] **Step 3: Commit**

```bash
git add ui/dialogs.py
git commit -m "feat(ui): update-ready install dialog"
```

---

### Task 8: Wire the updater into the main window

**Files:**
- Modify: `ui/main_window.py`

**Interfaces:**
- Consumes: Task 4 (`UpdateCheckWorker`, `UpdateDownloadWorker`), Task 5 (the `--apply-update` flag), Task 6 (`UpdateButton`), Task 7 (`show_update_ready`), Task 3 (`update_temp_path`, `cleanup_update_temp`, `select_asset`).
- Produces: `MainWindow.check_for_updates(force=False)`, `MainWindow._on_update_available`, `MainWindow._start_update_download`, `MainWindow._on_update_downloaded`, `MainWindow._install_update`.

- [ ] **Step 1: Add the header row, imports, and state**

In `ui/main_window.py`, add imports:

```python
import os
import subprocess
import sys

from PyQt5 import QtWidgets, QtCore, QtGui

from ui.update_indicator import UpdateButton
from ui.dialogs import show_update_ready
from workers.update_worker import UpdateCheckWorker, UpdateDownloadWorker
from core.updater import (
    cleanup_update_temp, is_newer, select_asset, update_temp_path,
)
```

In `MainWindow.__init__`, before `self.init_ui()`, add:

```python
        self._update_release = None
        self._update_asset = None
        self._update_path = ""
        self._update_state = "idle"
        self._check_worker = None
        self._download_worker = None
        cleanup_update_temp()
```

In `init_ui`, after the menu bar is added and before the tabs, add the header row:

```python
        header = QtWidgets.QHBoxLayout()
        header.addStretch(1)
        self.update_button = UpdateButton(self)
        self.update_button.clicked.connect(self._on_update_button)
        header.addWidget(self.update_button)
        layout.addLayout(header)
```

In `_build_menubar`, add to the Help menu:

```python
        help_menu.addAction(self._action("Check for updates", lambda: self.check_for_updates(force=True)))
```

- [ ] **Step 2: Add the state machine**

Add these methods to `MainWindow`:

```python
    def check_for_updates(self, force=False):
        if not force:
            last = self.settings.value("update/last_check", "")
            if last:
                try:
                    from datetime import datetime, timedelta, timezone
                    when = datetime.fromisoformat(last)
                    if datetime.now(timezone.utc) - when < timedelta(hours=24):
                        return
                except ValueError:
                    pass
        if self._check_worker and self._check_worker.isRunning():
            return
        from socialclip_downloader import __version__
        self._check_worker = UpdateCheckWorker(__version__)
        self._check_worker.done_signal.connect(self._on_update_available)
        self._check_worker.error_signal.connect(self._on_update_error)
        self._check_worker.start()

    def _stamp_check(self):
        from datetime import datetime, timezone
        self.settings.setValue("update/last_check", datetime.now(timezone.utc).isoformat())

    def _on_update_available(self, release):
        self._stamp_check()
        if release is None:
            self.update_button.set_state("hidden")
            return
        from socialclip_downloader import __version__
        if not is_newer(release.version, __version__):
            self.update_button.set_state("hidden")
            return
        self._update_release = release
        self._update_asset = select_asset(release.assets)
        self.update_button.set_state("available", version=release.version)

    def _on_update_error(self, message):
        self._stamp_check()
        self._update_state = "error"
        self.update_button.set_state("error", detail=message)

    def _on_update_button(self):
        state = self._update_state
        if state == "available":
            self._start_update_download()
        elif state == "downloading":
            if self._download_worker:
                self._download_worker.cancel()
            self._update_state = "available"
            self.update_button.set_state("available", version=self._update_release.version)
        elif state == "ready":
            self._install_update()
        elif state == "error":
            self.check_for_updates(force=True)

    def _start_update_download(self):
        if not getattr(sys, "frozen", False) or self._update_asset is None:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(self._update_release.page_url))
            return
        self._update_path = update_temp_path(self._update_release.version)
        self._update_state = "downloading"
        self.update_button.set_state("downloading", detail="0%")
        self._download_worker = UpdateDownloadWorker(self._update_asset, self._update_path)
        self._download_worker.progress_signal.connect(
            lambda pct: self.update_button.set_state("downloading", detail="%d%%" % pct)
        )
        self._download_worker.done_signal.connect(self._on_update_downloaded)
        self._download_worker.error_signal.connect(self._on_update_error)
        self._download_worker.start()

    def _on_update_downloaded(self, path):
        self._update_state = "ready"
        self.update_button.set_state("ready", version=self._update_release.version)

    def _install_update(self):
        if not show_update_ready(self, self._update_release.version):
            return
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) if os.name == "nt" else 0
        subprocess.Popen(
            [self._update_path, "--apply-update", "--target", sys.executable,
             "--wait-pid", str(os.getpid())],
            creationflags=flags, close_fds=True,
        )
        QtWidgets.QApplication.quit()
```

- [ ] **Step 3: Kick off the startup check**

At the end of `__init__` (after `_apply_saved_theme`), add:

```python
        QtCore.QTimer.singleShot(4000, self.check_for_updates)
```

- [ ] **Step 4: Verify it compiles and lints**

Run: `python -m py_compile ui/main_window.py` then `python -m flake8 ui/main_window.py --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: `0`

- [ ] **Step 5: Verify the header and button construct offscreen**

Run:

```bash
python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PyQt5 import QtWidgets, QtCore; app=QtWidgets.QApplication([]); app.setOrganizationName('petra-dot'); app.setApplicationName('SocialClip Downloader'); QtCore.QSettings().setValue('first_run_done', True); from ui.main_window import MainWindow; w=MainWindow(); print('has button', hasattr(w,'update_button'), 'hidden', w.update_button.isHidden()); w.close()"
```

Expected: `has button True hidden True`

- [ ] **Step 6: Commit**

```bash
git add ui/main_window.py
git commit -m "feat(ui): check for updates on startup and wire the indicator"
```

---

### Task 9: Documentation

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `AGENTS.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing code-facing.

- [ ] **Step 1: README**

Add a short "Updates" note: the app checks GitHub for a newer release at most once a day, shows an indicator in the top right, and on Windows downloads, verifies, and installs it with a restart. macOS/Linux and source runs open the release page.

- [ ] **Step 2: CHANGELOG**

Under `## Unreleased`, add `### Added` for the in-app updater, naming the Windows self-update and the digest verification.

- [ ] **Step 3: AGENTS.md**

Add `core/updater.py`, `workers/update_worker.py`, `ui/update_indicator.py` to the layout list, and a one-line note: the updater checks GitHub Releases, verifies the asset SHA-256, and self-applies on Windows via `--apply-update`.

- [ ] **Step 4: Commit**

```bash
git add README.md CHANGELOG.md AGENTS.md
git commit -m "docs: in-app updater"
```

---

## Self-Review

- **Spec coverage:** helpers (Task 1), fetch/download/verify (Task 2), apply/fallback/cleanup (Task 3), workers (Task 4), `--apply-update` (Task 5), indicator (Task 6), dialog (Task 7), state machine + header + menu (Task 8), docs (Task 9). The digest check is Task 2 (helper) and Task 4 (used before `done`); the host allow-list is Task 2; the daily cache is Task 8; source-run and non-Windows notify is Task 8.
- **Placeholder scan:** no TBD/TODO; every code step carries real code. Task 5 Step 1 shows a two-part edit; use the second block as the final body.
- **Type consistency:** `ReleaseInfo`/`AssetInfo` fields match across Tasks 1, 2, 4, 6, 8; `UpdateCheckWorker(current_version)` and `UpdateDownloadWorker(asset, dest)` match Task 8; `select_asset(assets, platform=None)` matches; `update_temp_path(version)` matches.
