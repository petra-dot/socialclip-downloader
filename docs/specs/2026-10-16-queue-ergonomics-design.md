# Queue ergonomics: retry failed and edit a job's options

Date: 2026-10-16
Status: approved

## Why

A failed queue job is a dead end today: the only move is to remove it and add
the URL again. And a job's options are frozen at the moment it is added, so a
wrong resolution or folder means re-adding. Both are small frictions with a
clear fix.

## Decisions

1. **Retry re-queues `failed` jobs only.** Back to `pending`, `attempts` kept
   (it is a retry counter), the stale failure `message` cleared. A deliberate
   cancel and an archived skip are not "failures" and stay untouched.
2. **A per-job Edit dialog**, prefilled from that job's options: format,
   resolution, folder, subtitles, cookie file. Change only that job.
3. **GUI gets both; the CLI gets `queue retry` only.** Per-job option editing on
   the CLI is fiddly and low value.
4. **Editable while `pending` only.** A running job is owned by the worker; a
   terminal job will not run again unless retried.

## Non-goals

- No CLI option editor.
- No edit of `cookies_from_browser` per job; it stays a global setting.
- No undo of a retry or an edit.
- No change to `attempts` semantics or to the run loop.

## Architecture

### `core/queue.py` (pure)

- `retry_failed(job_id=None) -> int`:

```python
    def retry_failed(self, job_id: Optional[str] = None) -> int:
        """Re-queue failed jobs (one, or all). Returns how many changed."""
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
```

- `set_options(job_id, options) -> bool`:

```python
    def set_options(self, job_id: str, options: dict) -> bool:
        """Replace a pending job's options. False for any other state."""
        for job in self.jobs:
            if job.id == job_id and job.state == "pending":
                job.options = dict(options)
                return True
        return False
```

Both are additive; no existing method changes.

### `ui/dialogs.py` - `EditJobDialog`

`EditJobDialog(parent, job)`, prefilled from `job.options`:

- Format combo from `OUTPUT_FORMATS` (`utils.file_utils`), selected via
  `output_index_for(options["output_type"])`.
- Resolution combo from `RESOLUTIONS`, selected from
  `str(options["target_resolution"])`.
- Folder input + Browse, prefilled from `os.path.dirname(options["outtmpl"])`.
- Subtitles combo (Off / Sidecar (.srt) / Embed / Both), selected from
  `options.get("subtitles", "off")`.
- Cookie file input + Browse, prefilled from `options.get("cookies_file", "")`.
- `chosen() -> dict` returns the raw fields:

```python
    def chosen(self) -> dict:
        return {
            "save_dir": self.folder_input.text().strip(),
            "output_text": self.output_combo.currentText(),
            "resolution": self.resolution_combo.currentText(),
            "cookies_path": self.cookies_input.text().strip(),
            "subtitles": self.subtitle_combo.currentData(),
        }
```

The dialog imports only `utils.file_utils` and Qt; it does **not** import
`batch_tab` (which imports `dialogs`), so there is no cycle. It returns raw
fields; the caller builds the options dict.

### `ui/batch_tab.py`

- Toolbar: a **Retry failed** button beside Clear finished.

```python
    def on_retry_failed(self):
        count = self.queue.retry_failed()
        if not count:
            self.batch_log("No failed jobs to retry.")
            return
        self.queue.store.save()
        self.refresh_table()
        self.batch_log("Retrying %d failed job(s)." % count)
```

- Context menu: **Retry** for a `failed` row (`queue.retry_failed(job.id)`), and
  **Edit options...** for a `pending` row.

```python
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

### `cli.py`

A `queue retry` subcommand:

```python
    qrt = qsub.add_parser("retry")
    qrt.add_argument("--json", action="store_true")
    qrt.set_defaults(func=_cmd_queue)
```

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

## Data flow

```
Toolbar "Retry failed" ──▶ queue.retry_failed() ──▶ failed -> pending ──▶ save + refresh
Context "Retry"         ──▶ queue.retry_failed(job.id)
Context "Edit options"  ──▶ EditJobDialog ──▶ build_job_options ──▶ queue.set_options ──▶ save + refresh
CLI `queue retry`       ──▶ queue.retry_failed() ──▶ save + print
```

## Error handling

`retry_failed` on an empty/none-failed queue returns 0; the UI logs "No failed
jobs to retry." `set_options` returns False for a non-pending job; the UI only
offers Edit for pending rows, so a stale click is a silent no-op. Neither method
raises.

## Testing

- `core/queue.py`: `retry_failed()` re-queues every failed job, clears its
  message, keeps `attempts`, and leaves done/cancelled/skipped/pending alone;
  `retry_failed(job_id)` touches one; returns the count. `set_options` replaces a
  pending job's options, returns False for running/done/failed/cancelled/skipped
  and for an unknown id.
- `EditJobDialog`: constructs offscreen; `chosen()` reflects the prefilled fields.
- `cli.py`: `queue retry` re-queues failed jobs and prints the count (`--json`).

## Known limitations

- A retried job keeps its `attempts` count; there is no cap on retries.
- Editing a job does not re-validate the options against the site.
- The Edit dialog edits the same fields the Queue tab exposes; a job's
  `cookies_from_browser` is preserved, not editable there.
