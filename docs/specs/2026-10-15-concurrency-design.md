# Concurrency: parallel queue downloads

Date: 2026-10-15
Status: approved

## Why

The queue runs one job at a time. A 50-video collection therefore downloads
serially, and the app sits idle on network latency for most of the wall clock.
Running several downloads at once is the single biggest speed-up available to
the queue.

## Decisions

1. **Scope is the Queue, in both front ends.** The GUI Queue tab and the CLI
   `queue run` both run N at once. The Download tab's single download is
   unchanged.
2. **Default 3 concurrent, range 1-8**, adjustable by the user. On by default:
   the feature is real out of the box.
3. **UI:** each running row shows its own percent; the top bar becomes overall
   queue progress (terminal jobs / total); the button becomes **Cancel all**,
   and right-clicking a running row cancels just that one.
4. **CLI:** `queue run` defaults to 3; `--jobs N` overrides (1-8).

## Non-goals

- No concurrency for the single-download (Download) tab.
- No adaptive/auto-tuned worker count; the user picks it.
- No cross-process coordination; one queue file, one running front end at a time.

## Architecture

### Core (`core/queue.py`) stays pure and thread-free

`run_once` currently claims a job, runs it, and applies the result in one call.
Split the two pure halves out so a concurrent caller can claim and apply under
its own lock:

- `claim_next() -> Optional[QueueJob]`: if paused, return `None`; else find the
  first `pending` job, set it `running`, `attempts += 1`, return it. `None` when
  the queue is paused or empty.
- `apply_result(job, result) -> QueueJob`: the existing state-from-result block
  (ok / cancelled / failed), unchanged in behaviour.
- `run_once(executor)` becomes `claim_next()` + `executor(job)` +
  `apply_result(job, result)`. Signature and behaviour are unchanged, so the
  existing tests and any sequential caller keep working. The CLI `queue run`
  moves to the pool (below); `run_once` stays for the tests and a sequential
  path.

`core/queue.py` gains no locks and no threads; the caller serializes access to
`queue.jobs`.

### GUI runner (`workers/queue_worker.py`)

`QueueWorker(queue, jobs=3)`.

- `run()` owns a `concurrent.futures.ThreadPoolExecutor(max_workers=jobs)` and a
  `threading.Lock` (`self._lock`).
- Coordinator loop: fill the pool to N by calling `claim_next()` and submitting
  `self._run_job(job)`; each time a future completes, claim and submit the next;
  stop when no pending jobs remain and the pool has drained. Pausing stops
  claiming new jobs; in-flight jobs finish.
- `_run_job(job)`: `self._executor(job)`, then under `self._lock`:
  `queue.apply_result(job, result)`, emit `job_signal`, `queue.store.save()`.
  Saving under the lock means one writer; `QueueStore.save` keeps its
  temp-file-then-`os.replace` atomic write.
- Per-job cancel: `self._cancel_events: dict[job_id, threading.Event]`.
  `_executor` passes that job's `is_set` as `cancel`. `cancel_job(job_id)` sets
  that one event; `cancel_all()` sets every event and calls `queue.cancel_all()`.
- Signals: `job_signal(str, str, object)` and `finished_signal(str)` unchanged;
  `progress_signal` becomes `(str, int)` (job_id, percent).

### CLI (`cli.py`)

`queue run` gains `--jobs N` (type int, default 3, choices 1-8). `_cmd_queue`'s
`run` branch replaces its `while True: run_once` loop with the same pool shape,
printing one line per finished job and the same summary dict as today
(`run`/`done`/`failed`/`cancelled`).

### UI (`ui/batch_tab.py`)

- A **"Downloads at once"** `QSpinBox` (1-8, default 3) on the Queue tab,
  persisted in `QSettings` (`queue/jobs`).
- `_on_progress(job_id, percent)` writes the percent into that row's Detail
  cell; the running row's Status stays `running`.
- The top progress bar shows overall progress: terminal jobs / total jobs,
  recomputed on each `job_signal`.
- `cancel_current_btn` becomes **Cancel all** (`cancel_all`). The row context
  menu gains **Cancel this download** for `running` rows, wired to
  `worker.cancel_job(job.id)`.

## Data flow

```
QueueTab ──start──▶ QueueWorker(queue, jobs=N)
                       │  claim_next()  (lock)
                       ▼
              ThreadPoolExecutor(max_workers=N)
                       │  per job: download_one(cancel=job_event)
                       ▼
              apply_result(job) + store.save()  (lock) ──▶ job_signal / progress_signal
```

## Cancel semantics

A cancelled run returns `error_category == "cancelled"` from `download_one` and
`apply_result` sets the job `cancelled`, a terminal state. Each running job has
its own `Event`, so cancelling one job does not touch the others. **Cancel all**
sets every event and marks every non-terminal job cancelled.

## Error handling

A job that raises is caught per job (as today) and marked `failed`; it never
takes down the pool. A crash in one worker thread does not stop the others.

## Testing

- Pure tests for `claim_next` (returns the first pending, marks it running,
  increments `attempts`, returns `None` when paused/empty) and `apply_result`
  (ok / cancelled / failed state mapping).
- `run_once` keeps its existing test coverage; it must stay behaviourally
  identical.
- The thread loop and the Qt signals stay GUI-verified via offscreen
  construction, per the repo's convention (threads and Qt are not unit-tested).

## Known limitations

- Two jobs whose titles resolve to the same output path target the same file;
  yt-dlp does not clobber a partial write, so the last writer wins. Not solved;
  the queue rarely holds two identical titles.
- Network and CPU use scale with N; the 1-8 range is the guard rail.
