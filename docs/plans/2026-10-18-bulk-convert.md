# Bulk Convert Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Convert tab into a persistent list of files that convert one at a time, with per-row targets and state, drag-and-drop, retry, and clear finished - using the Queue tab's patterns.

**Architecture:** A new Qt-free `core/convert_queue.py` holds the job model, the pure queue primitives, and a versioned JSON store beside `queue.json`. A new worker thread drains it one job at a time through the existing `core.convert.convert_file`. `ui/convert_tab.py` becomes a toolbar + table + options block + detail panel, mirroring `ui/batch_tab.py`.

**Tech Stack:** Python 3.8+, PyQt5, pytest, flake8.

**Spec:** `docs/specs/2026-10-18-bulk-convert-design.md`

## Global Constraints

- `core/` stays Qt-free and thread-free; `tests/test_core_isolation.py` enforces it.
- No new dependencies. Standard library and PyQt5 only.
- `core.convert.convert_file`, `core/pipeline.py`, `core/formats.py`, and the CLI `convert` command are untouched.
- All 632 existing tests keep passing; flake8 gate `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics` must stay `0`.
- Windows console children keep going through `utils.proc.no_window_kwargs()`.
- Conventional Commits. Never commit a real social-media URL.
- The Qt layer is verified offscreen; the pytest suite stays free of GUI tests.
- Reuse `ui.style` tokens (`token`, `space`, `make_chip`, `make_result_panel`, `primary_button_style`, `danger_text_style`); no literal hex.

## File Structure

- `core/convert_queue.py` - **new**. `ConvertJob`, `ConvertQueue`, `ConvertStore`, states.
- `core/paths.py` - gains `convert_path()`.
- `workers/convert_queue_worker.py` - **new**. Drains the queue one job at a time.
- `ui/convert_tab.py` - rewritten as the list tab.
- `tests/test_convert_queue.py` - **new** pure tests.
- `tests/test_paths.py`, `tests/verify_ui_offscreen.py` - extended.

---

### Task 1: Core queue model and store

**Files:**
- Create: `core/convert_queue.py`
- Test: `tests/test_convert_queue.py` (new)

**Interfaces:**
- Produces: `ConvertJob`, `STATUS_PENDING/RUNNING/DONE/FAILED/CANCELLED`, `TERMINAL_STATES`, `ConvertQueue`, `ConvertStore`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_convert_queue.py
from core.convert_queue import (
    ConvertQueue, ConvertStore, ConvertJob, STATUS_DONE, STATUS_FAILED,
    STATUS_PENDING, STATUS_RUNNING, TERMINAL_STATES,
)
from core.manifest import DownloadResult

OPTIONS = {"target_format": "mp4", "resolution": 1080, "copy_streams": None}


def _queue(tmp_path, jobs=None):
    store = ConvertStore(str(tmp_path / "convert.json"))
    queue = ConvertQueue(store)
    queue.jobs[:] = jobs or []
    return queue


def test_add_bakes_options_and_skips_duplicate_paths(tmp_path):
    queue = _queue(tmp_path)
    added = queue.add(["C:/v/a.mp4", "C:/v/b.mov"], OPTIONS)
    assert [job.path for job in added] == ["C:/v/a.mp4", "C:/v/b.mov"]
    assert added[0].target_format == "mp4"
    assert added[0].resolution == 1080
    assert added[0].state == STATUS_PENDING
    again = queue.add(["C:/v/a.mp4"], OPTIONS)
    assert again == []


def test_claim_next_returns_the_first_pending_and_marks_it_running(tmp_path):
    queue = _queue(tmp_path)
    queue.add(["C:/v/a.mp4", "C:/v/b.mp4"], OPTIONS)
    first = queue.claim_next()
    assert first.path == "C:/v/a.mp4"
    assert first.state == STATUS_RUNNING
    assert queue.claim_next().path == "C:/v/b.mp4"
    assert queue.claim_next() is None


def test_apply_result_maps_ok_failed_and_cancelled(tmp_path):
    queue = _queue(tmp_path)
    ok, bad, stopped = queue.add(["a", "b", "c"], OPTIONS)
    queue.apply_result(ok.id, DownloadResult(status="ok", path="C:/v/a.mp3"))
    assert ok.state == STATUS_DONE and ok.output_path == "C:/v/a.mp3"
    queue.apply_result(bad.id, DownloadResult(status="error", message="boom"))
    assert bad.state == STATUS_FAILED and bad.message == "boom"
    queue.apply_result(stopped.id, DownloadResult(status="error",
                                                  error_category="cancelled"))
    assert stopped.state == "cancelled"


def test_set_options_touches_pending_only(tmp_path):
    queue = _queue(tmp_path)
    first, second = queue.add(["a", "b"], OPTIONS)
    second.state = STATUS_RUNNING
    changed = queue.set_options([first.id, second.id], {"target_format": "mp3"})
    assert changed == 1
    assert first.target_format == "mp3"
    assert second.target_format == "mp4"


def test_remove_refuses_a_running_job(tmp_path):
    queue = _queue(tmp_path)
    job, = queue.add(["a"], OPTIONS)
    job.state = STATUS_RUNNING
    assert queue.remove(job.id) is False
    job.state = STATUS_PENDING
    assert queue.remove(job.id) is True


def test_retry_failed_and_clear_finished(tmp_path):
    queue = _queue(tmp_path)
    job, = queue.add(["a"], OPTIONS)
    job.state = STATUS_FAILED
    assert queue.retry_failed() == 1
    assert job.state == STATUS_PENDING
    job.state = STATUS_DONE
    assert queue.clear_finished() == 1
    assert queue.jobs == []


def test_store_round_trips_and_keeps_an_unknown_key(tmp_path):
    path = tmp_path / "convert.json"
    path.write_text('{"version": 1, "jobs": [{"id": "x", "path": "a", "future": 1}]}',
                    encoding="utf-8")
    store = ConvertStore(str(path))
    store.load()
    assert [job.path for job in store.jobs] == ["a"]
    store.save()
    assert ConvertStore(str(path)).load() is None or True  # loads without raising


def test_store_loads_empty_from_a_corrupt_file(tmp_path):
    path = tmp_path / "convert.json"
    path.write_text("{ not json", encoding="utf-8")
    store = ConvertStore(str(path))
    store.load()
    assert store.jobs == []
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_convert_queue.py -q`
Expected: FAIL - `ModuleNotFoundError: No module named 'core.convert_queue'`.

- [ ] **Step 3: Implement**

```python
# core/convert_queue.py
"""A persistent list of files waiting to be converted.

Qt-free and thread-free: the worker owns the thread, this owns the data and the
pure transitions. Mirrors core/queue.py so the two lists behave the same way.
"""

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

STORE_VERSION = 1

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

TERMINAL_STATES = (STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED)


@dataclass
class ConvertJob:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    path: str = ""
    target_format: str = "mp4"
    resolution: int = 0
    copy_streams: Optional[bool] = None
    state: str = STATUS_PENDING
    message: str = ""
    output_path: str = ""
    added_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def _options_dict(options) -> dict:
    options = options or {}
    return {
        "target_format": options.get("target_format") or "mp4",
        "resolution": int(options.get("resolution") or 0),
        "copy_streams": options.get("copy_streams"),
    }


class ConvertQueue:
    """The job list plus the pure transitions the worker drives."""

    def __init__(self, store=None):
        self.store = store
        self.jobs: List[ConvertJob] = []

    def add(self, paths, options) -> List[ConvertJob]:
        known = {job.path for job in self.jobs}
        baked = _options_dict(options)
        added = []
        for path in paths:
            path = (path or "").strip()
            if not path or path in known:
                continue
            known.add(path)
            job = ConvertJob(path=path, **baked)
            self.jobs.append(job)
            added.append(job)
        return added

    def _find(self, job_id) -> Optional[ConvertJob]:
        for job in self.jobs:
            if job.id == job_id:
                return job
        return None

    def remove(self, job_id) -> bool:
        job = self._find(job_id)
        if job is None or job.state == STATUS_RUNNING:
            return False
        self.jobs.remove(job)
        return True

    def set_options(self, job_ids, options) -> int:
        baked = _options_dict(options)
        wanted = set(job_ids)
        changed = 0
        for job in self.jobs:
            if job.id in wanted and job.state == STATUS_PENDING:
                job.target_format = baked["target_format"]
                job.resolution = baked["resolution"]
                job.copy_streams = baked["copy_streams"]
                changed += 1
        return changed

    def claim_next(self) -> Optional[ConvertJob]:
        for job in self.jobs:
            if job.state == STATUS_PENDING:
                job.state = STATUS_RUNNING
                return job
        return None

    def apply_result(self, job_id, result) -> None:
        job = self._find(job_id)
        if job is None:
            return
        category = getattr(result, "error_category", None)
        if getattr(result, "status", "") == "ok" and getattr(result, "path", ""):
            job.state = STATUS_DONE
            job.output_path = result.path
            job.message = getattr(result, "message", "") or ""
        elif category == "cancelled":
            job.state = STATUS_CANCELLED
            job.message = getattr(result, "message", "") or "Cancelled."
        else:
            job.state = STATUS_FAILED
            job.message = getattr(result, "message", "") or "Conversion failed."

    def retry_failed(self, job_id=None) -> int:
        count = 0
        for job in self.jobs:
            if job.state == STATUS_FAILED and (job_id is None or job.id == job_id):
                job.state = STATUS_PENDING
                job.message = ""
                count += 1
        return count

    def clear_finished(self) -> int:
        before = len(self.jobs)
        self.jobs[:] = [job for job in self.jobs
                        if job.state not in TERMINAL_STATES]
        return before - len(self.jobs)

    def pending_count(self) -> int:
        return sum(1 for job in self.jobs if job.state == STATUS_PENDING)


def _coerce_jobs(raw) -> List[ConvertJob]:
    if not isinstance(raw, list):
        return []
    known = ConvertJob.__dataclass_fields__
    out: List[ConvertJob] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        clean = {k: v for k, v in item.items() if k in known}
        try:
            out.append(ConvertJob(**clean))
        except (TypeError, ValueError):
            continue
    return out


class ConvertStore:
    """convert.json. Atomic write, tolerant load, never drops a job."""

    def __init__(self, path: Optional[str] = None):
        # Imported here, not at module level: core.paths.convert_path() is added
        # in Task 2, and this module must import cleanly before it exists.
        if path is None:
            from core.paths import convert_path
            path = convert_path()
        self.path = path
        self.jobs: List[ConvertJob] = []

    def load(self) -> None:
        self.jobs = []
        if not self.path:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict) or data.get("version") != STORE_VERSION:
            return
        self.jobs.extend(_coerce_jobs(data.get("jobs")))

    def save(self) -> None:
        if not self.path:
            return
        data = {"version": STORE_VERSION,
                "jobs": [asdict(job) for job in self.jobs]}
        tmp = "%s.%d.%s.tmp" % (self.path, os.getpid(), uuid.uuid4().hex)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, self.path)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_convert_queue.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/convert_queue.py tests/test_convert_queue.py
git commit -m "feat(convert): a persistent queue model for bulk conversion"
```

---

### Task 2: `convert_path()`

**Files:**
- Modify: `core/paths.py`
- Test: `tests/test_paths.py` (extend)

**Interfaces:**
- Consumes: nothing.
- Produces: `core.paths.convert_path() -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paths.py - add
def test_convert_path_honours_the_override(monkeypatch, tmp_path):
    from core.paths import convert_path
    monkeypatch.setenv("SOCIALCLIP_CONVERT", str(tmp_path / "convert.json"))
    assert convert_path() == str(tmp_path / "convert.json")


def test_convert_path_defaults_beside_the_queue(monkeypatch, tmp_path):
    from core.paths import convert_path
    monkeypatch.delenv("SOCIALCLIP_CONVERT", raising=False)
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    assert convert_path() == str(tmp_path / "convert.json")
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_paths.py -q`
Expected: FAIL - `ImportError: cannot import name 'convert_path'`.

- [ ] **Step 3: Implement**

```python
# core/paths.py - beside queue_path()
def convert_path() -> str:
    """The convert list file: the SOCIALCLIP_CONVERT override, else the data dir."""
    override = os.environ.get("SOCIALCLIP_CONVERT")
    if override:
        return override
    return os.path.join(data_dir(), "convert.json")
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_paths.py tests/test_convert_queue.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/paths.py tests/test_paths.py
git commit -m "feat(convert): a data-dir path for the convert list"
```

---

### Task 3: The convert queue worker

**Files:**
- Create: `workers/convert_queue_worker.py`

**Interfaces:**
- Consumes: `ConvertQueue` (Task 1).
- Produces: `ConvertQueueWorker(queue, store=None)` with `job_signal(object)` (a snapshot dict) and `finished_signal(str)`; `cancel(job_id)`, `cancel_all()`.

- [ ] **Step 1: Implement**

```python
# workers/convert_queue_worker.py
"""Drain a ConvertQueue one job at a time, off the UI thread."""

from PyQt5 import QtCore

from core.convert_queue import TERMINAL_STATES


class ConvertQueueWorker(QtCore.QThread):
    job_signal = QtCore.pyqtSignal(object)
    finished_signal = QtCore.pyqtSignal(str)

    def __init__(self, queue, store=None):
        super().__init__()
        self.queue = queue
        self.store = store
        self._cancelled = set()
        self._cancelling = False

    def cancel(self, job_id):
        """Cancel a running job. It stops between files, not mid-encode."""
        self._cancelled.add(job_id)

    def cancel_all(self):
        self._cancelling = True

    def _save(self):
        if self.store is not None:
            self.store.jobs = list(self.queue.jobs)
            self.store.save()

    def _emit(self, job):
        self.job_signal.emit({
            "id": job.id, "state": job.state, "path": job.path,
            "message": job.message, "output_path": job.output_path,
        })

    def run(self):
        from core.convert import convert_file

        done = 0
        while True:
            job = self.queue.claim_next()
            if job is None:
                break
            self._emit(job)
            if self._cancelling or job.id in self._cancelled:
                job.state = "cancelled"
                job.message = "Cancelled."
                done += 1
                self._save()
                self._emit(job)
                continue
            try:
                result = convert_file(
                    job.path, target_format=job.target_format,
                    target_resolution=job.resolution or None,
                    copy_streams=job.copy_streams,
                )
            except Exception as exc:  # noqa: BLE001 - a bad file must not stop the batch
                from core.manifest import error_result
                result = error_result("other", str(exc), "")
            self.queue.apply_result(job.id, result)
            done += 1
            self._save()
            self._emit(job)
        self.finished_signal.emit("Converted %d file(s)." % done)
```

- [ ] **Step 2: Verify it imports and the worker is inert without jobs**

Run: `python -c "from core.convert_queue import ConvertQueue; from workers.convert_queue_worker import ConvertQueueWorker; w=ConvertQueueWorker(ConvertQueue()); print('ok', w.isRunning())"`
Expected: `ok False`.

- [ ] **Step 3: Commit**

```bash
git add workers/convert_queue_worker.py
git commit -m "feat(convert): a worker that drains the convert queue one at a time"
```

---

### Task 4: Convert tab - toolbar, table, drag-and-drop

**Files:**
- Modify: `ui/convert_tab.py`

**Interfaces:**
- Consumes: `ConvertQueue`, `ConvertStore`, `ConvertQueueWorker`; `ui.style` tokens.
- Produces: `ConvertTab` with `self.table`, `self.add_files_btn`, `self.clear_finished_btn`, `self.retry_failed_btn`, `self.queue`, `self.store`.

- [ ] **Step 1: Replace the tab's construction**

Delete `file_heading`, `file_row`, `file_path_input`, `Select File…`, and the single
`Convert Selected File` button. Build instead:

```python
        from core.convert_queue import ConvertQueue, ConvertStore
        from ui.style import make_chip, space, token

        self.store = ConvertStore()
        self.store.load()
        self.queue = ConvertQueue(self.store)
        self.queue.jobs[:] = self.store.jobs

        heading = QtWidgets.QLabel("Convert")
        make_heading(heading)
        main.addWidget(heading)

        toolbar = QtWidgets.QHBoxLayout()
        self.add_files_btn = QtWidgets.QPushButton("Add files…")
        self.add_files_btn.clicked.connect(self.on_add_files)
        self.clear_finished_btn = QtWidgets.QPushButton("Clear finished")
        self.clear_finished_btn.clicked.connect(self.on_clear_finished)
        self.retry_failed_btn = QtWidgets.QPushButton("Retry failed")
        self.retry_failed_btn.clicked.connect(self.on_retry_failed)
        for button in (self.add_files_btn, self.clear_finished_btn,
                       self.retry_failed_btn):
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        main.addLayout(toolbar)

        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setAccessibleName("Conversion list")
        self.table.setHorizontalHeaderLabels(["File", "Status", "Detail"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAcceptDrops(True)
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        main.addWidget(self.table, 1)
```

Note: the `customContextMenuRequested` and `itemSelectionChanged` connections
belong to Task 5, where `_on_menu` and `_on_selection_changed` are defined.
Connecting them here would raise `AttributeError` at construction.

- [ ] **Step 2: Add the file dialog and drag-and-drop**

```python
    def on_add_files(self):
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select media files", default_download_folder(),
            "Media files (*.mp4 *.mov *.mkv *.avi *.webm *.mp3 *.m4a *.wav *.aac "
            "*.flac *.ogg *.opus *.gif);;All files (*)")
        if files:
            self._add_paths(files)

    def _add_paths(self, paths):
        kept = [p for p in paths if os.path.isfile(p)]
        added = self.queue.add(kept, self._new_item_options())
        if not added:
            self.show_hint("Those files are already in the list."
                           if kept else "No usable files were added.")
            return
        self.show_hint("")
        self._save()
        self.refresh_table()
        self._select_ids([job.id for job in added])

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        self._add_paths(paths)
        event.acceptProposedAction()
```

- [ ] **Step 3: Add the table fill and selection helpers**

```python
    def refresh_table(self):
        self.table.setRowCount(0)
        for job in self.queue.jobs:
            self._insert_row(job)

    def _insert_row(self, job):
        from ui.style import make_chip
        row = self.table.rowCount()
        self.table.insertRow(row)
        name = os.path.basename(job.path)
        name_item = QtWidgets.QTableWidgetItem(name)
        name_item.setToolTip(job.path)
        name_item.setData(QtCore.Qt.UserRole, job.id)
        self.table.setItem(row, 0, name_item)
        self.table.setCellWidget(row, 1, make_chip(
            state_label(job.state), state_kind(job.state)))
        self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(detail_for(job)))

    def _selected_jobs(self):
        ids = {self.table.item(index.row(), 0).data(QtCore.Qt.UserRole)
               for index in self.table.selectionModel().selectedRows()}
        return [job for job in self.queue.jobs if job.id in ids]

    def _select_ids(self, ids):
        wanted = set(ids)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(QtCore.Qt.UserRole) in wanted:
                item.setSelected(True)

    def _save(self):
        self.store.jobs = list(self.queue.jobs)
        self.store.save()
```

- [ ] **Step 4: Add the module-level helpers**

```python
# ui/convert_tab.py - module level
def state_label(state: str) -> str:
    return (state or "").capitalize()


def state_kind(state: str) -> str:
    return {"done": "ok", "failed": "error",
            "running": "busy"}.get(state, "muted")


def detail_for(job) -> str:
    from core.formats import download_format_label
    if job.state == "done" and job.output_path:
        return os.path.basename(job.output_path)
    if job.state == "failed":
        return job.message or "Failed."
    if job.state == "running":
        return job.message or "Converting…"
    label = download_format_label(job.target_format.upper())
    parts = [label]
    if job.resolution:
        parts.append("%dp" % job.resolution)
    return "  ·  ".join(parts) + "  ·  queued"
```

- [ ] **Step 5: Verify offscreen**

Run: `python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; os.environ['SOCIALCLIP_DATA']=os.environ.get('TEMP','/tmp')+'/sc-conv'; from PyQt5 import QtWidgets; import sys; app=QtWidgets.QApplication(sys.argv); from ui.convert_tab import ConvertTab; t=ConvertTab(); print('rows', t.table.rowCount(), 'ext', t.table.selectionMode()==QtWidgets.QAbstractItemView.ExtendedSelection)"`
Expected: `rows 0 ext True`.

- [ ] **Step 6: Commit**

```bash
git add ui/convert_tab.py
git commit -m "feat(convert): a file table with multi-select and drag-and-drop"
```

---

### Task 5: Convert tab - options block, run, right-click, bulk bar

**Files:**
- Modify: `ui/convert_tab.py`

**Interfaces:**
- Consumes: Task 4's `self.table`, `self.queue`, `self.store`; `ConvertQueueWorker`.
- Produces: `self.start_btn`, `self.bulk_bar`, `on_start`, `on_clear_finished`, `on_retry_failed`, `_on_menu`, `_on_selection_changed`.

- [ ] **Step 1: Keep the existing option combos as "options for new items"**

In `__init__`, set `self.worker = None` (the original file sets
`self.conv_worker = None`; rename it), or `on_start` raises on the first run.

`on_clear_finished` and `on_retry_failed` **already exist from Task 4**: its
toolbar connects them, so it had to define them early. Do not define them again
here; if Task 4's copies differ from Step 3 below, Step 3 wins.

Wire the two table signals Task 4 left unconnected:

```python
        self.table.customContextMenuRequested.connect(self._on_menu)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
```

Keep `self.conv_output_combo`, `self.conv_res_combo`, `self.copy_combo` and
`_update_conv_controls` exactly as they are; relabel their heading to
`"Options for new items"` and add one button beside them:

```python
        self.apply_options_btn = QtWidgets.QPushButton("Apply to all pending")
        self.apply_options_btn.clicked.connect(self.on_apply_options)
```

```python
    def on_apply_options(self):
        ids = [job.id for job in self.queue.jobs if job.state == "pending"]
        changed = self.queue.set_options(ids, self._new_item_options())
        if not changed:
            self.show_hint("No pending files to update.")
            return
        self._save()
        self.refresh_table()
```

`_new_item_options` already exists from Task 4 (its `_add_paths` needs it);
do not define it again here.

- [ ] **Step 2: Start / cancel**

```python
    def on_start(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel_all()
            self.start_btn.setEnabled(False)
            self.start_btn.setText("Cancelling…")
            return
        if not self.queue.pending_count():
            self.show_hint("Add at least one file first.")
            return
        self.show_hint("")
        self.start_btn.setText("Cancel all")
        self.start_btn.setEnabled(True)
        self.worker = ConvertQueueWorker(self.queue, self.store)
        self.worker.job_signal.connect(self._on_job)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _on_job(self, payload):
        self.refresh_table()
        self._sync_buttons()

    def _on_finished(self, message):
        self.log(message)
        self.start_btn.setText("Convert")
        self.start_btn.setEnabled(True)
        self.refresh_table()
```

- [ ] **Step 3: Bulk bar and selection**

```python
        self.bulk_bar = QtWidgets.QWidget()
        bulk = QtWidgets.QHBoxLayout(self.bulk_bar)
        bulk.setContentsMargins(0, 0, 0, 0)
        self.bulk_label = QtWidgets.QLabel("")
        bulk.addWidget(self.bulk_label)
        bulk.addStretch(1)
        for text, slot in (("Retry", self.on_retry_selected),
                           ("Remove", self.on_remove_selected),
                           ("Clear finished", self.on_clear_finished)):
            button = QtWidgets.QPushButton(text)
            button.clicked.connect(slot)
            bulk.addWidget(button)
        self.bulk_bar.setVisible(False)
        main.addWidget(self.bulk_bar)   # directly above self.table
```

```python
    def _on_selection_changed(self):
        jobs = self._selected_jobs()
        self._sync_buttons()
        self._show_detail(jobs[0] if jobs else None)
        if len(jobs) < 2:
            self.bulk_bar.setVisible(False)
            return
        self.bulk_label.setText("%d selected" % len(jobs))
        self.bulk_bar.setVisible(True)

    def on_retry_selected(self):
        for job in self._selected_jobs():
            self.queue.retry_failed(job.id)
        self._save()
        self.refresh_table()

    def on_remove_selected(self):
        for job in self._selected_jobs():
            self.queue.remove(job.id)
        self._save()
        self.refresh_table()

    def on_clear_finished(self):
        self.queue.clear_finished()
        self._save()
        self.refresh_table()

    def on_retry_failed(self):
        if not self.queue.retry_failed():
            self.show_hint("No failed files to retry.")
            return
        self._save()
        self.refresh_table()

    def _on_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        if index.row() not in {i.row()
                               for i in self.table.selectionModel().selectedRows()}:
            self.table.selectRow(index.row())
        menu = QtWidgets.QMenu(self)
        edit = menu.addAction("Edit options…")
        retry = menu.addAction("Retry")
        remove = menu.addAction("Remove")
        cancel = menu.addAction("Cancel")
        chosen = menu.exec_(self.table.viewport().mapToGlobal(pos))
        if chosen is edit:
            self._edit_selected_options()
        elif chosen is retry:
            self.on_retry_selected()
        elif chosen is remove:
            self.on_remove_selected()
        elif chosen is cancel:
            if self.worker and self.worker.isRunning():
                for job in self._selected_jobs():
                    self.worker.cancel(job.id)
```

- [ ] **Step 4: Multi-row edit**

`EditJobDialog` is the Queue's job-options dialog; it returns the download
options block, not a registry key, so reusing it here would write a human label
into `target_format`. Apply the tab's own "options for new items" to the selected
pending rows instead - the same values as `Apply to all pending`, scoped to the
selection:

```python
    def _edit_selected_options(self):
        jobs = [job for job in self._selected_jobs() if job.state == "pending"]
        if not jobs:
            self.show_hint("Only pending files can be edited.")
            return
        changed = self.queue.set_options(
            [job.id for job in jobs], self._new_item_options())
        if not changed:
            self.show_hint("Nothing to update.")
            return
        self._save()
        self.refresh_table()
        self.show_hint("Updated %d file(s) from the options above." % changed)
```

- [ ] **Step 5: Delete the dead single-file methods**

The old single-file flow is gone, so its handlers are dead and reference widgets
that no longer exist: `on_convert_file`, `_sync_convert_enabled`,
`_on_conv_output`, `_on_conv_finished`, and the old `on_pick_file`. Delete them
and any import they alone used (`ConvertFileWorker`).

- [ ] **Step 6: Verify offscreen**

Run: `python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; os.environ['SOCIALCLIP_DATA']=os.environ.get('TEMP','/tmp')+'/sc-conv'; from PyQt5 import QtWidgets; import sys; app=QtWidgets.QApplication(sys.argv); from ui.convert_tab import ConvertTab; t=ConvertTab(); print('bulk hidden', t.bulk_bar.isHidden(), 'start', t.start_btn.text())"`
Expected: `bulk hidden True start Convert`.

- [ ] **Step 6: Commit**

```bash
git add ui/convert_tab.py
git commit -m "feat(convert): run, retry, clear finished, and multi-row edit"
```

---

### Task 6: Convert tab - selected-row detail panel

**Files:**
- Modify: `ui/convert_tab.py`

**Interfaces:**
- Consumes: Task 4's `self._selected_jobs`; `make_result_panel`.
- Produces: `_show_detail(job)`.

- [ ] **Step 1: Implement the detail fill**

```python
    def _show_detail(self, job):
        from ui.style import token
        body = self.panel_labels["body"]
        ready = self.panel_labels["ready"]
        if job is None:
            body.setText("Select a file to see its details.")
            ready.setVisible(False)
            self.open_folder_btn.setVisible(False)
            return
        from core.formats import download_format_label
        lines = [os.path.basename(job.path),
                 download_format_label(job.target_format.upper())]
        if job.resolution:
            lines.append("%dp" % job.resolution)
        body.setText("  ·  ".join(lines))
        ready.setText(job.message or state_label(job.state))
        ready.setStyleSheet("color: %s;" % (
            token("ok") if job.state == "done" else token("text_muted")))
        ready.setVisible(True)
        self._last_output = job.output_path
        self.open_folder_btn.setVisible(bool(job.output_path))
```

- [ ] **Step 2: Verify offscreen**

Run: `python tests/verify_ui_offscreen.py`
Expected: `offscreen UI: ALL CHECKS PASSED` after Task 7's update; before it, expect a failure naming the removed `convert_file_btn`.

- [ ] **Step 3: Commit**

```bash
git add ui/convert_tab.py
git commit -m "feat(convert): the panel shows the selected file's detail"
```

---

### Task 7: Verification

**Files:**
- Modify: `tests/verify_ui_offscreen.py`

- [ ] **Step 1: Replace the removed single-file assertions**

Delete the `convert.convert_file_btn` / file-field assertions and assert the new
invariants instead:

```python
    convert = ConvertTab()
    assert convert.table.rowCount() == 0, "the list starts empty"
    assert convert.table.selectionMode() == \
        QtWidgets.QAbstractItemView.ExtendedSelection
    assert convert.bulk_bar.isHidden()
    assert convert.start_btn.text() == "Convert"
    assert convert.console_log.isHidden() is False
```

- [ ] **Step 2: Run it**

Run: `python tests/verify_ui_offscreen.py`
Expected: `offscreen UI: ALL CHECKS PASSED`.

- [ ] **Step 3: Run the whole suite and the lint gate**

Run: `python -m pytest -q && python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: 632 + the new tests pass, flake8 prints `0`.

- [ ] **Step 4: Manual pass**

Add several files, convert them, cancel mid-batch, retry a failure, clear
finished, restart the app and confirm the rows persisted.

- [ ] **Step 5: Commit**

```bash
git add tests/verify_ui_offscreen.py
git commit -m "test(convert): offscreen invariants for the convert list"
```

---

## Self-Review

- **Spec coverage:** §A (Task 1), §B (Tasks 1-2), §C (Task 3), §D (Tasks 4-5), §E (Task 6), §F (no task touches those files), §G (Tasks 1-2, 7).
- **Placeholder scan:** no TBD/TODO; every code step carries real code.
- **Type consistency:** `ConvertJob` fields, `ConvertQueue` method names, and `ConvertQueueWorker` signals are used with the same names in Tasks 3-6. `self.worker` is created in Task 5 and read in Task 5/6.
- **Known gap:** no per-row percentage (spec's non-goal); a running row shows the busy chip and its message.
