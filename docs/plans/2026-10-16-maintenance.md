# Maintenance and Self-Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep a frozen build working without a new release: check the app's components, repair missing/stale/broken ones from verified downloads into a per-user data directory, and give the user a Health view that repairs by hand.

**Architecture:** Two new Qt-free modules (`core/paths.py` for the writable data directory and migration, `core/maintenance.py` for the component model, checks, and installers), one new Qt worker, and the existing Doctor dialog grown into a Health view. `utils/ytdlp.load()` puts a managed yt-dlp on `sys.path` before anything imports `yt_dlp`.

**Tech Stack:** Python 3.8+, PyQt5, stdlib only (`urllib`, `zipfile`, `hashlib`, `json`, `os`, `shutil`, `sys`).

**Spec:** `docs/specs/2026-10-16-maintenance-design.md`

## Global Constraints

- `core/` is **Qt-free** by rule; `tests/test_core_isolation.py` enforces it. `core/paths.py` and `core/maintenance.py` must not import PyQt5/PySide.
- **Never commit a real social-media URL.** Tests and docs use placeholders only (`https://youtu.be/x`, `https://a.com/1`).
- **Conventional Commits.** Commit per task; never commit to `main`; never push without an explicit yes.
- **No new runtime dependency.** stdlib only.
- Every download is **HTTPS**, host allow-listed (`github.com`, `api.github.com`, `objects.githubusercontent.com`, `release-assets.githubusercontent.com`), and **SHA-256 verified** before use.
- **Never delete a working component** before its replacement is verified.
- `SOCIALCLIP_DATA` overrides the data directory. `SOCIALCLIP_QUEUE` keeps overriding the queue file only. `SOCIALCLIP_FFMPEG`/`FFMPEG_LOCATION` keep overriding ffmpeg.
- Python 3.8 compatible: no `match`, no `X | Y` type unions, no `list[str]` in runtime annotations that get evaluated. Use `typing.List`/`Optional` where a module evaluates annotations.

---

### Task 1: `core/paths.py` - data directory and migration

**Files:**
- Create: `core/paths.py`
- Test: `tests/test_paths.py`

**Interfaces:**
- Produces: `DATA_ENV = "SOCIALCLIP_DATA"`, `APP_DIR_NAME = "SocialClip Downloader"`, `legacy_dir() -> str`, `default_data_dir() -> str`, `data_dir() -> str`, `data_dir_writable() -> bool`, `managed_dir(kind) -> str`, `migrate_legacy_files() -> list`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paths.py
import os
import sys

import pytest

from core import paths


def test_data_dir_honours_env(tmp_path, monkeypatch):
    target = tmp_path / "custom"
    monkeypatch.setenv("SOCIALCLIP_DATA", str(target))
    assert paths.data_dir() == str(target)
    assert os.path.isdir(str(target))


def test_data_dir_default_windows(tmp_path, monkeypatch):
    monkeypatch.delenv("SOCIALCLIP_DATA", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "win32")
    assert paths.default_data_dir() == os.path.join(
        str(tmp_path), paths.APP_DIR_NAME
    )


def test_data_dir_default_linux(tmp_path, monkeypatch):
    monkeypatch.delenv("SOCIALCLIP_DATA", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "linux")
    assert paths.default_data_dir() == os.path.join(str(tmp_path), "socialclip")


def test_managed_dir_kinds(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    assert paths.managed_dir("yt-dlp") == os.path.join(str(tmp_path), "yt-dlp")
    assert paths.managed_dir("bin") == os.path.join(str(tmp_path), "bin")


def test_migrate_copies_and_keeps_originals(tmp_path, monkeypatch):
    legacy = tmp_path / "app"
    data = tmp_path / "data"
    legacy.mkdir()
    (legacy / "queue.json").write_text("[]", encoding="utf-8")
    (legacy / "youtube_cookies.txt").write_text("# Netscape", encoding="utf-8")
    monkeypatch.setattr(paths, "legacy_dir", lambda: str(legacy))
    monkeypatch.setenv("SOCIALCLIP_DATA", str(data))

    copied = paths.migrate_legacy_files()

    assert sorted(copied) == ["queue.json", "youtube_cookies.txt"]
    assert (data / "queue.json").read_text(encoding="utf-8") == "[]"
    assert (legacy / "queue.json").is_file()  # original kept


def test_migrate_never_overwrites(tmp_path, monkeypatch):
    legacy = tmp_path / "app"
    data = tmp_path / "data"
    legacy.mkdir()
    data.mkdir()
    (legacy / "queue.json").write_text("legacy", encoding="utf-8")
    (data / "queue.json").write_text("current", encoding="utf-8")
    monkeypatch.setattr(paths, "legacy_dir", lambda: str(legacy))
    monkeypatch.setenv("SOCIALCLIP_DATA", str(data))

    copied = paths.migrate_legacy_files()

    assert copied == []
    assert (data / "queue.json").read_text(encoding="utf-8") == "current"


def test_migrate_skips_when_same_dir(tmp_path, monkeypatch):
    legacy = tmp_path / "app"
    legacy.mkdir()
    (legacy / "queue.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(paths, "legacy_dir", lambda: str(legacy))
    monkeypatch.setenv("SOCIALCLIP_DATA", str(legacy))
    assert paths.migrate_legacy_files() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_paths.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.paths'`

- [ ] **Step 3: Write minimal implementation**

```python
# core/paths.py
"""Where the app keeps writable state: a per-user data directory.

Next to the executable is read-only in several real installs (a macOS app run
from a quarantined download, a Linux binary in /usr/local/bin, anything under
Program Files), so cookies and the queue could silently fail to save. This
module resolves one writable directory and copies any legacy files into it once.

Qt-free: the CLI uses it too.
"""

import os
import sys

DATA_ENV = "SOCIALCLIP_DATA"
APP_DIR_NAME = "SocialClip Downloader"

# State that used to live next to the app and must survive the move.
LEGACY_FILES = ("queue.json", "presets.json", "archive.txt")


def legacy_dir() -> str:
    """The directory state lived in before this module: the app directory."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_data_dir() -> str:
    """The platform's per-user data directory for this app."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_DIR_NAME)
    if sys.platform == "darwin":
        return os.path.join(
            os.path.expanduser("~"), "Library", "Application Support", APP_DIR_NAME
        )
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    return os.path.join(base, "socialclip")


def data_dir() -> str:
    """The writable data directory, created on demand.

    Falls back to the app directory when the per-user directory cannot be
    created, so the app still runs.
    """
    target = os.environ.get(DATA_ENV) or default_data_dir()
    try:
        os.makedirs(target, exist_ok=True)
    except OSError:
        return legacy_dir()
    return target


def data_dir_writable() -> bool:
    """True when a file can be created in the data directory."""
    try:
        probe = os.path.join(data_dir(), ".write-test")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("")
        os.remove(probe)
        return True
    except OSError:
        return False


def managed_dir(kind: str) -> str:
    """A subdirectory for a managed component: "yt-dlp" or "bin"."""
    return os.path.join(data_dir(), kind)


def _legacy_names(directory: str) -> list:
    names = list(LEGACY_FILES)
    try:
        for fname in os.listdir(directory):
            if fname.lower().endswith("_cookies.txt"):
                names.append(fname)
    except OSError:
        pass
    return names


def migrate_legacy_files() -> list:
    """Copy legacy app-dir state into the data dir. Returns the names copied.

    Copies only, never moves or deletes, and never overwrites: a file already in
    the data directory is the current one.
    """
    source = legacy_dir()
    target = data_dir()
    if os.path.abspath(source) == os.path.abspath(target):
        return []
    copied = []
    for name in _legacy_names(source):
        src = os.path.join(source, name)
        dst = os.path.join(target, name)
        if not os.path.isfile(src) or os.path.exists(dst):
            continue
        try:
            with open(src, "rb") as fh:
                data = fh.read()
            with open(dst, "wb") as fh:
                fh.write(data)
        except OSError:
            continue
        copied.append(name)
    return copied
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_paths.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add core/paths.py tests/test_paths.py
git commit -m "feat: resolve a per-user data directory and migrate legacy files"
```

---

### Task 2: Move state to the data directory

**Files:**
- Modify: `sites/cookies.py:51-58` (`default_cookie_dir`)
- Modify: `cli.py` (`_queue_path`, `_presets_path`, `_archive_path`)
- Modify: `socialclip_downloader.py` (`main`, call `migrate_legacy_files()`)
- Modify: `cli.py` (`main`, call `migrate_legacy_files()`)
- Test: `tests/test_paths.py` (append), `tests/test_cli_queue.py` (append)

**Interfaces:**
- Consumes: `core.paths.data_dir()`, `core.paths.migrate_legacy_files()`
- Produces: `sites.cookies.default_cookie_dir()` now returns `core.paths.data_dir()`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paths.py  (append)

def test_default_cookie_dir_is_the_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    from sites.cookies import default_cookie_dir
    assert default_cookie_dir() == str(tmp_path)


def test_queue_path_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
    override = tmp_path / "elsewhere" / "q.json"
    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(override))
    import cli
    assert cli._queue_path() == str(override)


def test_queue_path_defaults_into_data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("SOCIALCLIP_QUEUE", raising=False)
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
    import cli
    assert cli._queue_path() == str(tmp_path / "data" / "queue.json")


def test_presets_and_archive_follow_data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("SOCIALCLIP_QUEUE", raising=False)
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
    import cli
    assert cli._presets_path() == str(tmp_path / "data" / "presets.json")
    assert cli._archive_path() == str(tmp_path / "data" / "archive.txt")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_paths.py -q`
Expected: FAIL - `default_cookie_dir()` still returns the app dir, so the first assertion fails.

- [ ] **Step 3: Write minimal implementation**

`default_cookie_dir` becomes a one-line delegate:

```python
def default_cookie_dir() -> str:
    """Where cookie files live by default: the per-user data directory.

    Next to the executable is read-only in several real installs, so the app
    keeps cookies (and the queue) in a writable per-user directory instead.
    """
    from core.paths import data_dir
    return data_dir()
```

`cli.py`: point the three paths at the data dir. Keep the `SOCIALCLIP_QUEUE`
override for the queue file only.

```python
def _queue_path() -> str:
    from core.paths import data_dir
    override = os.environ.get("SOCIALCLIP_QUEUE")
    if override:
        return override
    return os.path.join(data_dir(), "queue.json")


def _presets_path() -> str:
    from core.paths import data_dir
    return os.path.join(data_dir(), "presets.json")


def _archive_path() -> str:
    """The archive file, beside the queue file."""
    return os.path.join(os.path.dirname(_queue_path()), "archive.txt")
```

At the top of `main()` in **both** entry points, before Qt or `core.download` is
imported, run the migration:

```python
def main(argv=None):
    from core.paths import migrate_legacy_files
    migrate_legacy_files()
    ...
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS. `tests/test_cookies.py`, `tests/test_cli_queue.py`, and
`tests/test_doctor.py` must still pass: they pass an explicit `cookie_dir` or
monkeypatch the path, so the default change does not break them.

- [ ] **Step 5: Commit**

```bash
git add sites/cookies.py cli.py socialclip_downloader.py tests/test_paths.py
git commit -m "feat: move cookies, queue, presets, and archive into the data dir"
```

---

### Task 3: `utils.ytdlp.load()` - managed yt-dlp precedence

**Files:**
- Modify: `utils/ytdlp.py`
- Modify: `socialclip_downloader.py` (`main`, call `load()` before Qt)
- Modify: `cli.py` (`main`, call `load()` first)
- Test: `tests/test_ytdlp.py` (append)

**Interfaces:**
- Consumes: `core.paths.managed_dir("yt-dlp")`
- Produces: `managed_ytdlp_dir() -> str`, `load() -> str` (`"managed"` or `"system"`), `find_js_runtime(which=None)` now also checks `core.paths.managed_dir("bin")/deno`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ytdlp.py  (append)
import os
import subprocess
import sys
import textwrap


def test_managed_ytdlp_dir_uses_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    from utils import ytdlp
    assert ytdlp.managed_ytdlp_dir() == os.path.join(str(tmp_path), "yt-dlp")


def test_load_prefers_managed_copy(tmp_path, monkeypatch):
    """A package in the managed dir must win over the installed one."""
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    pkg = tmp_path / "yt-dlp" / "yt_dlp"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "version.py").write_text('__version__ = "9999.01.01"\n',
                                     encoding="utf-8")

    code = textwrap.dedent(
        """
        from utils.ytdlp import load
        state = load()
        from yt_dlp.version import __version__
        print(state, __version__)
        """
    )
    env = dict(os.environ, PYTHONPATH=os.getcwd())
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env,
        cwd=os.getcwd(),
    )
    assert out.stdout.split() == ["managed", "9999.01.01"], out.stderr


def test_load_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    from utils import ytdlp
    first = ytdlp.load()
    second = ytdlp.load()
    assert first == second
    assert sys.path.count(ytdlp.managed_ytdlp_dir()) == 1


def test_find_js_runtime_prefers_managed_deno(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    name = "deno.exe" if sys.platform == "win32" else "deno"
    (bin_dir / name).write_text("", encoding="utf-8")
    from utils import ytdlp
    found_name, found_path = ytdlp.find_js_runtime(which=lambda _n: None)
    assert found_name == "deno"
    assert found_path == os.path.join(str(bin_dir), name)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ytdlp.py -q`
Expected: FAIL with `AttributeError: module 'utils.ytdlp' has no attribute 'managed_ytdlp_dir'`

- [ ] **Step 3: Write minimal implementation**

Add to `utils/ytdlp.py`:

```python
import os
import sys


def managed_ytdlp_dir() -> str:
    """Directory of the managed yt-dlp package, or "" when none is installed."""
    try:
        from core.paths import managed_dir
    except Exception:
        return ""
    return managed_dir("yt-dlp")


def load() -> str:
    """Put a managed yt-dlp on sys.path, if one is installed.

    Must run before anything imports ``yt_dlp``: the managed copy is newer by
    construction and is the whole point of managing it. Idempotent.
    """
    directory = managed_ytdlp_dir()
    if not directory or not os.path.isdir(os.path.join(directory, "yt_dlp")):
        return "system"
    if directory not in sys.path:
        sys.path.insert(0, directory)
    return "managed"


def _managed_bin() -> str:
    try:
        from core.paths import managed_dir
    except Exception:
        return ""
    return managed_dir("bin")


def _managed_runtime(name: str) -> str:
    directory = _managed_bin()
    if not directory:
        return ""
    for fname in (name, name + ".exe"):
        candidate = os.path.join(directory, fname)
        if os.path.isfile(candidate):
            return candidate
    return ""


def find_js_runtime(which=None):
    """(name, path) of the first available JS runtime, or ("", "").

    A runtime the app installed itself is checked before PATH.
    """
    which = shutil.which if which is None else which
    for name in RUNTIMES:
        managed = _managed_runtime(name)
        if managed:
            return name, managed
        try:
            found = which(name)
        except Exception:
            found = None
        if found:
            return name, found
    return "", ""
```

Call `load()` at the top of `main()` in both entry points, next to the
migration from Task 2:

```python
def main(argv=None):
    from core.paths import migrate_legacy_files
    from utils.ytdlp import load
    migrate_legacy_files()
    load()
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ytdlp.py -q`
Expected: PASS. The subprocess test prints `managed 9999.01.01`.

- [ ] **Step 5: Commit**

```bash
git add utils/ytdlp.py socialclip_downloader.py cli.py tests/test_ytdlp.py
git commit -m "feat: load a managed yt-dlp and prefer a managed JS runtime"
```

---

### Task 4: `core/maintenance.py` - component model, checks, repair plan

**Files:**
- Create: `core/version.py`
- Create: `core/maintenance.py`
- Modify: `socialclip_downloader.py` (import `__version__` from `core.version`)
- Test: `tests/test_maintenance.py`

**Interfaces:**
- Consumes: `core.paths.data_dir`, `utils.ytdlp.*`, `utils.ffmpeg.find_ffmpeg`, `core.doctor.ffmpeg_version`
- Produces: `core.version.__version__`, `STATES`, `REPAIRABLE`, `ALLOWED_HOSTS`, `Component`, `check_all(which=None, exists=None, runner=None) -> list`, `plan_repairs(components) -> list`, `latest_ytdlp(opener=None) -> tuple`

**Controller ruling:** the app version must be readable **without importing the Qt entry
point**. `core/maintenance.py` runs in the CLI too, and `import socialclip_downloader`
pulls PyQt5. So the version moves to `core/version.py`; `socialclip_downloader.py`
re-exports it so existing importers (`ui/main_window.py`) keep working.

- [ ] **Step 0: Create `core/version.py` and re-export it**

```python
# core/version.py
"""The app version, importable without pulling in Qt."""

__version__ = "0.9.3"
```

In `socialclip_downloader.py`, replace the literal assignment with the import,
keeping the `__version__` name so `from socialclip_downloader import __version__`
still works:

```python
from core.version import __version__  # noqa: F401 - re-exported
```

Run: `python -m pytest -q`
Expected: PASS (nothing else changes).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_maintenance.py
import os
import sys

from core import maintenance
from core.maintenance import Component


def _by_key(components):
    return {c.key: c for c in components}


def test_check_all_reports_missing_ytdlp(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    # yt-dlp is installed in this environment, so force the "missing" case.
    monkeypatch.setattr(maintenance, "_ytdlp_version", lambda: "")
    comps = _by_key(maintenance.check_all(
        which=lambda _n: None, runner=lambda _c: None,
    ))
    assert comps["yt-dlp"].state == "missing"
    assert comps["yt-dlp"].action == "install"
    assert comps["ffmpeg"].state == "missing"
    assert comps["js-runtime"].state == "missing"


def test_check_all_reports_stale_ytdlp(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    monkeypatch.setattr(maintenance, "_ytdlp_version", lambda: "2020.01.01")
    comps = _by_key(maintenance.check_all(which=lambda _n: None))
    assert comps["yt-dlp"].state == "stale"
    assert comps["yt-dlp"].action == "update"


def test_check_all_reports_found_components(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    monkeypatch.setattr(maintenance, "_ytdlp_version", lambda: "2099.01.01")
    monkeypatch.setattr(
        maintenance, "find_ffmpeg", lambda **kw: "/usr/bin/ffmpeg"
    )
    monkeypatch.setattr(
        maintenance, "find_js_runtime", lambda which=None: ("node", "/usr/bin/node")
    )
    comps = _by_key(maintenance.check_all())
    assert comps["yt-dlp"].state == "ok"
    assert comps["ffmpeg"].state == "ok"
    assert comps["js-runtime"].state == "ok"
    assert comps["app"].state == "ok"
    assert comps["data-dir"].state == "ok"


def test_plan_repairs_selects_only_repairable():
    comps = [
        Component("yt-dlp", "yt-dlp", "stale", action="update"),
        Component("ffmpeg", "ffmpeg", "ok"),
        Component("js-runtime", "JavaScript runtime", "missing", action="install"),
        Component("app", "App", "stale", action="update"),
        Component("data-dir", "Data directory", "ok"),
    ]
    assert maintenance.plan_repairs(comps) == ["yt-dlp", "js-runtime"]


def test_plan_repairs_ignores_unknown():
    comps = [Component("yt-dlp", "yt-dlp", "unknown", action="install")]
    assert maintenance.plan_repairs(comps) == []


def test_latest_ytdlp_parses_the_release(monkeypatch):
    payload = {
        "tag_name": "2026.08.19",
        "assets": [
            {"name": "SHA2-256SUMS",
             "browser_download_url": "https://github.com/x/sums"},
            {"name": "yt_dlp-2026.08.19-py3-none-any.whl",
             "browser_download_url": "https://github.com/x/w.whl"},
        ],
    }
    monkeypatch.setattr(maintenance, "_get_json", lambda url, opener=None: payload)
    version, wheel, sums = maintenance.latest_ytdlp()
    assert version == "2026.08.19"
    assert wheel.endswith(".whl")
    assert sums.endswith("sums")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_maintenance.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.maintenance'`

- [ ] **Step 3: Write minimal implementation**

```python
# core/maintenance.py
"""Check the app's components and repair the ones that rot.

yt-dlp's extractors break in weeks, and YouTube needs a JavaScript runtime that
is not bundled. This module reports each component's state and installs a
verified replacement into the per-user data directory.

Qt-free. Network access is injectable so the checks and installers are testable.
"""

import hashlib
import json
import os
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import List, Optional

from core.doctor import ffmpeg_version
from core.paths import data_dir, managed_dir
from core.version import __version__
from utils.ffmpeg import find_ffmpeg
from utils.ytdlp import find_js_runtime, is_stale, version_age_days

STATES = ("ok", "missing", "stale", "broken", "unknown")

# Repaired from a download. "app" self-updates through core/updater.py and
# "data-dir" is not a download at all.
REPAIRABLE = ("yt-dlp", "ffmpeg", "js-runtime")

ALLOWED_HOSTS = ("github.com", "api.github.com",
                 "objects.githubusercontent.com")

YTDLP_LATEST = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
YTDLP_REPO = "https://github.com/yt-dlp/yt-dlp"

USER_AGENT = "SocialClip-Downloader"


@dataclass
class Component:
    key: str
    label: str
    state: str
    version: str = ""
    detail: str = ""
    action: str = "none"


def _ytdlp_version() -> str:
    from utils.ytdlp import ytdlp_version
    return ytdlp_version()


def _get(url: str, opener=None, timeout: int = 30) -> bytes:
    """Fetch a URL. HTTPS and an allow-listed host are required."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "") not in ALLOWED_HOSTS:
        raise ValueError("refusing to fetch %s" % (url or "an unknown URL"))
    open_url = opener or urllib.request.urlopen
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with open_url(request, timeout=timeout) as response:
        return response.read()


def _get_json(url: str, opener=None) -> dict:
    return json.loads(_get(url, opener=opener).decode("utf-8"))


def check_all(which=None, exists=None, runner=None) -> List[Component]:
    """Every component's state from local information only. Never raises."""
    components = []

    components.append(
        Component("app", "App", "ok", version=__version__)
    )

    version = ""
    try:
        version = _ytdlp_version()
    except Exception:
        version = ""
    if not version:
        ytdlp = Component(
            "yt-dlp", "yt-dlp", "missing", detail="not installed",
            action="install",
        )
    elif is_stale(version):
        age = version_age_days(version)
        ytdlp = Component(
            "yt-dlp", "yt-dlp", "stale", version=version,
            detail="%s days old" % age, action="update",
        )
    else:
        ytdlp = Component("yt-dlp", "yt-dlp", "ok", version=version)
    components.append(ytdlp)

    try:
        path = find_ffmpeg(which=which, exists=exists) or ""
    except Exception:
        path = ""
    if path:
        text = ""
        try:
            text = ffmpeg_version(path, runner=runner) or ""
        except Exception:
            text = ""
        components.append(
            Component("ffmpeg", "ffmpeg", "ok", version=text or "present")
        )
    else:
        components.append(
            Component("ffmpeg", "ffmpeg", "missing", detail="not found",
                      action="install")
        )

    try:
        name, runtime_path = find_js_runtime(which=which)
    except Exception:
        name, runtime_path = "", ""
    if name:
        components.append(
            Component("js-runtime", "JavaScript runtime", "ok",
                      version="%s (%s)" % (name, runtime_path))
        )
    else:
        components.append(
            Component("js-runtime", "JavaScript runtime", "missing",
                      detail="YouTube needs deno or node", action="install")
        )

    try:
        writable = os.access(data_dir(), os.W_OK)
    except Exception:
        writable = False
    components.append(
        Component(
            "data-dir", "Data directory",
            "ok" if writable else "broken",
            version=data_dir(),
            detail="" if writable else "not writable",
        )
    )
    return components


def plan_repairs(components) -> List[str]:
    """Component keys that should be repaired now. Pure.

    Only missing, stale, and broken components are repaired, and only the
    repairable ones. Unknown stays unknown: better to say nothing than to
    reinstall over a working copy.
    """
    keys = []
    for component in components:
        if component.key not in REPAIRABLE:
            continue
        if component.state in ("missing", "stale", "broken"):
            keys.append(component.key)
    return keys


def latest_ytdlp(opener=None):
    """(version, wheel_url, sums_url) for the newest yt-dlp release."""
    data = _get_json(YTDLP_LATEST, opener=opener)
    version = (data.get("tag_name") or "").lstrip("v")
    wheel = sums = ""
    for asset in data.get("assets", []):
        name = asset.get("name") or ""
        url = asset.get("browser_download_url") or ""
        if name == "SHA2-256SUMS":
            sums = url
        elif name.endswith(".whl"):
            wheel = url
    if not (version and wheel and sums):
        raise ValueError("the yt-dlp release is missing a wheel or its checksums")
    return version, wheel, sums
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_maintenance.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add core/maintenance.py tests/test_maintenance.py
git commit -m "feat: check components and plan repairs"
```

---

### Task 5: `install_ytdlp` - fetch, verify, unpack, swap, roll back

**Files:**
- Modify: `core/maintenance.py`
- Test: `tests/test_maintenance.py` (append)

**Interfaces:**
- Consumes: `latest_ytdlp`, `_get`, `managed_dir`
- Produces: `_parse_sums(text) -> dict`, `_verify_bytes(data, expected_hex) -> bool`, `install_ytdlp(dest=None, opener=None) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_maintenance.py  (append)
import hashlib
import io
import zipfile


def _wheel_bytes(version="2099.01.01"):
    """A minimal wheel: a zip whose root holds the yt_dlp package."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("yt_dlp/__init__.py", "")
        zf.writestr("yt_dlp/version.py", '__version__ = "%s"\n' % version)
    return buffer.getvalue()


def _release_opener(wheel, wheel_name, good_digest=True):
    sums = hashlib.sha256(wheel).hexdigest()
    if not good_digest:
        sums = "0" * 64

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def read(self):
            return self._payload

        def geturl(self):
            return "https://github.com/x/x"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opener(request, timeout=None):
        url = getattr(request, "full_url", request)
        if "latest" in url:
            body = json.dumps({
                "tag_name": "2099.01.01",
                "assets": [
                    {"name": "SHA2-256SUMS",
                     "browser_download_url": "https://github.com/x/sums"},
                    {"name": wheel_name,
                     "browser_download_url": "https://github.com/x/" + wheel_name},
                ],
            }).encode("utf-8")
            return _Response(body)
        if url.endswith("sums"):
            return _Response(("%s  %s\n" % (sums, wheel_name)).encode("utf-8"))
        return _Response(wheel)

    return opener


def test_parse_sums_reads_the_checksum_file():
    text = "abc123  yt_dlp-1-py3-none-any.whl\ndef456  other.zip\n"
    assert maintenance._parse_sums(text) == {
        "yt_dlp-1-py3-none-any.whl": "abc123",
        "other.zip": "def456",
    }


def test_install_ytdlp_unpacks_a_verified_wheel(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    wheel = _wheel_bytes()
    dest = tmp_path / "yt-dlp"
    version = maintenance.install_ytdlp(
        dest=str(dest),
        opener=_release_opener(wheel, "yt_dlp-2099.01.01-py3-none-any.whl"),
    )
    assert version == "2099.01.01"
    assert (dest / "yt_dlp" / "version.py").is_file()


def test_install_ytdlp_refuses_a_bad_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    dest = tmp_path / "yt-dlp"
    wheel = _wheel_bytes()
    try:
        maintenance.install_ytdlp(
            dest=str(dest),
            opener=_release_opener(
                wheel, "yt_dlp-2099.01.01-py3-none-any.whl", good_digest=False
            ),
        )
        raised = False
    except ValueError:
        raised = True
    assert raised
    assert not (dest / "yt_dlp").exists()


def test_install_ytdlp_keeps_a_previous_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    dest = tmp_path / "yt-dlp"
    (dest / "yt_dlp").mkdir(parents=True)
    (dest / "yt_dlp" / "version.py").write_text(
        '__version__ = "1.0.0"\n', encoding="utf-8"
    )
    maintenance.install_ytdlp(
        dest=str(dest),
        opener=_release_opener(_wheel_bytes(), "yt_dlp-2099.01.01-py3-none-any.whl"),
    )
    assert (tmp_path / "yt-dlp.prev" / "yt_dlp" / "version.py").is_file()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_maintenance.py -q -k install`
Expected: FAIL with `AttributeError: module 'core.maintenance' has no attribute '_parse_sums'`

- [ ] **Step 3: Write minimal implementation**

```python
# core/maintenance.py  (append)

import shutil
import tempfile


def _parse_sums(text: str) -> dict:
    """name -> hex digest, from a sha256sums-style file. Pure."""
    sums = {}
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            sums[parts[-1].lstrip("*")] = parts[0].lower()
    return sums


def _verify_bytes(data: bytes, expected_hex: str) -> bool:
    return hashlib.sha256(data).hexdigest().lower() == (expected_hex or "").lower()


def _unpack_wheel(data: bytes, target: str) -> None:
    """Extract a wheel's ``yt_dlp`` package into `target`."""
    os.makedirs(target, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = [n for n in zf.namelist() if n.startswith("yt_dlp/")]
        if not names:
            raise ValueError("the wheel does not contain a yt_dlp package")
        zf.extractall(target, members=names)


def _swap(new_dir: str, dest: str, keep_previous: bool) -> None:
    """Replace `dest` with `new_dir`, keeping the old copy when asked."""
    previous = dest + ".prev"
    if keep_previous and os.path.isdir(dest):
        if os.path.isdir(previous):
            shutil.rmtree(previous, ignore_errors=True)
        os.replace(dest, previous)
    elif os.path.isdir(dest):
        shutil.rmtree(dest, ignore_errors=True)
    os.replace(new_dir, dest)


def install_ytdlp(dest=None, opener=None) -> str:
    """Download, verify, and install the newest yt-dlp. Returns its version.

    The wheel is unpacked into a temporary directory and only swapped in after
    its SHA-256 matches the release's checksum file, so a bad download never
    replaces a working copy.
    """
    dest = dest or managed_dir("yt-dlp")
    version, wheel_url, sums_url = latest_ytdlp(opener=opener)

    sums = _parse_sums(_get(sums_url, opener=opener).decode("utf-8"))
    name = wheel_url.rsplit("/", 1)[-1]
    expected = sums.get(name)
    if not expected:
        raise ValueError("no checksum published for %s" % name)

    data = _get(wheel_url, opener=opener)
    if not _verify_bytes(data, expected):
        raise ValueError("checksum mismatch for %s" % name)

    parent = os.path.dirname(dest) or "."
    os.makedirs(parent, exist_ok=True)
    temp = tempfile.mkdtemp(prefix="ytdlp-", dir=parent)
    try:
        _unpack_wheel(data, temp)
        _swap(temp, dest, keep_previous=True)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return version
```

Add `import io` to the module's imports.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_maintenance.py -q`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add core/maintenance.py tests/test_maintenance.py
git commit -m "feat: install a verified yt-dlp with rollback"
```

---

### Task 6: `install_ffmpeg`, `install_deno`, and managed-first lookup

**Files:**
- Modify: `core/maintenance.py`
- Modify: `utils/ffmpeg.py` (`find_ffmpeg` checks the managed dir first)
- Test: `tests/test_maintenance.py` (append), `tests/test_ffmpeg.py` (append)

**Interfaces:**
- Consumes: `managed_dir`, `_get`, `_parse_sums`, `_verify_bytes`
- Produces: `FFMPEG_BUILDS`, `DENO_RELEASE`, `_platform_tag() -> str`, `install_ffmpeg(dest=None, opener=None) -> str`, `install_deno(dest=None, opener=None) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_maintenance.py  (append)
import sys as _sys


def test_platform_tag_is_known():
    assert maintenance._platform_tag() in ("win64", "linux64", "macos64")


def test_install_deno_unpacks_and_verifies(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    binary = b"#!/bin/sh\necho deno\n"
    digest = hashlib.sha256(binary).hexdigest()
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("deno", binary)
    payload = zip_buffer.getvalue()
    payload_digest = hashlib.sha256(payload).hexdigest()

    class _Response:
        def __init__(self, body):
            self._body = body

        def read(self):
            return self._body

        def geturl(self):
            return "https://github.com/x/x"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opener(request, timeout=None):
        url = getattr(request, "full_url", request)
        if url.endswith(".sha256sum"):
            return _Response(("%s  deno.zip\n" % payload_digest).encode("utf-8"))
        return _Response(payload)

    version = maintenance.install_deno(
        dest=str(tmp_path / "bin"), opener=opener,
    )
    assert version
    name = "deno.exe" if _sys.platform == "win32" else "deno"
    assert (tmp_path / "bin" / name).is_file()


def test_find_ffmpeg_prefers_managed(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    name = "ffmpeg.exe" if _sys.platform == "win32" else "ffmpeg"
    (bin_dir / name).write_text("", encoding="utf-8")
    from utils import ffmpeg
    assert ffmpeg.find_ffmpeg(env={}, which=lambda _n: None,
                              exists=os.path.isfile) == os.path.join(
        str(bin_dir), name)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_maintenance.py tests/test_ffmpeg.py -q -k "deno or managed"`
Expected: FAIL with `AttributeError: module 'core.maintenance' has no attribute '_platform_tag'`

- [ ] **Step 3: Write minimal implementation**

**Controller ruling (verify before coding):** BtbN publishes per-asset `.sha256`
files; confirm by fetching
`https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip.sha256`
(or the linux64/macos64 equivalent) and checking it returns 200. If BtbN does
**not** publish one, use its `checksums.sha256` asset if the release has one; if
neither exists, switch Windows ffmpeg to gyan.dev's
`ffmpeg-release-essentials.zip` plus its `.sha256`, keep BtbN for
linux64/macos64, and report the change. Never install an unverified ffmpeg.

```python
# core/maintenance.py  (append)

import stat
import sys

FFMPEG_BUILDS = "https://github.com/BtbN/FFmpeg-Builds/releases/latest"
DENO_RELEASE = "https://github.com/denoland/deno/releases/latest/download"


def _platform_tag() -> str:
    """BtbN's build tag for this platform."""
    if sys.platform == "win32":
        return "win64"
    if sys.platform == "darwin":
        return "macos64"
    return "linux64"


def _deno_asset() -> str:
    if sys.platform == "win32":
        return "deno-x86_64-pc-windows-msvc.zip"
    if sys.platform == "darwin":
        return "deno-x86_64-apple-darwin.zip"
    return "deno-x86_64-unknown-linux-gnu.zip"


def _make_executable(path: str) -> None:
    try:
        mode = os.stat(path).st_mode
        os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass


def install_ffmpeg(dest=None, opener=None) -> str:
    """Download a static ffmpeg build, verify it, and install ffmpeg/ffprobe.

    Returns the version string. Unpacks to a temporary directory first, so a bad
    download never replaces a working copy.
    """
    dest = dest or managed_dir("bin")
    tag = _platform_tag()
    zip_name = "ffmpeg-master-latest-%s-gpl.zip" % tag
    zip_url = "%s/download/%s" % (FFMPEG_BUILDS, zip_name)
    sums_url = zip_url + ".sha256"

    expected = _parse_sums(_get(sums_url, opener=opener).decode("utf-8")).get(
        zip_name
    )
    if not expected:
        raise ValueError("no checksum published for %s" % zip_name)
    data = _get(zip_url, opener=opener)
    if not _verify_bytes(data, expected):
        raise ValueError("checksum mismatch for %s" % zip_name)

    parent = os.path.dirname(dest) or "."
    os.makedirs(parent, exist_ok=True)
    temp = tempfile.mkdtemp(prefix="ffmpeg-", dir=parent)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            wanted = [
                n for n in zf.namelist()
                if os.path.basename(n) in (
                    "ffmpeg", "ffmpeg.exe", "ffprobe", "ffprobe.exe"
                )
            ]
            if not wanted:
                raise ValueError("the ffmpeg build has no ffmpeg binary")
            for name in wanted:
                with zf.open(name) as src:
                    out = os.path.join(temp, os.path.basename(name))
                    with open(out, "wb") as fh:
                        shutil.copyfileobj(src, fh)
                    _make_executable(out)

        os.makedirs(dest, exist_ok=True)
        for name in os.listdir(temp):
            os.replace(os.path.join(temp, name), os.path.join(dest, name))
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    return "installed"


def install_deno(dest=None, opener=None) -> str:
    """Download deno, verify it, and install it as the JS runtime."""
    dest = dest or managed_dir("bin")
    asset = _deno_asset()
    url = "%s/%s" % (DENO_RELEASE, asset)
    sums = _get(url + ".sha256sum", opener=opener).decode("utf-8")
    expected = _parse_sums(sums).get(asset) or sums.split()[0]

    data = _get(url, opener=opener)
    if not _verify_bytes(data, expected):
        raise ValueError("checksum mismatch for %s" % asset)

    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        name = next(
            (n for n in zf.namelist() if os.path.basename(n).startswith("deno")),
            "",
        )
        if not name:
            raise ValueError("the deno archive has no binary")
        out = os.path.join(dest, os.path.basename(name))
        with zf.open(name) as src, open(out, "wb") as fh:
            shutil.copyfileobj(src, fh)
    _make_executable(out)
    return "installed"
```

`utils/ffmpeg.py`: check the managed `bin/` before the bundled copy, so a
repaired ffmpeg is used.

```python
def _managed_bin_dir():
    """The app's managed bin directory, or "" when there is none."""
    try:
        from core.paths import managed_dir
    except Exception:
        return ""
    return managed_dir("bin")


def find_ffmpeg(env=None, which=None, exists=None, candidate_dirs=None,
                bundle_dir=None):
    """Locate ffmpeg: managed copy, bundled copy, env override, PATH, dirs."""
    env = os.environ if env is None else env
    which = shutil.which if which is None else which
    exists = os.path.isfile if exists is None else exists

    managed = _managed_bin_dir()
    if managed:
        for name in ("ffmpeg", "ffmpeg.exe"):
            candidate = os.path.join(managed, name)
            if exists(candidate):
                return candidate

    if bundle_dir is None:
        bundle_dir = _bundle_dir()
    # ... unchanged from here ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_maintenance.py tests/test_ffmpeg.py -q`
Expected: PASS. `tests/test_ffmpeg.py`'s existing cases must still pass: they
pass `env={}` and a `which` stub, and `_managed_bin_dir()` returns "" when the
data dir has no `bin/`.

- [ ] **Step 5: Commit**

```bash
git add core/maintenance.py utils/ffmpeg.py tests/test_maintenance.py tests/test_ffmpeg.py
git commit -m "feat: install a verified ffmpeg and deno, and prefer the managed ffmpeg"
```

---

### Task 7: `workers/maintenance_worker.py`

**Files:**
- Create: `workers/maintenance_worker.py`
- Test: `tests/test_maintenance_worker.py`

**Interfaces:**
- Consumes: `core.maintenance.check_all`, `plan_repairs`, `install_ytdlp`, `install_ffmpeg`, `install_deno`
- Produces: `MaintenanceCheckWorker` (`done_signal(list)`, `error_signal(str)`), `MaintenanceRepairWorker(keys)` (`progress_signal(str, str)`, `done_signal(list)`, `error_signal(str)`), `run_repairs(keys, progress=None) -> list`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_maintenance_worker.py
import os
import sys

from workers.maintenance_worker import run_repairs


def test_run_repairs_calls_the_right_installer(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    calls = []

    # Patch the names the worker module bound, not core.maintenance's: the
    # worker imported them directly.
    from workers import maintenance_worker

    monkeypatch.setattr(
        maintenance_worker, "install_ytdlp",
        lambda dest=None, opener=None: calls.append("yt-dlp") or "1.0",
    )
    monkeypatch.setattr(
        maintenance_worker, "install_ffmpeg",
        lambda dest=None, opener=None: calls.append("ffmpeg") or "1.0",
    )
    monkeypatch.setattr(
        maintenance_worker, "install_deno",
        lambda dest=None, opener=None: calls.append("deno") or "1.0",
    )
    monkeypatch.setattr(maintenance_worker, "check_all", lambda *a, **kw: [])

    seen = []
    result = run_repairs(["yt-dlp", "js-runtime"], progress=seen.append)

    assert calls == ["yt-dlp", "deno"]
    assert result == []
    assert len(seen) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_maintenance_worker.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'workers.maintenance_worker'`

- [ ] **Step 3: Write minimal implementation**

```python
# workers/maintenance_worker.py
"""Run component checks and repairs off the UI thread."""

from PyQt5 import QtCore

from core.maintenance import (
    check_all,
    install_deno,
    install_ffmpeg,
    install_ytdlp,
    plan_repairs,
)

# component key -> installer. "js-runtime" is satisfied by a managed deno.
INSTALLERS = {
    "yt-dlp": install_ytdlp,
    "ffmpeg": install_ffmpeg,
    "js-runtime": install_deno,
}


def run_repairs(keys, progress=None):
    """Install each requested component, then re-check. Returns the components.

    A failure is reported through `progress` and does not stop the others: one
    broken component must not block the rest.
    """
    for key in keys:
        installer = INSTALLERS.get(key)
        if installer is None:
            continue
        if progress:
            progress(key, "installing")
        try:
            version = installer()
        except Exception as exc:  # noqa: BLE001 - report, keep going
            if progress:
                progress(key, "failed: %s" % exc)
            continue
        if progress:
            progress(key, "installed %s" % (version or ""))
    return check_all()


class MaintenanceCheckWorker(QtCore.QThread):
    done_signal = QtCore.pyqtSignal(object)
    error_signal = QtCore.pyqtSignal(str)

    def run(self):
        try:
            components = check_all()
        except Exception as exc:  # noqa: BLE001 - never crash the thread
            self.error_signal.emit(str(exc))
            return
        self.done_signal.emit(components)


class MaintenanceRepairWorker(QtCore.QThread):
    progress_signal = QtCore.pyqtSignal(str, str)
    done_signal = QtCore.pyqtSignal(object)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, keys):
        super().__init__()
        self.keys = list(keys)

    def run(self):
        try:
            components = run_repairs(
                self.keys, progress=self.progress_signal.emit,
            )
        except Exception as exc:  # noqa: BLE001 - never crash the thread
            self.error_signal.emit(str(exc))
            return
        self.done_signal.emit(components)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_maintenance_worker.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add workers/maintenance_worker.py tests/test_maintenance_worker.py
git commit -m "feat: run component checks and repairs off the UI thread"
```

---

### Task 8: Health view and the startup check

**Files:**
- Modify: `ui/dialogs.py` (`DoctorDialog` gains component rows, Repair, Repair all, Open data folder)
- Modify: `ui/main_window.py` (startup check, daily cache, Help menu item)
- Modify: `ui/main_window.py` (the `File` menu gains **Open data folder**)
- Test: `tests/test_ui_wiring.py` (append)

**Interfaces:**
- Consumes: `core.maintenance.Component`, `core.paths.data_dir`, `workers.maintenance_worker`
- Produces: `ui.dialogs.doctor_lines(report, components) -> list` (pure, testable), `ui.dialogs.show_doctor(parent, on_repair=None)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ui_wiring.py  (append)
from core.maintenance import Component
from ui.dialogs import doctor_lines


def test_doctor_lines_include_every_component():
    components = [
        Component("yt-dlp", "yt-dlp", "stale", version="2020.01.01",
                  detail="2000 days old", action="update"),
        Component("ffmpeg", "ffmpeg", "ok", version="ffmpeg version 6.1"),
        Component("js-runtime", "JavaScript runtime", "missing",
                  detail="YouTube needs deno or node", action="install"),
    ]
    text = "\n".join(doctor_lines({"schema_version": "1.2"}, components))
    assert "yt-dlp" in text
    assert "stale" in text
    assert "JavaScript runtime" in text
    assert "missing" in text
    assert "ffmpeg version 6.1" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_wiring.py -q -k doctor`
Expected: FAIL with `ImportError: cannot import name 'doctor_lines'`

- [ ] **Step 3: Write minimal implementation**

`ui/dialogs.py`: a pure line builder, then the dialog uses it and adds the
buttons. Keep the existing ffmpeg/cookies/network lines below the component
rows.

```python
def doctor_lines(report, components=None) -> list:
    """Human-readable Doctor/Health text. Pure, so it is testable."""
    lines = ["Health report (schema %s)" % report.get("schema_version", "1.2"), ""]
    if components:
        lines.append("components:")
        for component in components:
            version = " %s" % component.version if component.version else ""
            detail = " (%s)" % component.detail if component.detail else ""
            lines.append(
                "  %-20s %-8s%s%s"
                % (component.label, component.state, version, detail)
            )
        lines.append("")

    ffmpeg = report.get("ffmpeg", {})
    lines.append("ffmpeg:")
    if ffmpeg.get("found"):
        lines.append("  path: %s" % ffmpeg.get("path"))
        lines.append("  version: %s" % (ffmpeg.get("version") or "unknown"))
    else:
        lines.append("  not found")

    lines.append("")
    lines.append("cookies:")
    found = [c for c in report.get("cookies", []) if c.get("found")]
    if found:
        for cookie in found:
            lines.append("  %s: %s" % (cookie.get("platform"), cookie.get("path")))
    else:
        lines.append("  none found")

    network = report.get("network", {})
    lines.append("")
    lines.append("network:")
    lines.append("  ok: %s" % network.get("ok"))
    lines.append("  detail: %s" % network.get("detail"))

    lines.append("")
    lines.append(_js_runtime_line(report))
    lines.append(_ytdlp_line(report))
    return lines


def show_doctor(parent, on_repair=None):
    """Health view: the report, the components, and a Repair action."""
    from core.maintenance import check_all, plan_repairs
    from core.paths import data_dir

    try:
        report = run_checks()
    except Exception as exc:
        report = {"schema_version": "1.2", "error": str(exc)}
    try:
        components = check_all()
    except Exception:
        components = []

    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Health")
    dialog.resize(620, 460)
    layout = QtWidgets.QVBoxLayout(dialog)
    view = QtWidgets.QTextEdit()
    view.setReadOnly(True)
    view.setPlainText("\n".join(doctor_lines(report, components)))
    layout.addWidget(view)

    buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
    repair = buttons.addButton("Repair", QtWidgets.QDialogButtonBox.ActionRole)
    repair_all = buttons.addButton(
        "Repair all", QtWidgets.QDialogButtonBox.ActionRole
    )
    open_dir = buttons.addButton(
        "Open data folder", QtWidgets.QDialogButtonBox.ActionRole
    )

    def _repair(keys):
        if on_repair is None or not keys:
            return
        dialog.accept()
        on_repair(keys)

    repair.clicked.connect(lambda: _repair(plan_repairs(components)))
    repair_all.clicked.connect(lambda: _repair(list(plan_repairs(components))))
    open_dir.clicked.connect(lambda: reveal_in_folder(data_dir()))
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.exec_()
```

`show_doctor` already exists at `ui/dialogs.py:67`; replace its body with the
version above. `reveal_in_folder` is imported mid-module at
`ui/dialogs.py:259`, below `show_doctor`, so **move
`from utils.ui_helpers import reveal_in_folder` to the top imports** (after
`from utils.file_utils import default_download_folder`).

`ui/main_window.py`:

```python
    def _check_components(self, force=False):
        """Check components at most once a day; repair what is broken."""
        if not force:
            last = self.settings.value("maintenance/last_check", "") or ""
            if last and _within_a_day(last):
                return
        self.settings.setValue(
            "maintenance/last_check", datetime.datetime.now().isoformat()
        )
        self._maintenance_worker = MaintenanceCheckWorker()
        self._maintenance_worker.done_signal.connect(self._on_components_checked)
        self._maintenance_worker.start()

    def _on_components_checked(self, components):
        from core.maintenance import plan_repairs
        keys = plan_repairs(components)
        if not keys:
            return
        self.log("Repairing: %s" % ", ".join(keys))
        self._repair_worker = MaintenanceRepairWorker(keys)
        self._repair_worker.done_signal.connect(self._on_repair_done)
        self._repair_worker.progress_signal.connect(
            lambda key, detail: self.log("%s: %s" % (key, detail))
        )
        self._repair_worker.start()

    def _on_repair_done(self, components):
        from core.maintenance import plan_repairs
        remaining = plan_repairs(components)
        self.log(
            "Repair finished" if not remaining
            else "Still needs attention: %s" % ", ".join(remaining)
        )
```

In `ui/main_window.py`, add `import datetime` to the imports and
`from workers.maintenance_worker import MaintenanceCheckWorker,
MaintenanceRepairWorker`. In `_build_menubar` (`ui/main_window.py:87`), the
Help menu already has `self._action("&Doctor", lambda: show_doctor(self))` at
line 112: change that action's label to `&Health` and pass the repair callback,
and add a **Check components** action:

```python
help_menu.addAction(self._action(
    "&Health", lambda: show_doctor(self, on_repair=self._repair_components)
))
help_menu.addAction(self._action(
    "Check components", lambda: self._check_components(force=True)
))
```

Add to the File menu, next to the Cookies action at `ui/main_window.py:95`:

```python
from core.paths import data_dir
from utils.ui_helpers import reveal_in_folder
file_menu.addAction(self._action(
    "Open data folder", lambda: reveal_in_folder(data_dir())
))
```

Add the callback and call the check at the end of `__init__`:

```python
    def _repair_components(self, keys):
        self._repair_worker = MaintenanceRepairWorker(keys)
        self._repair_worker.done_signal.connect(self._on_repair_done)
        self._repair_worker.progress_signal.connect(
            lambda key, detail: self.log("%s: %s" % (key, detail))
        )
        self._repair_worker.start()
```

```python
        self._check_components()
```

- [ ] **Step 4: Run the full suite and a GUI smoke**

Run: `python -m pytest -q`
Expected: PASS.

Run:
```powershell
$env:PYTHONPATH=(Get-Location).Path; python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PyQt5 import QtWidgets; from ui.main_window import MainWindow; app=QtWidgets.QApplication([]); w=MainWindow(); print('Health OK')"
```
Expected: prints `Health OK` (the window constructs; the worker is off-thread).

- [ ] **Step 5: Commit**

```bash
git add ui/dialogs.py ui/main_window.py tests/test_ui_wiring.py
git commit -m "feat: Health view and a daily component check that repairs itself"
```

---

### Task 9: CLI `repair` and a components line in `doctor`

**Files:**
- Modify: `cli.py` (a `repair` subcommand; `doctor` prints component states)
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `core.maintenance.check_all`, `plan_repairs`, `workers.maintenance_worker.run_repairs`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py  (append)
def test_cli_repair_dry_run(capsys):
    from cli import main
    code = main(["repair", "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "would repair" in out or "nothing to repair" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -q -k repair`
Expected: FAIL - argparse rejects the unknown `repair` command.

- [ ] **Step 3: Write minimal implementation**

```python
    r = sub.add_parser("repair")
    r.add_argument("--dry-run", action="store_true",
                   help="show what would be repaired, then stop")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=_cmd_repair)
```

```python
def _cmd_repair(args):
    from core.maintenance import check_all, plan_repairs
    from workers.maintenance_worker import run_repairs

    components = check_all()
    keys = plan_repairs(components)
    if args.dry_run:
        if args.json:
            print(json.dumps({"schema_version": SCHEMA_VERSION,
                              "would_repair": keys}))
        else:
            print("would repair: %s" % ", ".join(keys) if keys
                  else "nothing to repair")
        return EXIT_OK

    if not keys:
        print("nothing to repair")
        return EXIT_OK
    components = run_repairs(keys, progress=lambda k, d: print("%s: %s" % (k, d)))
    remaining = plan_repairs(components)
    if args.json:
        print(json.dumps({"schema_version": SCHEMA_VERSION,
                          "repaired": keys, "remaining": remaining}))
    return EXIT_OK if not remaining else EXIT_FAIL
```

Add a components block to `_cmd_doctor` before the existing ffmpeg block:

```python
    from core.maintenance import check_all
    for component in check_all():
        print("%-20s %-8s %s" % (
            component.label, component.state, component.version or component.detail
        ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py tests/test_cli_queue.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli.py tests/test_cli.py
git commit -m "feat: socialclip repair and component states in doctor"
```

---

### Task 10: Documentation

**Files:**
- Modify: `README.md` (a Maintenance section; the cookie-folder instructions; the CLI table gains `repair`)
- Modify: `CHANGELOG.md` (`## Unreleased` -> a new section)
- Modify: `AGENTS.md` (the layout block gains `core/paths.py` and `core/maintenance.py`; the gotchas note the data directory)
- Modify: `socialclip_downloader.py` (`__version__` moves to `core/version.py`)

- [ ] **Step 1: README**

Add under **Features**:

```markdown
- **Self-repair and Health** - the app checks its components (yt-dlp, ffmpeg, the
  JavaScript runtime YouTube needs) at most once a day and repairs a missing or
  stale one from a verified download, so a build keeps working without a new
  release. **Help -> Check components** shows the **Health** view: every
  component with its version and state, plus **Repair** and **Open data folder**.
  `socialclip repair` does the same from the CLI.
- **Your data lives in one writable folder** - cookies, the queue, presets, the
  archive, and the downloaded components live in a per-user data directory
  (`%LOCALAPPDATA%\SocialClip Downloader`, `~/Library/Application Support/SocialClip Downloader`,
  or `~/.local/share/socialclip`). **File -> Open data folder** reveals it. Any
  files left next to the app are copied there once on first run.
```

Change the cookie-folder sentence to name the data directory, and add `repair`
to the CLI command table.

- [ ] **Step 2: CHANGELOG**

Add an `## Unreleased` section with `### Added` (the maintenance subsystem,
`core/paths.py`, `core/maintenance.py`, the Health view, `socialclip repair`)
and `### Changed` (state moved to the data dir, with a one-time copy migration).

- [ ] **Step 3: AGENTS.md**

Add to the layout block:

```
core/paths.py              per-user data directory + one-time legacy migration (pure)
core/maintenance.py        component checks + verified installers for yt-dlp/ffmpeg/deno
workers/maintenance_worker.py  runs checks and repairs off the UI thread
```

Add a gotcha: cookies, `queue.json`, `presets.json`, `archive.txt`, and the
managed components live in the data directory; `SOCIALCLIP_DATA` moves it and
`SOCIALCLIP_QUEUE` still overrides the queue file only.

- [ ] **Step 4: Bump the version and run everything**

Set `__version__ = "0.10.0"` in **`core/version.py`** (a new subsystem is a minor
bump). `socialclip_downloader.py` re-exports it, so nothing else changes.

Run: `python -m pytest -q`
Run: `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: PASS and `0`.

Run a functional smoke:
```powershell
$env:PYTHONPATH=(Get-Location).Path; python cli.py doctor; python cli.py repair --dry-run
```
Expected: component states print; `repair --dry-run` lists what would change.

- [ ] **Step 5: Commit**

```bash
git add README.md CHANGELOG.md AGENTS.md socialclip_downloader.py
git commit -m "docs: maintenance, self-repair, and the data directory"
```

---

## Self-Review

**Spec coverage:**
- Per-user data dir + migration -> Tasks 1, 2.
- Managed yt-dlp load order -> Task 3.
- Component model, checks, repair plan -> Task 4.
- Verified yt-dlp with rollback -> Task 5.
- Verified ffmpeg + deno, managed-first lookup -> Task 6.
- Off-thread work -> Task 7.
- Health view, daily check, Repair, Open data folder -> Task 8.
- CLI `repair` + doctor components -> Task 9.
- Docs, version -> Task 10.
- `SOCIALCLIP_QUEUE` kept -> Task 2. `SOCIALCLIP_DATA` -> Task 1.
- Security (HTTPS, allow-list, SHA-256, no delete-before-verify) -> Tasks 4, 5, 6.

**Gaps noted, deliberately out of this plan:**
- The **cookie resolution** bug (Queue tab never detects; `core.download` never
  resolves per-URL) is a separate bounded fix, tracked on its own.
- **Automatic rollback on a post-install failure** (a managed yt-dlp that
  imports but then fails a download) is spec Risk 2. This plan keeps `.prev`
  and lets Repair restore it; an automatic trigger is not included.
