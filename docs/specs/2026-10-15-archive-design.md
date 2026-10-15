# Archive: skip already-downloaded videos

Date: 2026-10-15
Status: approved

## Why

Re-running a queue (a collection fetched twice, a retried batch) re-downloads
every video again. A persistent record of what has already been downloaded lets
the Queue skip the repeats instead of re-fetching gigabytes.

## Decisions

1. **A skipped job ends in a new `skipped` state**, shown in its row and counted
   separately in the run summary. Distinct from `done`/`failed`/`cancelled`.
2. **Off by default.** The user turns it on; the toggle persists once set. A
   re-queued video is never silently skipped on upgrade.
3. **Scope is the Queue only:** the GUI Queue tab and CLI `queue run`. The single
   Download tab and `download` always download.
4. **Management:** the Queue tab gets a "Skip already downloaded" checkbox and a
   "Clear archive" button; the CLI gets `queue run --archive` and
   `queue archive --clear`.

## Non-goals

- No archive for the single Download tab or `download`.
- No per-job archive override; the archive is one queue-wide setting.
- No dedupe by URL; the archive keys on yt-dlp's `extractor id`, which is stable
  across URL forms.

## Architecture

### Mechanism: reuse yt-dlp's `download_archive`

yt-dlp records each finished download as `extractor id` in a plain-text file and
skips a video already in it, with one extraction. The app sets that file and
detects the skip; it does not hand-roll the key format.

- `utils/ydl_opts.py`: `_nle_ydl_opts(outtmpl, progress_hooks=None,
  cookies_file=None, archive_file=None)` sets `download_archive` when
  `archive_file` is given.
- `core/download.py`: `download_one(..., archive=None)`. When `archive` is set,
  both `_nle_ydl_opts` calls (the section path and the clip fallback) receive
  `archive_file=archive`. A `saw_download` flag is set from the progress hook on
  `downloading`/`finished`.

### Skip detection

After `extract_info`, if `archive` is set and `info` is present and
`saw_download` is False, no download happened: the video was already archived.
Return `error_result("skipped", "Already downloaded; skipped.", url)`. An
extraction failure still returns `not_found` first (the check is after the
`if not info` guard).

### Result contract

`skipped` is `status="error"` + `error_category="skipped"`, mirroring the
existing `cancelled` category: a distinct value set explicitly, never produced
by `sites.errors.classify_error`. The `manifest-schema` `error_category` enum
gains `skipped`.

### Queue state

`core/queue.py`: add `"skipped"` to `STATES` and `TERMINAL_STATES`.
`apply_result` gains a branch, beside the `cancelled` one:

```python
elif result.error_category == "skipped":
    job.state = "skipped"
    if result.message:
        job.message = result.message
```

`skipped` is terminal: it counts as finished in the overall progress bar,
`cancel_all` leaves it alone, and `can_remove` allows removing the row.

### Archive file (`core/archive.py`, new, pure)

- `default_archive_path() -> str`: `os.path.join(app_dir(), "archive.txt")`,
  beside `queue.json` and `presets.json`.
- `clear_archive(path) -> bool`: remove the file if it exists; return whether it
  was removed. Never raises.

No threads, no Qt (core rule).

### Wiring

- `workers/queue_worker.py`: `QueueWorker(queue, jobs=3, archive=None)`;
  `_download` passes `archive=self.archive` to `download_one`.
- `ui/batch_tab.py`: a "Skip already downloaded" `QCheckBox` (persisted in
  `QSettings` key `queue/archive`, default off) and a "Clear archive" button
  (`clear_archive(default_archive_path())`, then log the result). `on_start_queue`
  passes `archive=default_archive_path() if checked else None`.
- `cli.py`: `queue run --archive` (a store-true flag; passes the archive path to
  the executor); `queue archive --clear` (a new `queue` subcommand that calls
  `clear_archive` and prints a result); `_queue_executor(job, archive=None)`
  forwards it; `_run_cli_job(job, archive=None)`; the `run` summary dict gains a
  `skipped` count and the text summary prints it.

## Data flow

```
Queue tab (checkbox) ─┐
                      ├─▶ download_one(archive=path) ─▶ yt-dlp download_archive
CLI `queue run --archive` ─┘                             │
                                        skipped ──▶ error_result("skipped")
                                                         │
                                          apply_result ──▶ job.state "skipped"
```

## Error handling

`clear_archive` swallows `OSError` and returns False. A missing archive file is
not an error (the first run creates it via yt-dlp). The skip check never raises;
it is a plain flag test after extraction.

## Testing

- `core/queue.py`: `apply_result` maps `error_category == "skipped"` to
  `job.state == "skipped"`; `skipped` is in `TERMINAL_STATES`.
- `core/archive.py`: `default_archive_path()` ends in `archive.txt` beside the
  queue file; `clear_archive` removes an existing file, returns False for a
  missing one, never raises.
- `core/download.py`: with a monkeypatched `YoutubeDL`, an archived video (no
  hook fired) returns `error_category == "skipped"`; a normal download does not.
- `cli.py`: `queue run --archive` reaches `download_one` with the archive path;
  `queue archive --clear` removes the file.

## Known limitations

- The archive is one file shared by GUI and CLI; two front ends running at once
  could interleave writes. yt-dlp appends line-by-line; acceptable.
- A video whose site does not provide a stable `extractor id` is not archived
  (yt-dlp cannot key it). Silent, and yt-dlp's own behaviour.
- The archive grows without bound; "Clear archive" is the reset.
