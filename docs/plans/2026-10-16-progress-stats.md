# Download Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show percent, speed, ETA, and size in the download progress display on both tabs.

**Architecture:** A pure `core/progress.py` holds a `Progress` namedtuple and formatters. The download hook builds a `Progress`; both workers' progress signals carry it; both UIs render it.

**Tech Stack:** Python 3.8+, PyQt5 (GUI), yt-dlp (existing).

**Spec:** `docs/specs/2026-10-16-progress-stats-design.md`

## Global Constraints

- Python 3.8+; **no new dependencies**.
- `core/` stays **Qt-free and thread-free** (enforced by `tests/test_core_isolation.py`).
- The suite must stay green: `python -m pytest -q` (baseline 431 passing).
- Lint prints 0: `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`
- Conventional Commits. **Never commit a real social-media URL** (use `https://youtu.be/x`). **Never push** without approval.
- Every formatter tolerates `None` and returns `""` for it; no path raises.

---

### Task 1: `core/progress.py` - the Progress type and formatters

**Files:**
- Create: `core/progress.py`
- Test: `tests/test_progress.py` (create)

**Interfaces:**
- Produces:
  - `Progress` - `namedtuple("Progress", "percent speed eta downloaded total")`.
  - `format_bytes(n) -> str`, `format_speed(bps) -> str`, `format_eta(seconds) -> str`, `format_progress(p) -> str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_progress.py`:

```python
from core.progress import (
    Progress, format_bytes, format_eta, format_progress, format_speed,
)


def test_format_bytes_units():
    assert format_bytes(512) == "512 B"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(1024 * 1024 * 14.2) == "14.2 MB"
    assert format_bytes(1024 ** 3 * 1.4) == "1.4 GB"


def test_format_speed():
    assert format_speed(1024 * 1024 * 3.2) == "3.2 MB/s"
    assert format_speed(None) == ""


def test_format_eta():
    assert format_eta(12) == "ETA 00:12"
    assert format_eta(3723) == "ETA 1:02:03"
    assert format_eta(None) == ""


def test_format_progress_all_fields():
    p = Progress(percent=45, speed=1024 * 1024 * 3.2, eta=12,
                 downloaded=int(1024 * 1024 * 14.2),
                 total=int(1024 * 1024 * 31.0))
    text = format_progress(p)
    assert text.startswith("45%")
    assert "3.2 MB/s" in text
    assert "ETA 00:12" in text
    assert "14.2/31.0 MB" in text


def test_format_progress_omits_unknown_parts():
    p = Progress(percent=5, speed=None, eta=None, downloaded=1024, total=None)
    assert format_progress(p) == "5%  1.0 KB"


def test_format_progress_never_trailing_separator():
    p = Progress(percent=100, speed=None, eta=None, downloaded=0, total=None)
    assert format_progress(p) == "100%"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_progress.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.progress'`.

- [ ] **Step 3: Write `core/progress.py`**

```python
from collections import namedtuple
from typing import Optional

Progress = namedtuple(
    "Progress", ("percent", "speed", "eta", "downloaded", "total")
)

_UNITS = (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024))


def format_bytes(n) -> str:
    """1024-based size: '512 B', '48.3 KB', '14.2 MB', '1.4 GB'."""
    if n is None:
        return ""
    n = float(n)
    for label, scale in _UNITS:
        if n >= scale:
            return "%.1f %s" % (n / scale, label)
    return "%d B" % int(n)


def format_speed(bps: Optional[float]) -> str:
    """'3.2 MB/s', or '' when unknown."""
    if bps is None:
        return ""
    return format_bytes(bps) + "/s"


def format_eta(seconds: Optional[int]) -> str:
    """'ETA MM:SS' (or 'ETA H:MM:SS'), or '' when unknown."""
    if seconds is None:
        return ""
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return "ETA %d:%02d:%02d" % (hours, minutes, secs)
    return "ETA %02d:%02d" % (minutes, secs)


def format_progress(p: Progress) -> str:
    """'45%  3.2 MB/s  ETA 00:12  14.2/31.0 MB'; unknown parts drop out."""
    parts = ["%d%%" % int(p.percent)]
    if p.speed is not None:
        parts.append(format_speed(p.speed))
    if p.eta is not None:
        parts.append(format_eta(p.eta))
    if p.total:
        parts.append("%s/%s" % (format_bytes(p.downloaded),
                                format_bytes(p.total)))
    elif p.downloaded:
        parts.append(format_bytes(p.downloaded))
    return "  ".join(parts)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_progress.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, 437 passed.

- [ ] **Step 6: Commit**

```bash
git add core/progress.py tests/test_progress.py
git commit -m "feat(progress): Progress type and speed/eta/size formatters"
```

---

### Task 2: The download hook emits a `Progress`

**Files:**
- Modify: `core/download.py` (the `hook` and its two call sites)
- Test: `tests/test_core_download.py` (append)

**Interfaces:**
- Consumes: `Progress` (Task 1).
- Produces: `download_one`'s `progress` callable is now called with one `Progress` argument (was a bare `percent`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_core_download.py`:

```python
def test_progress_carries_speed_eta_and_size(monkeypatch, tmp_path):
    from core.progress import Progress

    class YDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True):
            for hook in self.opts.get("progress_hooks", []):
                hook({"status": "downloading", "downloaded_bytes": 1024 * 1024,
                      "total_bytes": 1024 * 1024 * 4, "speed": 1024 * 1024 * 2,
                      "eta": 3})
            return None

        def prepare_filename(self, info):
            return ""

    monkeypatch.setattr("yt_dlp.YoutubeDL", YDL)
    seen = []
    download_one(
        "https://youtu.be/x", outtmpl=str(tmp_path / "%(title)s.%(ext)s"),
        output_type="MP4", convert=False, target_resolution=1080,
        progress=seen.append,
    )
    assert seen, "the hook must report progress"
    p = seen[0]
    assert isinstance(p, Progress)
    assert p.percent == 25
    assert p.speed == 1024 * 1024 * 2
    assert p.eta == 3
    assert p.downloaded == 1024 * 1024
    assert p.total == 1024 * 1024 * 4
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_core_download.py::test_progress_carries_speed_eta_and_size -v`
Expected: FAIL - the hook calls `progress(int)` today, so `seen[0]` is an int, not a `Progress`.

- [ ] **Step 3: Emit a `Progress` from the hook**

In `core/download.py`, add the import near the top:

```python
from core.progress import Progress
```

In the `hook` function, replace the `progress` block with:

```python
            if progress:
                if d.get("status") == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate")
                    downloaded = int(d.get("downloaded_bytes", 0) or 0)
                    pct = int(downloaded / total * 100) if total else 0
                    progress(Progress(
                        percent=pct,
                        speed=d.get("speed"),
                        eta=d.get("eta"),
                        downloaded=downloaded,
                        total=total,
                    ))
                elif d.get("status") == "finished":
                    progress(Progress(percent=100, speed=None, eta=None,
                                      downloaded=0, total=None))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_core_download.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, 438 passed.

- [ ] **Step 6: Commit**

```bash
git add core/download.py tests/test_core_download.py
git commit -m "feat(download): emit a Progress with speed, eta, and size"
```

---

### Task 3: Carry `Progress` to both UIs

**Files:**
- Modify: `workers/download_worker.py`, `workers/queue_worker.py`, `ui/single_tab.py`, `ui/batch_tab.py`
- Test: offscreen construction checks

**Interfaces:**
- Consumes: `Progress` (Task 1), the hook (Task 2), `format_progress` (Task 1).
- Produces:
  - `DownloadWorker.progress_signal = pyqtSignal(object)` (a `Progress`).
  - `QueueWorker.progress_signal = pyqtSignal(str, object)` (`job_id`, `Progress`).

- [ ] **Step 1: Widen the Download worker's signal**

In `workers/download_worker.py`, change the signal:

```python
    progress_signal = QtCore.pyqtSignal(object)  # a core.progress.Progress
```

`progress=self.progress_signal.emit` in the `download_one(...)` call is unchanged.

- [ ] **Step 2: Widen the Queue worker's signal**

In `workers/queue_worker.py`, change the signal and the lambda:

```python
    progress_signal = QtCore.pyqtSignal(str, object)  # (job_id, Progress)
```

```python
            progress=lambda p: self.progress_signal.emit(job.id, p),
```

- [ ] **Step 3: Render it on the Download tab**

In `ui/single_tab.py`, add a label under the progress bar (beside `self.progress_bar`), e.g.:

```python
        self.progress_label = QtWidgets.QLabel("")
        self.progress_label.setAccessibleName("Download progress detail")
```

and replace the connection `self.worker.progress_signal.connect(self.progress_bar.setValue)` with `self.worker.progress_signal.connect(self._on_progress)`, adding:

```python
    def _on_progress(self, p):
        from core.progress import format_progress
        self.progress_bar.setValue(int(p.percent))
        self.progress_label.setText(format_progress(p))
```

Reset `self.progress_label.setText("")` wherever the bar is reset to 0.

- [ ] **Step 4: Render it on the Queue tab**

In `ui/batch_tab.py`, replace `_on_progress`:

```python
    def _on_progress(self, job_id, p):
        from core.progress import format_progress
        row = self._row_for_id.get(job_id)
        if row is not None:
            self._set_row_status(row, "running", format_progress(p))
```

`_update_overall_progress` is unchanged (percent only).

- [ ] **Step 5: Verify construction offscreen**

Run:
```bash
python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PyQt5 import QtWidgets; from ui.batch_tab import QueueTab; app=QtWidgets.QApplication([]); t=QueueTab({'path':''}); from core.progress import Progress; t._on_progress('nope', Progress(50, 1024*1024*2, 5, 1024, 2048)); print('ok')"
```
Expected: prints `ok` (an unknown job id is a safe no-op).

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, 438 passed.

- [ ] **Step 7: Commit**

```bash
git add workers/download_worker.py workers/queue_worker.py ui/single_tab.py ui/batch_tab.py
git commit -m "feat(ui): show speed, ETA, and size in the progress display"
```

---

### Task 4: Documentation

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `AGENTS.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: README**

Note that the progress display shows speed, ETA, and downloaded/total size on the Download tab and in each queue row.

- [ ] **Step 2: CHANGELOG - Unreleased `### Added`**

Add: progress now shows speed, ETA, and size.

- [ ] **Step 3: AGENTS.md**

Add one line: the progress payload is a `core.progress.Progress` (`percent`, `speed`, `eta`, `downloaded`, `total`); `format_progress` renders it; both workers' `progress_signal` carry it.

- [ ] **Step 4: Run the suite once**

Run: `python -m pytest -q`
Expected: PASS, 438 passed.

- [ ] **Step 5: Commit**

```bash
git add README.md CHANGELOG.md AGENTS.md
git commit -m "docs: download speed, ETA, and size"
```

---

## Self-Review

- **Spec coverage:** `core/progress.py` + formatters (Task 1), the hook emitting `Progress` (Task 2), both workers' signals + both UIs (Task 3), docs (Task 4). `None` handling and the no-trailing-separator rule are pinned by Task 1 tests. The Queue's overall bar stays percent only (Task 3 leaves `_update_overall_progress` unchanged).
- **Placeholder scan:** none; every code step carries real code.
- **Type consistency:** `Progress(percent, speed, eta, downloaded, total)` identical across Tasks 1/2/3; `format_progress` identical across Tasks 1/3; `progress_signal(object)` and `progress_signal(str, object)` match Task 3's consumers.
- **Note:** Task 2 changes the hook's payload, and Task 3 updates its consumers. Between the two, running the GUI would mis-handle progress; the test suite stays green throughout (workers' fakes ignore `progress`, and no GUI test drives a real hook). The two tasks are adjacent in execution.
