# Bulk Convert - Design

Status: draft - awaiting review
Date: 2026-10-18
Applies to: `core/convert_queue.py` (new), `core/paths.py`, `workers/convert_queue_worker.py`
(new), `ui/convert_tab.py`, `tests/`

## Problem

The Convert tab converts one file at a time: pick a file, choose a target, press
Convert. Converting a folder of clips means repeating that per file, with no
list, no per-file state, and no way to see what is left. The Queue tab already
solves the same shape of problem for downloads (a persistent list, per-row
status, retry, clear finished), so the two tabs disagree about how a batch works.

## Goal

One Convert tab that converts a list of files: add many at once, see each row's
target and state, run them one at a time, cancel, retry, and clear finished -
using the Queue tab's patterns so the two tabs read as one app.

## Decisions (locked during the design pass)

- **Files come in** by a multi-select file dialog and by drag-and-drop from the
  file manager onto the table.
- **The list persists** in `convert.json` in the data directory, like
  `queue.json`.
- **The output target is baked per row** when it is added, shown in the row, with
  **Edit options** on the right-click menu applying to every selected row, and one
  **Apply to all pending** button.
- **The list is the whole tab**: one row is one file. The single-file field goes
  away; its controls become the "options for new items" block.
- **One conversion at a time.** ffmpeg encodes are CPU-bound; serial keeps the
  machine responsive.
- **The right-hand panel becomes a selected-row detail**, not a form result: file,
  target, output path, state, message, and Open folder.

## Non-goals

- No pause/resume (conversions are short; the Queue's pause exists for long
  downloads).
- No progress percentage per row: `core.convert.convert_file` reports no
  progress, and adding one is a separate change. A running row shows a busy
  state and its status text.
- No changes to `core.convert.convert_file`, `core/pipeline.py`, or the CLI
  `convert` command.
- No new dependencies.

## A. Core model - `core/convert_queue.py` (Qt-free, tested)

Mirror `core/queue.py`'s shape: data plus pure logic, no threads.

- `ConvertJob` dataclass: `id` (uuid hex), `path`, `target_format` (a
  `core/formats.py` registry key), `resolution` (int or 0), `copy_streams`
  (True/False/None), `state`, `message`, `output_path`, `added_at`.
- States: `pending`, `running`, `done`, `failed`, `cancelled`.
  `TERMINAL_STATES = ("done", "failed", "cancelled")`.
- `ConvertQueue`:
  - `add(paths, options) -> list[ConvertJob]` - one job per path, options baked
    in, duplicates by path skipped.
  - `remove(job_id) -> bool` - pending/failed/done/cancelled only, never
    `running`.
  - `set_options(job_ids, options) -> int` - applies to `pending` rows only,
    returns how many changed.
  - `claim_next() -> ConvertJob | None` - the first `pending`, marked
    `running`.
  - `apply_result(job_id, result)` - maps a `core.manifest.DownloadResult` to
    `done` (with `output_path`) or `failed` (with the message); a cancelled run
    ends `cancelled`.
  - `retry_failed(job_id=None) -> int` - failed back to `pending`.
  - `clear_finished() -> int` - drops terminal rows.
  - `pending_count()`, `jobs`.
- Pure functions for the parts worth testing without Qt:
  `job_from_paths(paths, options, existing_paths) -> list[ConvertJob]` (dedupe)
  and `state_label(state)` / `state_kind(state)` equivalents live in the tab, not
  here.

## B. Store and path

- `core/paths.convert_path()`: `SOCIALCLIP_CONVERT` override, else
  `os.path.join(data_dir(), "convert.json")`. Same shape as `queue_path()`.
- `ConvertStore` in `core/convert_queue.py`: `version: 1`, atomic write through a
  per-process temp file, tolerant load that drops unknown keys but never the job
  (the Queue's rule), and `load()` / `save()`.

## C. Worker - `workers/convert_queue_worker.py`

- `ConvertQueueWorker(QtCore.QThread)`: takes a `ConvertQueue` and its store.
  - Loops: `claim_next()`; if none, stop. Convert it, `apply_result`, save, emit.
  - Signals: `job_signal(job_id, state, job)` (a snapshot, never the live object -
    the Queue's rule) and `finished_signal(str)`.
  - `cancel(job_id)` marks the running job to stop after the current ffmpeg call
    returns; `cancel_all()` cancels the running one and leaves the rest pending.
    `core.convert.convert_file` has no cancel hook, so cancellation is
    cooperative at the boundary between files, and the running file finishes.
- The tab owns the thread; `core/` stays thread-free.

## D. Convert tab - `ui/convert_tab.py`

The list is the tab.

- **Toolbar:** `Add files…` (multi-select), `Clear finished`, `Retry failed`.
- **Table** (`QTableWidget`, `ExtendedSelection`): `File | Status | Detail`.
  - `File`: the basename, with the full path as a tooltip.
  - `Status`: a `make_chip` chip (`pending` muted, `running` busy, `done` ok,
    `failed` error, `cancelled` muted).
  - `Detail`: the baked target for pending (`MP4 (H.264 + AAC) 1080p`, using
    `core.formats` labels), the output name for done, the error for failed, the
    status text while running.
- **Drag-and-drop:** `setAcceptDrops(True)` on the table; `dragEnterEvent`
  accepts `text/uri-list`, `dropEvent` adds the local files.
- **Options for new items** block: target format (the full registry), resolution
  (disabled for audio/GIF/copy, reusing the existing `_update_conv_controls`
  logic), streams; plus `Apply to all pending`.
- **`Convert`** starts the worker and becomes `Cancel all` while it runs.
- **Right-click** on a row: `Edit options…` (applies to every selected row),
  `Remove`, `Retry`, `Cancel`.
- **Bulk bar** on multi-select: `N selected` plus `Retry`, `Remove`,
  `Clear finished` - above the table, as in the Queue.
- **Activity log** stays shown by default and minimizable (unchanged behaviour).
- The old single-file widgets (`file_path_input`, `Select File…`, the single
  `Convert Selected File` button) are removed; their options become the options
  block.

## E. Result panel

The shared `make_result_panel()` frame stays, repurposed as the **selected row's
detail**: file name, target label, output path (or "-"), state, the message, and
`Open folder` (enabled only when the row has an output). It clears when nothing
is selected. The empty state reads "Select a file to see its details."

## F. Nothing else moves

`core.convert.convert_file`, `core/pipeline.py`, `core/formats.py`, and the CLI
`convert` command are untouched. `ui/convert_tab.py`'s single-file path is
replaced by the list; nothing else in the app reads it.

## G. Testing and verification

- `tests/test_convert_queue.py` (new): `add` bakes options and skips duplicate
  paths; `claim_next` returns the first pending and marks it running; `apply_result`
  maps ok/failed/cancelled; `retry_failed` touches failed only; `set_options`
  touches pending only; `remove` refuses a running job; `clear_finished` drops
  terminal rows; the store round-trips and keeps a job with an unknown key.
- `tests/test_paths.py` (extend): `convert_path()` honours `SOCIALCLIP_CONVERT`
  and otherwise sits in the data dir.
- `tests/verify_ui_offscreen.py` (extend): the Convert tab builds with an empty
  table, `Add files…` adds rows through the queue API, the table is
  `ExtendedSelection`, the bulk bar appears on multi-select, the start button
  becomes `Cancel all` while a worker runs, and the detail panel fills on
  selection. **The existing single-file assertions
  (`convert.convert_file_btn.isEnabled()`, the file field) must be replaced** -
  that widget is removed by §D, so the script would fail on import otherwise.
- Manual: add several files, convert them, cancel mid-batch, retry a failure,
  clear finished, and confirm the rows survive a restart.
- All 632 existing tests keep passing; flake8 gate stays `0`.

## Risks

1. **The tab's UI changes shape.** The single-file flow disappears by decision;
   the CLI and the core path are untouched, so only this tab is affected.
2. **Drag-and-drop on Windows** can deliver `text/uri-list` or plain paths;
   accept both and filter to existing local files.
3. **Cancellation is cooperative.** A cancel lands between files, not mid-encode,
   because `convert_file` has no cancel hook. The row must say so, and the running
   file must finish rather than leave a partial output (the converter already
   deletes a failed output).
4. **The store is a second file to keep honest.** Same versioned, atomic,
   tolerant pattern as `queue.json`; a corrupt file loads empty rather than
   raising.
5. **`convert.json` grows with stale rows.** `Clear finished` is the answer, and
   it is on the toolbar and the bulk bar.
