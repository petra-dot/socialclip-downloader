# Concurrency (Parallel Queue Downloads) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Queue run up to N downloads at once (default 3, range 1-8) in both the GUI and the CLI.

**Architecture:** `core/queue.py` gains two pure primitives, `claim_next()` and `apply_result()`, split out of `run_once` so a concurrent caller can claim and apply under its own lock; core stays thread-free. The GUI worker and the CLI each own a `ThreadPoolExecutor(max_workers=N)` loop. Each running job carries its own cancel `Event`.

**Tech Stack:** Python 3.8+, PyQt5 (GUI), `concurrent.futures` + `threading` (stdlib, no new dependency).

**Spec:** `docs/specs/2026-10-15-concurrency-design.md`

## Global Constraints

- Python 3.8+; **no new runtime dependencies** (`concurrent.futures` and `threading` are stdlib).
- `core/` stays **Qt-free and thread-free** (enforced by `tests/test_core_isolation.py`). No locks, no threads, no PyQt in `core/queue.py`.
- The suite must stay green: `python -m pytest -q` (baseline 390 passing).
- Lint prints 0: `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`
- Conventional Commits. **Never commit a real social-media URL** (use `https://a.com/1`, `https://youtu.be/x`). **Never push** without explicit approval.
- `run_once`'s signature and behaviour are unchanged; its existing tests must keep passing.

---

### Task 1: Core split - `claim_next` and `apply_result`

**Files:**
- Modify: `core/queue.py:149-183`
- Test: `tests/test_queue.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `Queue.claim_next() -> Optional[QueueJob]` - first pending job marked `running` with `attempts += 1`; `None` when paused or empty.
  - `Queue.apply_result(job: QueueJob, result: Optional[DownloadResult]) -> QueueJob` - maps a finished run onto the job's terminal state.
  - `Queue.run_once(executor)` - unchanged signature/behaviour, now `claim_next` + executor + `apply_result`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_queue.py`:

```python
def test_claim_next_marks_running_and_counts_attempt():
    q = Queue()
    job = q.add("https://a.com/1", {})
    claimed = q.claim_next()
    assert claimed is job
    assert job.state == "running"
    assert job.attempts == 1
    assert q.claim_next() is None


def test_claim_next_returns_none_when_paused():
    q = Queue()
    q.add("https://a.com/1", {})
    q.pause()
    assert q.claim_next() is None


def test_apply_result_ok_sets_done_fields():
    q = Queue()
    job = q.add("https://a.com/1", {})
    job.state = "running"
    result = DownloadResult(status="ok", url=job.url, path="C:/out.mp4",
                            bytes=10, height=1080, message="done")
    q.apply_result(job, result)
    assert job.state == "done"
    assert job.path == "C:/out.mp4"
    assert job.bytes == 10
    assert job.height == 1080
    assert job.message == "done"


def test_apply_result_cancelled():
    q = Queue()
    job = q.add("https://a.com/1", {})
    job.state = "running"
    result = DownloadResult(status="error", error_category="cancelled",
                            message="Cancelled.")
    q.apply_result(job, result)
    assert job.state == "cancelled"


def test_apply_result_generic_failure():
    q = Queue()
    job = q.add("https://a.com/1", {})
    job.state = "running"
    result = DownloadResult(status="error", error_category="network",
                            message="No network.")
    q.apply_result(job, result)
    assert job.state == "failed"
    assert job.message == "No network."


def test_apply_result_non_result_is_failed():
    q = Queue()
    job = q.add("https://a.com/1", {})
    job.state = "running"
    q.apply_result(job, None)
    assert job.state == "failed"
    assert job.message == "executor returned no result"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_queue.py -k "claim_next or apply_result" -v`
Expected: FAIL with `AttributeError: 'Queue' object has no attribute 'claim_next'` (and `apply_result`).

- [ ] **Step 3: Split `run_once` into `claim_next` + `apply_result`**

In `core/queue.py`, replace the whole `run_once` method (currently lines 149-183) with these three methods:

```python
    def claim_next(self) -> Optional[QueueJob]:
        """Take the first pending job: mark it running, count the attempt.

        The caller owns any locking; a concurrent caller must serialize this
        and apply_result against the shared job list.
        """
        if self.paused:
            return None
        job = self.next_pending()
        if job is None:
            return None
        job.state = "running"
        job.attempts += 1
        return job

    def apply_result(
        self, job: QueueJob, result: Optional[DownloadResult]
    ) -> QueueJob:
        """Map a finished run onto the job's terminal state."""
        if not isinstance(result, DownloadResult):
            job.state = "failed"
            job.message = "executor returned no result"
            return job
        if result.status == "ok":
            job.state = "done"
            job.path = result.path
            job.bytes = result.bytes or 0
            job.height = result.height or 0
            if result.message:
                job.message = result.message
        elif result.error_category == "cancelled":
            job.state = "cancelled"
            if result.message:
                job.message = result.message
        else:
            job.state = "failed"
            job.message = result.message or ""
        return job

    def run_once(
        self, executor: Callable[[QueueJob], Optional[DownloadResult]]
    ) -> Optional[QueueJob]:
        job = self.claim_next()
        if job is None:
            return None
        try:
            result = executor(job)
        except Exception as exc:  # noqa: BLE001 - never let a job crash the loop
            job.state = "failed"
            job.message = str(exc)
            return job
        return self.apply_result(job, result)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_queue.py -v`
Expected: PASS (all new tests, plus every pre-existing `test_run_once_*` test).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, 396 passed (390 + 6 new).

- [ ] **Step 6: Commit**

```bash
git add core/queue.py tests/test_queue.py
git commit -m "refactor(queue): split claim_next and apply_result out of run_once"
```

---

### Task 2: Concurrent GUI worker

**Files:**
- Modify: `workers/queue_worker.py` (whole file)
- Modify: `ui/batch_tab.py` (two seam lines: `_on_progress` signature, `on_cancel_current` call)
- Test: `tests/test_queue_worker.py`

**Interfaces:**
- Consumes: `Queue.claim_next()`, `Queue.apply_result(job, result)` (Task 1).
- Produces:
  - `QueueWorker(queue, jobs=3)` - `jobs` clamped to 1-8.
  - `QueueWorker.progress_signal = pyqtSignal(str, int)` - `(job_id, percent)`. **Changed arity.**
  - `QueueWorker.cancel_job(job_id)` - set one running job's cancel event.
  - `QueueWorker.cancel_all()` - set every event and mark every non-terminal job cancelled.
  - `QueueWorker.cancel_current` is **removed** (was one shared event).

- [ ] **Step 1: Update the worker tests first**

Rewrite `tests/test_queue_worker.py` so the sequential tests pin `jobs=1` and the cancel test uses the new API, and add a concurrency test. Replace the file's body with:

```python
import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets  # noqa: E402

from core.manifest import DownloadResult  # noqa: E402
from core.queue import Queue  # noqa: E402
from ui.batch_tab import build_job_options  # noqa: E402
from workers.queue_worker import QueueWorker  # noqa: E402


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_worker_drains_queue_and_emits_states(monkeypatch):
    _app()
    q = Queue()
    q.add("https://a.com/1", {})
    q.add("https://b.com/2", {})

    def fake_download_one(url, **kw):
        return DownloadResult(status="ok", url=url, path="C:/o.mp4", message="ok")

    monkeypatch.setattr("workers.queue_worker.download_one", fake_download_one)

    seen = []
    worker = QueueWorker(q)
    worker.job_signal.connect(lambda jid, state, job: seen.append(state))
    worker.run()

    assert seen.count("running") == 2
    assert seen.count("done") == 2
    assert all(j.state == "done" for j in q.jobs)


def test_cancel_job_stops_only_that_job(monkeypatch):
    _app()
    q = Queue()
    a = q.add("https://a.com/1", {})
    q.add("https://b.com/2", {})

    worker = QueueWorker(q, jobs=1)

    def fake_download_one(url, **kw):
        if url.endswith("/1"):
            worker.cancel_job(a.id)
            assert kw["cancel"]() is True
            return DownloadResult(status="error", error_category="cancelled",
                                  url=url, message="Cancelled.")
        assert kw["cancel"]() is False
        return DownloadResult(status="ok", url=url, path="C:/o.mp4", message="ok")

    monkeypatch.setattr("workers.queue_worker.download_one", fake_download_one)
    worker.run()

    assert [j.state for j in q.jobs] == ["cancelled", "done"]


def test_executor_ignores_reserved_option_keys(monkeypatch):
    _app()
    q = Queue()
    q.add("https://a.com/1",
          {"cancel": "bogus", "progress": "bogus", "outtmpl": "tmpl"})

    captured = {}

    def fake_download_one(url, **kw):
        captured.update(kw)
        return DownloadResult(status="ok", url=url, path="C:/o.mp4", message="ok")

    monkeypatch.setattr("workers.queue_worker.download_one", fake_download_one)
    QueueWorker(q).run()

    assert q.jobs[0].state == "done"
    assert callable(captured["cancel"])
    assert callable(captured["progress"])
    assert captured["outtmpl"] == "tmpl"


def test_gui_options_match_real_download_one_signature(monkeypatch):
    _app()
    options = build_job_options("C:/out", "Video (MP4)", "1080", "")
    assert "output_dir" not in options

    q = Queue()
    q.add("https://a.com/1", options)

    def real_download_one(url, outtmpl, output_type, convert, target_resolution,
                          cookies_file=None, progress=None, cancel=None,
                          subtitles=False, embed_thumbnail=False, format_id=None):
        return DownloadResult(status="ok", url=url, path="C:/out/clip.mp4",
                              message="ok")

    monkeypatch.setattr("workers.queue_worker.download_one", real_download_one)
    QueueWorker(q).run()

    assert q.jobs[0].state == "done"


def test_pause_holds_thread_then_resume_finishes(monkeypatch):
    _app()
    q = Queue()
    q.add("https://a.com/1", {})
    q.add("https://b.com/2", {})

    worker = QueueWorker(q, jobs=1)

    def fake_download_one(url, **kw):
        if url.endswith("/1"):
            worker.pause()
        return DownloadResult(status="ok", url=url, path="C:/o.mp4", message="ok")

    monkeypatch.setattr("workers.queue_worker.download_one", fake_download_one)
    worker.start()

    deadline = time.time() + 5
    while time.time() < deadline and q.jobs[0].state != "done":
        time.sleep(0.02)

    assert q.jobs[0].state == "done"
    assert q.jobs[1].state == "pending"
    assert worker.isRunning()

    worker.resume()
    assert worker.wait(5000)
    assert [j.state for j in q.jobs] == ["done", "done"]


def test_cancel_all_while_paused_terminates(monkeypatch):
    _app()
    q = Queue()
    q.add("https://a.com/1", {})
    q.add("https://b.com/2", {})

    worker = QueueWorker(q, jobs=1)
    worker.pause()
    worker.cancel_all()
    worker.start()

    assert worker.wait(5000)
    assert [j.state for j in q.jobs] == ["cancelled", "cancelled"]


def test_running_emit_is_not_retroactively_mutated(monkeypatch):
    _app()
    captured = []

    def fake_download_one(url, **kw):
        return DownloadResult(status="ok", url=url, path="C:/o.mp4", message="ok")

    monkeypatch.setattr("workers.queue_worker.download_one", fake_download_one)

    q = Queue()
    q.add("https://a.com/1", {})
    worker = QueueWorker(q)
    worker.job_signal.connect(lambda jid, state, job: captured.append((state, job)))
    worker.run()

    running_states = [job.state for (s, job) in captured if s == "running"]
    assert running_states and all(s == "running" for s in running_states), captured


def test_runs_up_to_jobs_at_once(monkeypatch):
    _app()
    q = Queue()
    for i in range(3):
        q.add("https://a.com/%d" % i, {})

    # A 3-party barrier releases only if all three run concurrently. Run
    # sequentially and the first wait() times out -> the job fails.
    barrier = threading.Barrier(3, timeout=5)

    def fake_download_one(url, **kw):
        barrier.wait()
        return DownloadResult(status="ok", url=url, path="C:/o.mp4", message="ok")

    monkeypatch.setattr("workers.queue_worker.download_one", fake_download_one)
    QueueWorker(q, jobs=3).run()

    assert all(j.state == "done" for j in q.jobs)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_queue_worker.py -v`
Expected: FAIL - `cancel_job` is missing, and `test_runs_up_to_jobs_at_once` fails because today's worker is sequential (the barrier times out).

- [ ] **Step 3: Rewrite the worker**

Replace all of `workers/queue_worker.py` with:

```python
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import replace

from PyQt5 import QtCore

from core.download import download_one
from core.queue import resolve_outtmpl

DEFAULT_JOBS = 3
MAX_JOBS = 8


class QueueWorker(QtCore.QThread):
    progress_signal = QtCore.pyqtSignal(str, int)  # (job_id, percent)
    job_signal = QtCore.pyqtSignal(str, str, object)  # (job_id, state, QueueJob)
    finished_signal = QtCore.pyqtSignal(str)

    def __init__(self, queue, jobs=DEFAULT_JOBS, parent=None):
        super().__init__(parent)
        self.queue = queue
        self.jobs = max(1, min(int(jobs), MAX_JOBS))
        self._cancel_events = {}
        self._lock = threading.Lock()

    def _executor(self, job):
        with self._lock:
            self.job_signal.emit(job.id, job.state, replace(job))
        event = self._cancel_events[job.id]
        opts = job.options or {}
        outtmpl = resolve_outtmpl(opts)
        return download_one(
            job.url,
            outtmpl=outtmpl,
            output_type=opts.get("output_type", "MP4"),
            convert=opts.get("convert", False),
            target_resolution=opts.get("target_resolution", 1080),
            cookies_file=opts.get("cookies_file"),
            cancel=event.is_set,
            progress=lambda pct: self.progress_signal.emit(job.id, pct),
            subtitles=opts.get("subtitles", "off"),
        )

    def _run_job(self, job):
        try:
            result = self._executor(job)
        except Exception as exc:  # noqa: BLE001 - one job must not kill the pool
            with self._lock:
                job.state = "failed"
                job.message = str(exc)
                self.job_signal.emit(job.id, job.state, replace(job))
                self.queue.store.save()
            return
        with self._lock:
            self.queue.apply_result(job, result)
            self.job_signal.emit(job.id, job.state, replace(job))
            self.queue.store.save()

    def run(self):
        with ThreadPoolExecutor(max_workers=self.jobs) as pool:
            pending = set()
            while True:
                if not self.queue.paused:
                    while len(pending) < self.jobs:
                        job = self.queue.claim_next()
                        if job is None:
                            break
                        self._cancel_events[job.id] = threading.Event()
                        pending.add(pool.submit(self._run_job, job))
                if not pending:
                    if self.queue.paused and self.queue.next_pending() is not None:
                        self.msleep(100)
                        continue
                    break
                _done, pending = wait(pending, return_when=FIRST_COMPLETED)
        self.finished_signal.emit(self._summary())

    def _summary(self):
        jobs = self.queue.jobs
        done = sum(1 for j in jobs if j.state == "done")
        failed = sum(1 for j in jobs if j.state == "failed")
        cancelled = sum(1 for j in jobs if j.state == "cancelled")
        return f"Queue finished: {done} done, {failed} failed, {cancelled} cancelled"

    def pause(self):
        self.queue.pause()

    def resume(self):
        self.queue.resume()

    def cancel_job(self, job_id):
        event = self._cancel_events.get(job_id)
        if event is not None:
            event.set()

    def cancel_all(self):
        for event in list(self._cancel_events.values()):
            event.set()
        self.queue.cancel_all()
```

- [ ] **Step 4: Patch the two UI seam lines so the app keeps running**

In `ui/batch_tab.py`, change `_on_progress` (currently line 579-580) to accept the job id (it uses it in Task 3):

```python
    def _on_progress(self, job_id, percent):
        self.progress_bar.setValue(int(percent))
```

And in `on_cancel_current` (currently line 617-621) call `cancel_all`:

```python
    def on_cancel_current(self):
        if self.queue_worker and self.queue_worker.isRunning():
            self.queue_worker.cancel_all()
            self.cancel_current_btn.setEnabled(False)
            self.batch_log("Cancelling the current item...")
```

- [ ] **Step 5: Run the worker tests to verify they pass**

Run: `python -m pytest tests/test_queue_worker.py -v`
Expected: PASS (including `test_runs_up_to_jobs_at_once`).

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, 397 passed.

- [ ] **Step 7: Commit**

```bash
git add workers/queue_worker.py ui/batch_tab.py tests/test_queue_worker.py
git commit -m "feat(queue): run up to N downloads at once in the GUI worker"
```

---

### Task 3: Queue tab - concurrency control, per-row progress, Cancel all

**Files:**
- Modify: `ui/batch_tab.py`

**Interfaces:**
- Consumes: `QueueWorker(queue, jobs=)`, `progress_signal(str, int)`, `cancel_job(job_id)`, `cancel_all()` (Task 2).
- Produces: no new module interface (UI only).

- [ ] **Step 1: Add the "Downloads at once" spin box**

In `init_ui`, immediately before the `start_row` block (currently line 236), insert:

```python
        jobs_row = QtWidgets.QHBoxLayout()
        jobs_row.addWidget(QtWidgets.QLabel("Downloads at once:"))
        self.jobs_spin = QtWidgets.QSpinBox()
        self.jobs_spin.setAccessibleName("Queue concurrent downloads")
        self.jobs_spin.setRange(1, 8)
        self.jobs_spin.setValue(int(self.settings.value("queue/jobs", 3)))
        self.jobs_spin.valueChanged.connect(
            lambda v: self.settings.setValue("queue/jobs", int(v))
        )
        jobs_row.addWidget(self.jobs_spin)
        jobs_row.addStretch(1)
        queue_layout.addLayout(jobs_row)
```

- [ ] **Step 2: Rename the cancel button to "Cancel all"**

In `init_ui`, change the `start_row` cancel button (currently lines 244-247):

```python
        self.cancel_all_btn = QtWidgets.QPushButton("Cancel all")
        self.cancel_all_btn.setEnabled(False)
        self.cancel_all_btn.clicked.connect(self.on_cancel_all)
        start_row.addWidget(self.cancel_all_btn)
```

Then replace every other `self.cancel_current_btn` reference with `self.cancel_all_btn` (they are at the `_on_job` handler and `on_start_queue`/`on_queue_finished`; search the file for `cancel_current_btn`).

- [ ] **Step 3: Pass the chosen concurrency to the worker**

In `on_start_queue` (currently line 599), change the worker construction:

```python
        self.queue_worker = QueueWorker(self.queue, jobs=self.jobs_spin.value())
```

- [ ] **Step 4: Per-row progress and overall bar**

Replace `_on_progress` (from Task 2) with:

```python
    def _on_progress(self, job_id, percent):
        row = self._row_for_id.get(job_id)
        if row is not None:
            self._set_row_status(row, "running", "%d%%" % int(percent))
```

Replace `_on_job` (currently lines 560-577) and add the overall-progress helper; drop `_running_id` (remove `self._running_id = ""` from `__init__`):

```python
    def _on_job(self, job_id, state, job):
        row = self._row_for_id.get(job_id)
        if row is None:
            return
        if state == "done":
            detail = os.path.basename(job.path) if job.path else (job.message or "")
        else:
            detail = job.message or ""
        self._set_row_status(row, state, detail)
        self._update_overall_progress()

    def _update_overall_progress(self):
        total = len(self.queue.jobs)
        if not total:
            self.progress_bar.setValue(0)
            return
        finished = sum(1 for j in self.queue.jobs if j.state in TERMINAL_STATES)
        self.progress_bar.setValue(int(finished / total * 100))
```

- [ ] **Step 5: Replace `on_cancel_current` with `on_cancel_all`**

Replace the method from Task 2 with:

```python
    def on_cancel_all(self):
        if self.queue_worker and self.queue_worker.isRunning():
            self.queue_worker.cancel_all()
            self.cancel_all_btn.setEnabled(False)
            self.batch_log("Cancelling all running downloads...")
```

- [ ] **Step 6: Add "Cancel this download" to the running row's context menu**

In `on_table_context_menu` (currently lines 514-535), add the action and its handler:

```python
        cancel_this = menu.addAction("Cancel this download")
        cancel_this.setEnabled(job.state == "running")
        cancel_action = menu.addAction("Cancel")
        cancel_action.setEnabled(job.state == "pending")

        chosen = menu.exec_(self.batch_table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is remove_action:
            self.on_remove_job(job)
        elif chosen is cancel_action:
            self.on_cell_clicked(index.row(), 1)
        elif chosen is cancel_this:
            self._cancel_running_job(job)

    def _cancel_running_job(self, job):
        if self.queue_worker and self.queue_worker.isRunning():
            self.queue_worker.cancel_job(job.id)
            self.batch_log("Cancelling this download...")
```

- [ ] **Step 7: Verify construction and wiring offscreen**

Run:
```bash
python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PyQt5 import QtWidgets; from ui.batch_tab import QueueTab; app=QtWidgets.QApplication([]); t=QueueTab({'path':''}); print('spin', t.jobs_spin.value(), 'cancel', t.cancel_all_btn.text())"
```
Expected: prints `spin 3 cancel Cancel all`.

- [ ] **Step 8: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, 397 passed.

- [ ] **Step 9: Commit**

```bash
git add ui/batch_tab.py
git commit -m "feat(ui): concurrency control, per-row progress, and Cancel all on the queue"
```

---

### Task 4: CLI `queue run --jobs`

**Files:**
- Modify: `cli.py:262-291` (the `run` branch) and `cli.py:375-377` (the `run` parser)
- Test: `tests/test_cli_queue.py` (append)

**Interfaces:**
- Consumes: `Queue.claim_next()`, `Queue.apply_result()` (Task 1); `_queue_executor(job)` (existing).
- Produces: `socialclip queue run --jobs N` (int, default 3, choices 1-8).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_queue.py`:

```python
def test_queue_run_rejects_bad_jobs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(tmp_path / "q.json"))
    rc = cli.main(["queue", "run", "--jobs", "99"])
    assert rc == cli.EXIT_USAGE == 2
    assert "invalid choice" in capsys.readouterr().err
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_cli_queue.py::test_queue_run_rejects_bad_jobs -v`
Expected: FAIL - `--jobs` is unknown, so argparse exits with `unrecognized arguments`, and `"invalid choice"` is not in stderr.

- [ ] **Step 3: Add the `--jobs` argument**

In `build_parser`, change the `run` parser (currently lines 375-377):

```python
    qr = qsub.add_parser("run")
    qr.add_argument("--json", action="store_true")
    qr.add_argument("--jobs", type=int, default=3, choices=range(1, 9),
                    metavar="N")
    qr.set_defaults(func=_cmd_queue)
```

- [ ] **Step 4: Run the pool in the `run` branch**

Replace the `while True: queue.run_once(...)` loop (currently lines 272-284) with:

```python
        from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
        run = done = failed = cancelled = 0
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            pending = set()
            while True:
                while len(pending) < args.jobs:
                    job = queue.claim_next()
                    if job is None:
                        break
                    pending.add(pool.submit(_queue_executor, job))
                if not pending:
                    break
                finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in finished:
                    job = _apply_cli_result(queue, future)
                    queue.store.save()
                    run += 1
                    if job.state == "done":
                        done += 1
                    elif job.state == "failed":
                        failed += 1
                    elif job.state == "cancelled":
                        cancelled += 1
```

Add the helper just above `_cmd_queue`:

```python
def _apply_cli_result(queue, future):
    """Claimed job + its result -> applied job. Never raises."""
    job, result = future.result()
    return queue.apply_result(job, result)
```

Then make the submitted callable return `(job, result)`; replace `pool.submit(_queue_executor, job)` with a small wrapper. Define near `_queue_executor`:

```python
def _run_cli_job(job):
    try:
        return job, _queue_executor(job)
    except Exception as exc:  # noqa: BLE001 - one job must not kill the pool
        return job, error_result("other", str(exc), job.url)
```

with `from core.manifest import error_result` added to the imports at the top of the `run` branch (or module level). Submit `_run_cli_job` instead of `_queue_executor`.

- [ ] **Step 5: Run the CLI queue tests**

Run: `python -m pytest tests/test_cli_queue.py -v`
Expected: PASS (the new `--jobs` test plus every existing `queue run` test).

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, 398 passed.

- [ ] **Step 7: Commit**

```bash
git add cli.py tests/test_cli_queue.py
git commit -m "feat(cli): queue run --jobs"
```

---

### Task 5: Documentation

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `AGENTS.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: README - queue concurrency**

Under the Queue feature notes, add a short bullet: the Queue downloads up to 3 videos at once by default, adjustable 1-8 with the "Downloads at once" control (or `queue run --jobs N`), each running download showing its own progress and cancellable on its own.

- [ ] **Step 2: CHANGELOG - Unreleased `### Added`**

Add an entry: parallel queue downloads (default 3, 1-8), per-row progress, Cancel all.

- [ ] **Step 3: AGENTS.md - note the model**

Add one line: the Queue runs up to N downloads at once (`QueueWorker(queue, jobs=)` and `queue run --jobs`); the pool lives in `workers/queue_worker.py` and `cli.py`, and `core/queue.py` stays thread-free with `claim_next()`/`apply_result()` as the pure primitives.

- [ ] **Step 4: Run the suite once**

Run: `python -m pytest -q`
Expected: PASS, 398 passed.

- [ ] **Step 5: Commit**

```bash
git add README.md CHANGELOG.md AGENTS.md
git commit -m "docs: parallel queue downloads"
```

---

## Self-Review

- **Spec coverage:** scope (Tasks 2/4), default 3 range 1-8 (Tasks 2/3/4), UI per-row + overall + Cancel all (Task 3), CLI `--jobs` (Task 4), core split (Task 1), thread-free core (Task 1), docs (Task 5). Cancel semantics (Task 2). Known limitation (same-title collision) documented in the spec; not coded.
- **Placeholder scan:** none; every code step carries real code.
- **Type consistency:** `claim_next`/`apply_result` names and signatures identical across Tasks 1-4; `progress_signal(str, int)`, `cancel_job(job_id)`, `cancel_all()` identical across Tasks 2-3; `jobs=3`/1-8 consistent in Tasks 2, 3, 4.
