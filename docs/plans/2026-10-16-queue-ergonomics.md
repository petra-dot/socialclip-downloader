# Queue Ergonomics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Queue re-queue failed jobs and let the user edit a pending job's options.

**Architecture:** Two pure `core/queue.py` methods (`retry_failed`, `set_options`); a per-job `EditJobDialog`; a toolbar Retry button and two context-menu items; a CLI `queue retry`.

**Tech Stack:** Python 3.8+, PyQt5 (GUI).

**Spec:** `docs/specs/2026-10-16-queue-ergonomics-design.md`

## Global Constraints

- Python 3.8+; **no new dependencies**.
- `core/` stays **Qt-free and thread-free** (enforced by `tests/test_core_isolation.py`).
- The suite must stay green: `python -m pytest -q` (baseline 424 passing).
- Lint prints 0: `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`
- Conventional Commits. **Never commit a real social-media URL** (use `https://a.com/1`). **Never push** without approval.
- Retry touches `failed` only. Edit applies to `pending` only. `attempts` is kept on retry; the failure `message` is cleared.

---

### Task 1: `core/queue.py` - `retry_failed` and `set_options`

**Files:**
- Modify: `core/queue.py` (add two methods beside `remove_job`)
- Test: `tests/test_queue.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `Queue.retry_failed(job_id: Optional[str] = None) -> int` - re-queue `failed` jobs (one, or all) to `pending`, clear `message`, keep `attempts`; returns the count.
  - `Queue.set_options(job_id: str, options: dict) -> bool` - replace a `pending` job's options; False otherwise.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_queue.py`:

```python
def test_retry_failed_requeues_all_failed():
    q = Queue()
    a = q.add("https://a.com/1", {})
    b = q.add("https://b.com/2", {})
    c = q.add("https://c.com/3", {})
    a.state = "failed"
    a.message = "boom"
    a.attempts = 2
    b.state = "failed"
    c.state = "done"
    assert q.retry_failed() == 2
    assert a.state == "pending" and a.message == "" and a.attempts == 2
    assert b.state == "pending"
    assert c.state == "done"


def test_retry_failed_single_job():
    q = Queue()
    a = q.add("https://a.com/1", {})
    b = q.add("https://b.com/2", {})
    a.state = "failed"
    b.state = "failed"
    assert q.retry_failed(a.id) == 1
    assert a.state == "pending"
    assert b.state == "failed"


def test_retry_failed_leaves_other_states():
    q = Queue()
    for state in ("done", "cancelled", "skipped", "pending", "running"):
        job = q.add("https://a.com/1", {})
        job.state = state
    assert q.retry_failed() == 0


def test_set_options_replaces_a_pending_job():
    q = Queue()
    job = q.add("https://a.com/1", {"output_type": "MP4"})
    assert q.set_options(job.id, {"output_type": "MP3"}) is True
    assert job.options == {"output_type": "MP3"}


def test_set_options_refuses_non_pending():
    q = Queue()
    for state in ("running", "done", "failed", "cancelled", "skipped"):
        job = q.add("https://a.com/1", {})
        job.state = state
        assert q.set_options(job.id, {"x": 1}) is False


def test_set_options_unknown_id_returns_false():
    q = Queue()
    q.add("https://a.com/1", {})
    assert q.set_options("nope", {"x": 1}) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_queue.py -k "retry_failed or set_options" -v`
Expected: FAIL with `AttributeError: 'Queue' object has no attribute 'retry_failed'` (and `set_options`).

- [ ] **Step 3: Add the two methods**

In `core/queue.py`, add after `remove_job`:

```python
    def retry_failed(self, job_id: Optional[str] = None) -> int:
        """Re-queue failed jobs (one, or all). Returns how many changed.

        ``attempts`` is kept: it is a retry counter. The stale failure message
        is cleared so the row reads clean until the next run.
        """
        count = 0
        for job in self.jobs:
            if job.state != "failed":
                continue
            if job_id is not None and job.id != job_id:
                continue
            job.state = "pending"
            job.message = ""
            count += 1
        return count

    def set_options(self, job_id: str, options: dict) -> bool:
        """Replace a pending job's options. False for any other state."""
        for job in self.jobs:
            if job.id == job_id and job.state == "pending":
                job.options = dict(options)
                return True
        return False
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_queue.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, 430 passed.

- [ ] **Step 6: Commit**

```bash
git add core/queue.py tests/test_queue.py
git commit -m "feat(queue): retry failed jobs and set a pending job's options"
```

---

### Task 2: `ui/dialogs.py` - `EditJobDialog`

**Files:**
- Modify: `ui/dialogs.py` (append the class)
- Test: offscreen construction check

**Interfaces:**
- Consumes: `utils.file_utils.OUTPUT_FORMATS`, `RESOLUTIONS`, `output_index_for`.
- Produces: `EditJobDialog(parent, job)` with `chosen() -> dict` of raw fields (`save_dir`, `output_text`, `resolution`, `cookies_path`, `subtitles`).

- [ ] **Step 1: Add `EditJobDialog`**

In `ui/dialogs.py`, ensure `os` is imported (add `import os` at the top if absent), and append:

```python
class EditJobDialog(QtWidgets.QDialog):
    """Edit one pending queue job's options. Prefilled from its options dict."""

    def __init__(self, parent, job):
        super().__init__(parent)
        from utils.file_utils import OUTPUT_FORMATS, RESOLUTIONS, output_index_for

        opts = job.options or {}
        self.setWindowTitle("Edit job options")
        self.resize(520, 280)
        layout = QtWidgets.QVBoxLayout(self)

        fmt_row = QtWidgets.QHBoxLayout()
        fmt_row.addWidget(QtWidgets.QLabel("Output:"))
        self.output_combo = QtWidgets.QComboBox()
        self.output_combo.setAccessibleName("Edit job output format")
        self.output_combo.addItems(OUTPUT_FORMATS)
        index = output_index_for(opts.get("output_type", "MP4"))
        self.output_combo.setCurrentIndex(index if index >= 0 else 0)
        fmt_row.addWidget(self.output_combo)
        fmt_row.addWidget(QtWidgets.QLabel("Resolution:"))
        self.resolution_combo = QtWidgets.QComboBox()
        self.resolution_combo.setAccessibleName("Edit job target resolution")
        self.resolution_combo.addItems(RESOLUTIONS)
        self.resolution_combo.setCurrentText(str(opts.get("target_resolution", 1080)))
        fmt_row.addWidget(self.resolution_combo)
        fmt_row.addStretch(1)
        layout.addLayout(fmt_row)

        folder_row = QtWidgets.QHBoxLayout()
        folder_row.addWidget(QtWidgets.QLabel("Folder:"))
        self.folder_input = QtWidgets.QLineEdit(
            os.path.dirname(opts.get("outtmpl", "") or "")
        )
        self.folder_input.setAccessibleName("Edit job download folder")
        folder_row.addWidget(self.folder_input)
        browse = QtWidgets.QPushButton("Browse")
        browse.clicked.connect(self._browse)
        folder_row.addWidget(browse)
        layout.addLayout(folder_row)

        sub_row = QtWidgets.QHBoxLayout()
        sub_row.addWidget(QtWidgets.QLabel("Subtitles:"))
        self.subtitle_combo = QtWidgets.QComboBox()
        self.subtitle_combo.setAccessibleName("Edit job subtitle delivery")
        for value, label in (
            ("off", "Off"), ("sidecar", "Sidecar (.srt)"),
            ("embed", "Embed"), ("both", "Both"),
        ):
            self.subtitle_combo.addItem(label, value)
        saved = opts.get("subtitles", "off")
        sub_index = self.subtitle_combo.findData(saved)
        self.subtitle_combo.setCurrentIndex(sub_index if sub_index >= 0 else 0)
        sub_row.addWidget(self.subtitle_combo)
        sub_row.addStretch(1)
        layout.addLayout(sub_row)

        cookie_row = QtWidgets.QHBoxLayout()
        cookie_row.addWidget(QtWidgets.QLabel("Cookies file:"))
        self.cookies_input = QtWidgets.QLineEdit(opts.get("cookies_file", "") or "")
        self.cookies_input.setAccessibleName("Edit job cookies file path")
        self.cookies_input.setPlaceholderText("Optional: path to cookies.txt for auth")
        cookie_row.addWidget(self.cookies_input)
        layout.addLayout(cookie_row)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose folder", self.folder_input.text()
        )
        if folder:
            self.folder_input.setText(folder)

    def chosen(self) -> dict:
        return {
            "save_dir": self.folder_input.text().strip(),
            "output_text": self.output_combo.currentText(),
            "resolution": self.resolution_combo.currentText(),
            "cookies_path": self.cookies_input.text().strip(),
            "subtitles": self.subtitle_combo.currentData(),
        }
```

- [ ] **Step 2: Verify construction offscreen**

Run:
```bash
python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PyQt5 import QtWidgets; from ui.dialogs import EditJobDialog; from core.queue import QueueJob; app=QtWidgets.QApplication([]); j=QueueJob(url='u', options={'output_type':'MP3','target_resolution':720,'outtmpl':'C:/out/t.%(ext)s','subtitles':'both','cookies_file':'c.txt'}); d=EditJobDialog(None, j); print(d.chosen())"
```
Expected: prints a dict with `output_text` `Audio (MP3)`, `resolution` `720`, `save_dir` `C:/out`, `subtitles` `both`, `cookies_path` `c.txt`.

- [ ] **Step 3: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, 430 passed.

- [ ] **Step 4: Commit**

```bash
git add ui/dialogs.py
git commit -m "feat(ui): edit-job options dialog"
```

---

### Task 3: Queue tab - Retry button and context-menu actions

**Files:**
- Modify: `ui/batch_tab.py` (toolbar, `on_table_context_menu`, new handlers)
- Test: offscreen construction check

**Interfaces:**
- Consumes: `Queue.retry_failed`, `Queue.set_options` (Task 1); `EditJobDialog` (Task 2); existing `build_job_options`, `default_download_folder`.
- Produces: no new module interface (UI only).

- [ ] **Step 1: Add the toolbar button**

In `ui/batch_tab.py`, in `init_ui`, after the `clear_finished_btn` block, add:

```python
        self.retry_failed_btn = QtWidgets.QPushButton("Retry failed")
        self.retry_failed_btn.clicked.connect(self.on_retry_failed)
        urls_toolbar.addWidget(self.retry_failed_btn)
```

- [ ] **Step 2: Add the two handlers**

Add near `on_clear_finished`:

```python
    def on_retry_failed(self):
        count = self.queue.retry_failed()
        if not count:
            self.batch_log("No failed jobs to retry.")
            return
        self.queue.store.save()
        self.refresh_table()
        self.batch_log("Retrying %d failed job(s)." % count)

    def on_retry_job(self, job):
        if self.queue.retry_failed(job.id):
            self.queue.store.save()
            self.refresh_table()
            self.batch_log("Retrying one failed job.")

    def on_edit_job(self, job):
        from ui.dialogs import EditJobDialog
        dialog = EditJobDialog(self, job)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return
        fields = dialog.chosen()
        options = build_job_options(
            fields["save_dir"] or default_download_folder(),
            fields["output_text"], fields["resolution"],
            fields["cookies_path"], fields["subtitles"],
            (job.options or {}).get("cookies_from_browser", "") or "",
        )
        if self.queue.set_options(job.id, options):
            self.queue.store.save()
            self.refresh_table()
            self.batch_log("Updated the options for one job.")
```

- [ ] **Step 3: Add the context-menu actions**

In `on_table_context_menu`, add the two actions and their dispatch:

```python
        retry_action = menu.addAction("Retry")
        retry_action.setEnabled(job.state == "failed")
        edit_action = menu.addAction("Edit options...")
        edit_action.setEnabled(job.state == "pending")
```

and in the dispatch chain:

```python
        elif chosen is retry_action:
            self.on_retry_job(job)
        elif chosen is edit_action:
            self.on_edit_job(job)
```

- [ ] **Step 4: Verify construction offscreen**

Run:
```bash
python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PyQt5 import QtWidgets; from ui.batch_tab import QueueTab; app=QtWidgets.QApplication([]); t=QueueTab({'path':''}); print('retry', t.retry_failed_btn.text())"
```
Expected: prints `retry Retry failed`.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, 430 passed.

- [ ] **Step 6: Commit**

```bash
git add ui/batch_tab.py
git commit -m "feat(ui): retry failed and edit options on the queue"
```

---

### Task 4: CLI - `queue retry`

**Files:**
- Modify: `cli.py` (the `queue` subparsers, `_cmd_queue`)
- Test: `tests/test_cli_queue.py` (append)

**Interfaces:**
- Consumes: `Queue.retry_failed` (Task 1).
- Produces: `queue retry` (prints `retried N`, or JSON `{"schema_version":..., "retried": n}`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_queue.py`:

```python
def test_queue_retry_requeues_failed(tmp_path, monkeypatch, capsys):
    import cli
    import json
    from core.queue import QueueStore

    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(tmp_path / "q.json"))
    assert cli.main(["queue", "add", "https://a.com/1", "--json"]) == cli.EXIT_OK
    capsys.readouterr()

    store = QueueStore(str(tmp_path / "q.json"))
    store.load()
    store.jobs[0].state = "failed"
    store.save()

    rc = cli.main(["queue", "retry", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == cli.EXIT_OK
    assert data["retried"] == 1

    again = QueueStore(str(tmp_path / "q.json"))
    again.load()
    assert again.jobs[0].state == "pending"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_cli_queue.py::test_queue_retry_requeues_failed -v`
Expected: FAIL - `retry` is an unknown `queue` subcommand (argparse exit 2).

- [ ] **Step 3: Add the subcommand**

In `build_parser`, add after the `clear` subparser:

```python
    qrt = qsub.add_parser("retry")
    qrt.add_argument("--json", action="store_true")
    qrt.set_defaults(func=_cmd_queue)
```

- [ ] **Step 4: Handle it in `_cmd_queue`**

Add beside the `clear` branch:

```python
    if command == "retry":
        n = queue.retry_failed()
        queue.store.save()
        if args.json:
            print(json.dumps({"schema_version": SCHEMA_VERSION, "retried": n}))
        else:
            print(f"retried {n}")
        return EXIT_OK
```

- [ ] **Step 5: Run the CLI tests**

Run: `python -m pytest tests/test_cli_queue.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, 431 passed.

- [ ] **Step 7: Commit**

```bash
git add cli.py tests/test_cli_queue.py
git commit -m "feat(cli): queue retry"
```

---

### Task 5: Documentation

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `AGENTS.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: README - queue ergonomics**

Add to the Queue notes: a "Retry failed" button (and right-click Retry) re-queues failed jobs; right-clicking a pending job offers "Edit options..." to change its format, resolution, folder, subtitles, and cookie file; the CLI has `queue retry`.

- [ ] **Step 2: CHANGELOG - Unreleased `### Added`**

Add: retry failed jobs (Queue button, context menu, `queue retry`) and a per-job Edit options dialog for pending jobs.

- [ ] **Step 3: AGENTS.md**

Add one line: the Queue can retry failed jobs (`Queue.retry_failed()`, `queue retry`) and a pending job's options can be replaced (`Queue.set_options()`); retry touches `failed` only and edit applies to `pending` only.

- [ ] **Step 4: Run the suite once**

Run: `python -m pytest -q`
Expected: PASS, 431 passed.

- [ ] **Step 5: Commit**

```bash
git add README.md CHANGELOG.md AGENTS.md
git commit -m "docs: queue retry and edit options"
```

---

## Self-Review

- **Spec coverage:** retry failed only (Task 1), edit pending only (Tasks 1/3), the per-job dialog (Task 2), the toolbar + context menu (Task 3), the CLI `queue retry` (Task 4), docs (Task 5). `attempts` kept and `message` cleared (Task 1). The dialog returns raw fields and the tab builds the options dict via `build_job_options` (Tasks 2/3), avoiding a `dialogs` <-> `batch_tab` import cycle.
- **Placeholder scan:** none; every code step carries real code.
- **Type consistency:** `retry_failed(job_id=None) -> int` and `set_options(job_id, options) -> bool` identical across Tasks 1/3/4; `EditJobDialog(parent, job).chosen()` identical across Tasks 2/3; `build_job_options(..., cookies_from_browser=)` matches its existing signature.
