# Browser Extension Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Chrome, Edge and Firefox hand a URL to the app through a native-messaging host: right-click to add to the Queue or download now with a format picker, and scan a page for supported links.

**Architecture:** A headless `--native-host` mode in the existing exe speaks the browser's length-prefixed JSON protocol on the raw OS handles, writes jobs into `queue.json` through the existing Qt-free queue code, and optionally launches the GUI with `--run-queue`. The GUI gains a single-instance guard so a second launch forwards to the first instead of becoming a second writer. The extension is one MV3 payload with two manifests.

**Tech Stack:** Python 3.8+ stdlib, PyQt5 (QLocalServer/QLocalSocket, QSettings), existing `core/` modules, plain JavaScript MV3 extension, `winreg` for HKCU registration.

**Spec:** `docs/specs/2026-11-07-browser-extension-design.md`

## Global Constraints

- `core/` stays Qt-free and thread-free (`tests/test_core_isolation.py` enforces the first).
- No new dependency in `requirements.txt`.
- Never commit a real social-media URL; tests use `https://youtu.be/x` style placeholders only.
- Never run network or file-heavy work on the GUI thread.
- Format choices are exactly `MP4` and `MP3` plus the values of `utils.file_utils.RESOLUTIONS` (`720`, `1080`, `1440`, `2160`). `core/formats.py` is the converter registry and is not used here.
- Native host name is `com.petra_dot.socialclip`. Firefox add-on id is `socialclip@petra-dot`.
- Protocol version is `1`; scanner cap is `200` links.
- Conventional Commits. Do not push.

## Review Focus

These are the input classes the spec implies but no happy-path test would catch. Each gets a test in the task that owns the code.

1. **A host write while the GUI is running.** A running GUI holds the queue in memory and saves it back; a job added underneath it must survive (`Task 3`).
2. **A corrupt or future-version `queue.json`.** The host must refuse and report, never overwrite the user's queue with an empty one (`Task 2`).
3. **Anything on stdout other than protocol bytes.** A stray print corrupts the message and the browser reports a failure with no detail (`Task 7`).
4. **The same link with a tracking query string.** `?s=fb_shorts_profile&stack_idx=0` must still count as already queued (`Task 4`).
5. **A Firefox manifest carrying Chromium fields.** `allowed_origins` in a Firefox manifest makes the host unloadable (`Task 6`).

---

### Task 1: Move `build_job_options` into `core/`

The host must build the same option dict as the Queue tab without importing Qt widgets.

**Files:**
- Modify: `core/queue.py` (add the function beside `resolve_outtmpl`, line ~44)
- Modify: `ui/batch_tab.py:33-46` (delete the local definition, import it instead)
- Test: `tests/test_job_options.py` (create)

**Interfaces:**
- Consumes: `utils.file_utils.OUTPUT_TEMPLATE`, `utils.file_utils.default_download_folder`
- Produces: `core.queue.build_job_options(save_dir: str, output_text: str, resolution: str, cookies_path: str, subtitles: str = "off", cookies_from_browser: str = "") -> dict` returning exactly the keys `outtmpl`, `output_type`, `convert`, `target_resolution`, `cookies_file`, `subtitles`, `cookies_from_browser`

- [ ] **Step 1: Write the failing test**

```python
import os
import pytest
from core.queue import build_job_options
from utils.file_utils import OUTPUT_TEMPLATE


def test_mp4_options_match_the_queue_tab_contract():
    opts = build_job_options("/out", "Video (MP4)", "1080", "", "sidecar", "chrome")
    assert opts == {
        "outtmpl": os.path.join("/out", OUTPUT_TEMPLATE),
        "output_type": "MP4",
        "convert": True,
        "target_resolution": 1080,
        "cookies_file": "",
        "subtitles": "sidecar",
        "cookies_from_browser": "chrome",
    }


@pytest.mark.parametrize("label", ["Audio (MP3)", "MP3"])
def test_mp3_label_sets_audio_without_convert(label):
    opts = build_job_options("/out", label, "720", "c.txt", "off", "")
    assert opts["output_type"] == "MP3"
    assert opts["convert"] is False
    assert opts["target_resolution"] == 720
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_job_options.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_job_options' from 'core.queue'`

- [ ] **Step 3: Move the function**

Move the body from `ui/batch_tab.py:33-46` into `core/queue.py` unchanged, and in `ui/batch_tab.py` replace it with `from core.queue import build_job_options  # noqa: F401 - re-exported for callers`. The name must stay importable from `ui.batch_tab`, because `QueueTab._job_options` and `QueueTab.on_edit_job` call it.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_job_options.py tests/test_batch_tab_model.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/queue.py ui/batch_tab.py tests/test_job_options.py
git commit -m "refactor(queue): move build_job_options into core so the host can use it"
```

---

### Task 2: Strict queue load for the headless host

**Files:**
- Modify: `core/queue.py` (`QueueStore`, after `load`, line ~104)
- Test: `tests/test_queue.py` (append)

**Interfaces:**
- Consumes: `QueueStore.load`
- Produces: `core.queue.QueueFileError(Exception)`; `QueueStore.load_strict() -> None` raising `QueueFileError` when the file exists but is unreadable, not a dict, or carries a version other than `STORE_VERSION`

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from core.queue import QueueFileError, QueueStore


def test_strict_load_accepts_a_missing_file(tmp_path):
    store = QueueStore(str(tmp_path / "queue.json"))
    store.load_strict()
    assert store.jobs == []


def test_strict_load_raises_on_corrupt_json(tmp_path):
    path = tmp_path / "queue.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(QueueFileError):
        QueueStore(str(path)).load_strict()


def test_strict_load_raises_on_unknown_version(tmp_path):
    path = tmp_path / "queue.json"
    path.write_text('{"version": 99, "jobs": []}', encoding="utf-8")
    with pytest.raises(QueueFileError):
        QueueStore(str(path)).load_strict()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_queue.py -v -k strict`
Expected: FAIL with `ImportError: cannot import name 'QueueFileError'`

- [ ] **Step 3: Implement**

Add the exception class above `QueueStore`, and the method after `load`. Missing file is not an error:

```python
class QueueFileError(Exception):
    """The queue file exists but cannot be trusted; do not write over it."""
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_queue.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/queue.py tests/test_queue.py
git commit -m "feat(queue): add strict load that refuses an untrusted queue file"
```

---

### Task 3: Merge on save so a second writer cannot lose jobs

**Files:**
- Modify: `core/queue.py` (`QueueStore.__init__`, `load`, `save`)
- Test: `tests/test_queue.py` (append)

**Interfaces:**
- Consumes: `QueueStore.save`, `_coerce_jobs`
- Produces: `QueueStore.save()` unchanged signature; new private `_stamp` attribute and `_merge_from_disk()`; on save, any job present on disk whose `id` this instance does not know is appended before writing

- [ ] **Step 1: Write the failing test**

```python
def test_save_keeps_a_job_written_by_another_writer(tmp_path):
    path = str(tmp_path / "queue.json")
    first = QueueStore(path)
    first.load()
    Queue(first).add("https://youtu.be/x")
    first.save()

    second = QueueStore(path)
    second.load()
    Queue(second).add("https://youtu.be/y")

    Queue(first).add("https://youtu.be/z")
    first.save()
    second.save()  # stale copy; must not drop x and z

    final = QueueStore(path)
    final.load()
    assert sorted(j.url for j in final.jobs) == [
        "https://youtu.be/x", "https://youtu.be/y", "https://youtu.be/z",
    ]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_queue.py -v -k another_writer`
Expected: FAIL, only two urls present

- [ ] **Step 3: Implement**

Set `self._stamp = None` in `__init__`. After a successful read in `load`, and after `os.replace` in `save`, record `self._stamp = (st.st_mtime_ns, st.st_size)`. At the start of `save`, when `self.path` and `self._stamp` are set and the current stamp differs, read the file; if it parses at `STORE_VERSION`, append every disk job whose `id` is not already in `self.jobs`, keeping this instance's copy when ids collide. A file that fails to parse is left alone: keep the in-memory jobs and write them.

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_queue.py tests/test_cli_queue.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/queue.py tests/test_queue.py
git commit -m "fix(queue): merge on save so a second writer cannot drop jobs"
```

---

### Task 4: Protocol framing, URL normalization, duplicate lookup

**Files:**
- Create: `core/native.py`
- Test: `tests/test_native.py` (create)

**Interfaces:**
- Produces: `HOST_NAME = "com.petra_dot.socialclip"`, `PROTOCOL_VERSION = 1`, `MAX_SCAN_LINKS = 200`, `class ProtocolError(Exception)`; `encode_message(payload: dict) -> bytes`; `read_message(stream) -> dict`; `normalize_url(url: str) -> str`; `already_known(urls, jobs, entries) -> dict` with keys `in_queue` and `in_history`, each a list of the original URL strings in input order

- [ ] **Step 1: Write the failing tests**

```python
import io
import pytest
from core.native import ProtocolError, already_known, encode_message, normalize_url, read_message
from core.queue import QueueJob


def test_message_round_trip_preserves_the_payload():
    payload = {"cmd": "ping", "urls": ["https://youtu.be/x"]}
    assert read_message(io.BytesIO(encode_message(payload))) == payload


def test_read_message_rejects_a_short_body():
    frame = encode_message({"cmd": "ping"})
    with pytest.raises(ProtocolError):
        read_message(io.BytesIO(frame[: len(frame) - 2]))


def test_normalize_url_drops_tracking_query_and_trailing_slash():
    assert normalize_url("https://WWW.Facebook.com/reel/123/?s=f&stack_idx=0") == \
        "https://www.facebook.com/reel/123"
    assert normalize_url("not a url") == ""


def test_already_known_matches_across_query_strings():
    jobs = [QueueJob(url="https://youtu.be/x?t=10", state="pending")]
    found = already_known(["https://youtu.be/x"], jobs, [])
    assert found == {"in_queue": ["https://youtu.be/x"], "in_history": []}
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_native.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.native'`

- [ ] **Step 3: Implement**

`encode_message` is `struct.pack("<I", len(body)) + body` with `body = json.dumps(payload).encode("utf-8")`. `read_message` reads exactly 4 bytes, unpacks the length, reads that many bytes, and raises `ProtocolError` on a short frame or bad JSON.

`normalize_url` returns `""` for anything without an `http`/`https` scheme and host. Otherwise it lowercases the scheme and host, keeps the path with any trailing `/` removed, and drops query and fragment.

`already_known` uses `normalize_url` on both sides. A job counts as **in queue** only when its `state` is `pending`, `running` or `paused`; done, failed and cancelled jobs fall to the history check, which compares against `HistoryEntry.url`.

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_native.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/native.py tests/test_native.py
git commit -m "feat(native): add native-messaging framing and duplicate lookup"
```

---

### Task 5: Host command dispatch

**Files:**
- Modify: `core/native.py`
- Test: `tests/test_native.py` (append)

**Interfaces:**
- Consumes: `core.queue.Queue`, `core.queue.build_job_options`, `core.history.HistoryStore`, `sites.cookies.PLATFORM_PATTERNS`, `sites.cookies.PLATFORM_NAMES`, `utils.file_utils.RESOLUTIONS`, `core.version.__version__`
- Produces: `supported_sites() -> list[dict]` with keys `pattern`, `platform`, `name`; `download_choices() -> dict` with `outputs` (`["MP4", "MP3"]`) and `resolutions`; `handle_message(msg: dict, store, history, options: dict) -> dict`, always returning a dict with `ok: bool`, and `error: str` when `ok` is false

- [ ] **Step 1: Write the failing tests**

```python
from core.history import HistoryEntry, HistoryStore
from core.native import handle_message, supported_sites
from core.queue import QueueStore


def _store(tmp_path):
    store = QueueStore(str(tmp_path / "queue.json"))
    store.load_strict()
    return store


def test_ping_reports_the_protocol_version(tmp_path):
    reply = handle_message({"cmd": "ping"}, _store(tmp_path), HistoryStore(str(tmp_path / "h.json")), {})
    assert reply["ok"] is True
    assert reply["protocol"] == 1
    assert reply["version"]


def test_sites_come_from_the_app_registry():
    sites = supported_sites()
    assert {s["platform"] for s in sites} >= {"youtube", "facebook", "tiktok"}
    assert all(s["name"] and s["pattern"] for s in sites)


def test_add_writes_jobs_with_the_given_options(tmp_path):
    store = _store(tmp_path)
    reply = handle_message(
        {"cmd": "add", "urls": ["https://youtu.be/x"], "start": False},
        store, HistoryStore(str(tmp_path / "h.json")), {"output_type": "MP3"},
    )
    assert reply == {"ok": True, "added": 1}
    reloaded = QueueStore(store.path)
    reloaded.load_strict()
    assert reloaded.jobs[0].options == {"output_type": "MP3"}


def test_check_separates_queue_from_history(tmp_path):
    store = _store(tmp_path)
    store.jobs.append(__import__("core.queue", fromlist=["QueueJob"]).QueueJob(
        url="https://youtu.be/x", state="pending"))
    history = HistoryStore(str(tmp_path / "h.json"))
    history.add(HistoryEntry(id="1", title="t", url="https://youtu.be/y"))
    reply = handle_message(
        {"cmd": "check", "urls": ["https://youtu.be/x", "https://youtu.be/y"]},
        store, history, {})
    assert reply["in_queue"] == ["https://youtu.be/x"]
    assert reply["in_history"] == ["https://youtu.be/y"]


def test_unknown_command_fails_cleanly(tmp_path):
    reply = handle_message({"cmd": "nope"}, _store(tmp_path), HistoryStore(str(tmp_path / "h.json")), {})
    assert reply == {"ok": False, "error": "unknown command"}
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_native.py -v -k "ping or sites or add or check or unknown"`
Expected: FAIL with `ImportError: cannot import name 'handle_message'`

- [ ] **Step 3: Implement**

`handle_message` dispatches `ping`, `sites`, `formats`, `check`, `add`, and returns the unknown-command dict otherwise. `add` uses `Queue(store).add_many(urls, options)` then `store.save()`. Missing or non-list `urls` returns `{"ok": False, "error": "urls must be a list"}`. Do not filter duplicates here: consent already came from the popup.

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_native.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/native.py tests/test_native.py
git commit -m "feat(native): dispatch ping, sites, formats, check and add"
```

---

### Task 6: Host manifests and registration

**Files:**
- Create: `core/native_install.py`
- Test: `tests/test_native_install.py` (create)

**Interfaces:**
- Consumes: `core.native.HOST_NAME`, `core.paths.data_dir`
- Produces: `CHROMIUM_REGISTRY_PATHS = (r"Software\\Google\\Chrome\\NativeMessagingHosts", r"Software\\Microsoft\\Edge\\NativeMessagingHosts")`; `FIREFOX_REGISTRY_PATH = r"Software\\Mozilla\\NativeMessagingHosts"`; `host_manifest(executable: str, extension_id: str, firefox: bool = False) -> dict`; `manifest_path(data: str = None) -> str`; `wrapper_script(entry: str) -> tuple[str, str]` returning `(path, content)`; `install(executable: str, extension_id: str, frozen: bool = True) -> list[str]` returning the registry paths it wrote

- [ ] **Step 1: Write the failing tests**

```python
from core.native import HOST_NAME
from core.native_install import host_manifest


def test_chromium_manifest_allows_the_extension_origin():
    m = host_manifest("C:/app.exe", "abc123")
    assert m["name"] == HOST_NAME
    assert m["type"] == "stdio"
    assert m["path"] == "C:/app.exe"
    assert m["allowed_origins"] == ["chrome-extension://abc123/"]
    assert "allowed_extensions" not in m


def test_firefox_manifest_uses_the_addon_id_and_no_origins():
    m = host_manifest("/app", "socialclip@petra-dot", firefox=True)
    assert m["allowed_extensions"] == ["socialclip@petra-dot"]
    assert "allowed_origins" not in m
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_native_install.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`host_manifest` builds the dict above, plus `"description": "SocialClip Downloader native host"`. `manifest_path` is `os.path.join(data_dir(), HOST_NAME + ".json")`.

`wrapper_script` returns `<data_dir>/native-host.cmd` containing `@"<sys.executable>" "<repo>/socialclip_downloader.py" --native-host %*` on Windows, and a `native-host.sh` with the same idea elsewhere. It exists because a manifest pointing at `python.exe` cannot pass `--native-host`, so a source checkout cannot register the interpreter directly.

`install` writes the wrapper when `frozen` is false and points the manifest at the wrapper instead of `executable`. It then writes the manifest, then for each Chromium registry path creates the `HKCU` key `<path>\<HOST_NAME>` with the default value set to the manifest path, and for Firefox creates `HKCU` `<FIREFOX_REGISTRY_PATH>\<HOST_NAME>` with the same default value. Non-Windows platforms return an empty list and write only the manifest, with a printed note.

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_native_install.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/native_install.py tests/test_native_install.py
git commit -m "feat(native): build host manifests and register them per browser"
```

---

### Task 7: Raw stdio and the `--native-host` entry flag

**Files:**
- Create: `core/native_io.py`
- Modify: `socialclip_downloader.py` (`main`, before the dependency checks)
- Test: `tests/test_native_entry.py` (create)

**Interfaces:**
- Produces: `core.native_io.stdin_stream()` and `core.native_io.stdout_stream()` returning binary file objects on the inherited OS handles; `socialclip_downloader.run_native_host() -> int`

- [ ] **Step 1: Write the failing test**

```python
import json
import os
import struct
import subprocess
import sys


def test_native_host_answers_ping_on_a_clean_stdout(tmp_path):
    body = json.dumps({"cmd": "ping"}).encode("utf-8")
    env = dict(os.environ, SOCIALCLIP_DATA=str(tmp_path))
    proc = subprocess.run(
        [sys.executable, "socialclip_downloader.py", "--native-host"],
        input=struct.pack("<I", len(body)) + body,
        capture_output=True, env=env, timeout=120,
    )
    assert proc.returncode == 0
    length = struct.unpack("<I", proc.stdout[:4])[0]
    reply = json.loads(proc.stdout[4:4 + length])
    assert reply["ok"] is True
    assert reply["protocol"] == 1
    assert proc.stdout[4 + length:] == b""
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_native_entry.py -v`
Expected: FAIL, the process starts the GUI or exits non-zero

- [ ] **Step 3: Implement**

`core/native_io.py` uses `ctypes.windll.kernel32.GetStdHandle(-10 / -11)` and `msvcrt.open_osfhandle(handle, os.O_RDONLY)` for stdin (mode `0` for stdout), then `os.fdopen(fd, "rb"/"wb", 0)`. That is the whole reason this module exists: a windowed build gives `sys.stdin`/`sys.stdout` as `None`. On non-Windows, return `sys.stdin.buffer` / `sys.stdout.buffer`.

In `socialclip_downloader.main`, handle `--native-host` and `--install-native-host` before `load()` and the dependency checks. `run_native_host()` reads one message, builds options from `QSettings("petra-dot", "SocialClip Downloader")` keys `batch/save_dir`, `batch/cookies` and `cookies/browser` with `build_job_options(..., subtitles="off")`, calls `handle_message`, writes the reply, and returns `0`. When the message asked to start, spawn the GUI detached with `--run-queue` and return without waiting.

**Nothing else may print in this path.** The reply is the only thing on stdout.

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_native_entry.py tests/test_native.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/native_io.py socialclip_downloader.py tests/test_native_entry.py
git commit -m "feat(native): add headless --native-host stdio mode"
```

---

### Task 8: Single instance, `--run-queue`, and the menu item

**Files:**
- Create: `ui/ipc.py`
- Modify: `socialclip_downloader.py` (after the update flag, before `MainWindow`)
- Modify: `ui/main_window.py:78-140` (`start_background_work`, File menu)
- Modify: `ui/batch_tab.py:790` (`on_start_queue` -> `start_queue(confirm=True)`)
- Test: `tests/verify_ui_offscreen.py` (append checks)

**Interfaces:**
- Produces: `ui.ipc.SERVER_NAME = "socialclip-" + getpass.getuser()`; `ui.ipc.send_to_primary(payload: dict, timeout_ms: int = 400) -> bool`; `ui.ipc.IpcServer(parent=None)` with `json_received = pyqtSignal(dict)`, `listen() -> bool`, and `close()`
- Produces: `QueueTab.start_queue(confirm: bool = True)`; `on_start_queue` becomes a thin slot calling it

- [ ] **Step 1: Write the failing check**

Add to `tests/verify_ui_offscreen.py`:

```python
from ui.ipc import IpcServer

srv = IpcServer()
ok("ipc: second instance is refused", not (srv.listen() and IpcServer().listen()))
srv.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -u tests/verify_ui_offscreen.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'ui.ipc'`

- [ ] **Step 3: Implement**

`ui/ipc.py`: `IpcServer.listen()` returns `QLocalServer.listen(SERVER_NAME)`; on `newConnection` it reads one length-prefixed JSON blob and emits `json_received`. `send_to_primary` connects, writes the framed payload, and returns whether it succeeded.

`socialclip_downloader.main`: after the ffmpeg warning and before `MainWindow()`, compute `run_queue = "--run-queue" in sys.argv`; if `send_to_primary({"action": "run" if run_queue else "show"})` returns `True`, return `0`. Otherwise create the window, start the IPC server, and connect `json_received` to a handler that raises the window, reloads the queue (`batch_tab.queue.store.load()`), refreshes the table, and calls `batch_tab.start_queue(confirm=False)` when the action is `run`. If a `--run-queue` launch became primary, switch to the Queue tab and call `start_queue(confirm=False)` after `start_background_work()`.

`QueueTab.start_queue(confirm=True)` is `on_start_queue` with the stale-options `QMessageBox` guarded by `if confirm:`, so an extension-driven start never blocks on a modal dialog.

Add a File menu action **Install browser extension host** that runs `native_install.install(sys.executable, extension_id)` inside a `QInputDialog` for the extension id, and reports the written paths in a message box.

- [ ] **Step 4: Run**

Run: `python -u tests/verify_ui_offscreen.py`
Expected: `ALL CHECKS PASSED`

- [ ] **Step 5: Commit**

```bash
git add ui/ipc.py socialclip_downloader.py ui/main_window.py ui/batch_tab.py tests/verify_ui_offscreen.py
git commit -m "feat(ui): single-instance guard, --run-queue, and host install menu"
```

---

### Task 9: Chromium extension

**Files:**
- Create: `extension/manifest.chromium.json`
- Create: `extension/background.js`
- Create: `extension/popup.html`, `extension/popup.js`, `extension/popup.css`
- Test: manual load, plus the manifest assertions in Task 10

**Interfaces:**
- Consumes: host commands `ping`, `sites`, `formats`, `check`, `add` from Tasks 4 and 5

- [ ] **Step 1: Write the manifest**

```json
{
  "manifest_version": 3,
  "name": "SocialClip Downloader",
  "version": "0.1.0",
  "description": "Send links to SocialClip Downloader.",
  "permissions": ["contextMenus", "nativeMessaging", "activeTab", "scripting", "storage"],
  "background": {"service_worker": "background.js"},
  "action": {"default_popup": "popup.html", "default_title": "SocialClip"}
}
```

- [ ] **Step 2: Write `background.js`**

Two context-menu entries on `link`, `video`, `audio` and `page` contexts, created in `onInstalled`. On click, resolve the URL as `info.linkUrl || info.srcUrl || info.pageUrl`, then:

1. `sendNativeMessage(HOST_NAME, {cmd: "ping"})`. On failure, show the action badge `!` and stop.
2. `{cmd: "check", urls: [url]}`.
3. If either list is non-empty, open the popup (`chrome.action.openPopup()`, falling back to a notification-free badge) with the URL and reason stored in `chrome.storage.session`. Otherwise send `{cmd: "add", urls: [url], start: <menu was Download now>}`.

Use `globalThis.browser ?? globalThis.chrome` so the same file runs on Firefox.

- [ ] **Step 3: Write the popup**

On open: read `check`/`formats` from `chrome.storage.local`, paint immediately, then refresh from the host. Render an output select (`MP4`, `MP3`), a resolution select, an optional "already in queue / already in history" warning block with **Add anyway** and **Cancel**, and a **Scan page** button that runs `chrome.scripting.executeScript` collecting `document.links`, filters by the cached `sites` patterns with `new RegExp("^(?:" + pattern + ")$")` against the hostname, de-duplicates by normalized URL, caps at 200, and shows tick boxes.

**Add** sends `{cmd: "add", urls: <ticked>, options: <chosen>, start: false}`; **Download now** sends `start: true`.

- [ ] **Step 4: Manual check**

Load unpacked from `extension/`, right-click a link, confirm the popup or the add, and confirm the job appears in the app.

- [ ] **Step 5: Commit**

```bash
git add extension
git commit -m "feat(extension): chromium extension with context menu and page scan"
```

---

### Task 10: Firefox manifest variant

**Files:**
- Create: `extension/manifest.firefox.json`
- Test: `tests/test_extension_manifests.py` (create)

**Interfaces:**
- Consumes: nothing new; shares `background.js` and the popup

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path

EXT = Path(__file__).resolve().parent.parent / "extension"


def test_firefox_manifest_has_an_addon_id_and_no_service_worker():
    m = json.loads((EXT / "manifest.firefox.json").read_text(encoding="utf-8"))
    assert m["browser_specific_settings"]["gecko"]["id"] == "socialclip@petra-dot"
    assert "service_worker" not in m["background"]
    assert m["background"]["scripts"] == ["background.js"]


def test_chromium_manifest_uses_a_service_worker():
    m = json.loads((EXT / "manifest.chromium.json").read_text(encoding="utf-8"))
    assert m["background"]["service_worker"] == "background.js"
    assert "browser_specific_settings" not in m
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_extension_manifests.py -v`
Expected: FAIL, file missing

- [ ] **Step 3: Write the Firefox manifest**

Same permissions and popup as Chromium, but `"background": {"scripts": ["background.js"]}` and `"browser_specific_settings": {"gecko": {"id": "socialclip@petra-dot", "strict_min_version": "115.0"}}`. No `allowed_origins` anywhere.

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_extension_manifests.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add extension/manifest.firefox.json tests/test_extension_manifests.py
git commit -m "feat(extension): firefox manifest variant"
```

---

### Task 11: Docs and full verification

**Files:**
- Modify: `README.md` (new "Browser extension" section)
- Modify: `AGENTS.md` (layout section: `core/native*.py`, `ui/ipc.py`, `extension/`)

- [ ] **Step 1: Document the install path**

README: load unpacked in Chrome/Edge, copy the extension id, run `python socialclip_downloader.py --install-native-host --extension-id <id>`, and for Firefox set the add-on id `socialclip@petra-dot`. State that a permanent Firefox install needs AMO signing and that Chromium needs developer mode.

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass, count higher than 647

- [ ] **Step 3: Lint**

Run: `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: `0`

- [ ] **Step 4: Offscreen UI**

Run: `python -u tests/verify_ui_offscreen.py`
Expected: `ALL CHECKS PASSED`

- [ ] **Step 5: Commit**

```bash
git add README.md AGENTS.md
git commit -m "docs: browser extension setup and new modules"
```

---

## Manual acceptance run

1. `python socialclip_downloader.py --install-native-host --extension-id <id>`
2. Load `extension/` unpacked, right-click a supported link, **Add to SocialClip Queue**. The job appears in the Queue tab.
3. Right-click another link, **Download now**, pick MP3, confirm. The app comes forward on the Queue tab with the job running.
4. Open a channel page, **Scan page**, confirm the supported links are listed, tick two, add.
5. Right-click a link already in the queue: the popup warns and offers **Add anyway**.
