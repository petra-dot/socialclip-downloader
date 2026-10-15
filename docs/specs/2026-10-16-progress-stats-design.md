# Download stats: speed, ETA, and size in the progress display

Date: 2026-10-16
Status: approved

## Why

The progress display shows only a percentage. While a large download runs, the
two numbers that matter are how fast it is going and how long is left, and
yt-dlp already reports both. The percent-only bar wastes that.

## Decisions

1. **Show percent, speed, ETA, and size** in the progress text.
2. **Both tabs.** The single Download tab shows the text under its bar; the Queue
   shows the same text in each running row's Detail cell.
3. **The Queue's overall bar stays percent only.** Speed and ETA do not
   aggregate across concurrent downloads.
4. **Missing values are omitted, never faked.** yt-dlp reports `speed`, `eta`,
   and `total` as `None` early in a download and for live streams; those parts
   simply drop out of the string.

## Non-goals

- No change to the updater's progress (its own percent-only signal).
- No progress output in the CLI.
- No graph, sparkline, or history.
- No change to what gets downloaded.

## Architecture

### `core/progress.py` (new, pure)

```python
Progress = collections.namedtuple(
    "Progress", ("percent", "speed", "eta", "downloaded", "total")
)
```

- `percent: int` - 0-100.
- `speed: Optional[float]` - bytes per second, `None` when unknown.
- `eta: Optional[int]` - seconds remaining, `None` when unknown.
- `downloaded: int` - bytes so far.
- `total: Optional[int]` - total bytes, `None` when unknown.

Formatters (all pure):

- `format_bytes(n) -> str` - 1024-based, one decimal for KB and up, integer for
  B: `512 B`, `48.3 KB`, `14.2 MB`, `1.4 GB`.
- `format_speed(bps) -> str` - `format_bytes(bps) + "/s"`, or `""` when `None`.
- `format_eta(seconds) -> str` - `ETA MM:SS`, or `ETA H:MM:SS` past an hour, or
  `""` when `None`.
- `format_progress(p) -> str` - `"45%  3.2 MB/s  ETA 00:12  14.2/31.0 MB"`:
  the percent always; then speed, ETA, and size each only when known. Size is
  `downloaded/total` when total is known, else `downloaded`. Parts are joined by
  two spaces.

### `core/download.py`

The progress hook builds a `Progress` and calls `progress(p)` where it called
`progress(percent)`:

```python
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                pct = int(d.get("downloaded_bytes", 0) / total * 100) if total else 0
                progress(Progress(
                    percent=pct,
                    speed=d.get("speed"),
                    eta=d.get("eta"),
                    downloaded=int(d.get("downloaded_bytes", 0) or 0),
                    total=total,
                ))
            elif d.get("status") == "finished":
                progress(Progress(percent=100, speed=None, eta=None,
                                  downloaded=0, total=None))
```

`progress` is one callable carrying a richer payload; no second callback.

### `workers/download_worker.py`

`progress_signal = QtCore.pyqtSignal(object)` - carries a `Progress`.
`progress=self.progress_signal.emit` is unchanged.

### `workers/queue_worker.py`

`progress_signal = QtCore.pyqtSignal(str, object)` - `(job_id, Progress)`.

```python
            progress=lambda p: self.progress_signal.emit(job.id, p),
```

### `ui/single_tab.py`

A label under the progress bar; `_on_progress(p)` sets the bar to `p.percent` and
the label to `format_progress(p)`.

### `ui/batch_tab.py`

`_on_progress(job_id, p)` writes `format_progress(p)` into that row's Detail
cell. `_update_overall_progress` is unchanged (percent only).

## Data flow

```
yt-dlp hook ──▶ Progress ──▶ progress(p) ──▶ DownloadWorker.progress_signal(object)
                                          └─▶ QueueWorker.progress_signal(str, object)
                                                     │
                              ui: bar.setValue(p.percent) + label/Detail = format_progress(p)
```

## Error handling

Every formatter tolerates `None` and returns `""` for it; `format_progress`
never produces a trailing separator. A `total` of `None` yields a size of just
`downloaded`. No path raises.

## Testing

- `core/progress.py`: `format_bytes` at B/KB/MB/GB boundaries; `format_speed`
  and `format_eta` including `None`; `format_eta` past an hour; `format_progress`
  with all fields, with `speed`/`eta` `None`, and with `total` `None`.
- `core/download.py`: a fake yt-dlp whose hook fires `downloading` with `speed`,
  `eta`, `downloaded_bytes`, `total_bytes` yields a `Progress` carrying those
  values (captured through a `progress` callable).

## Known limitations

- Speed and ETA are yt-dlp's own estimates and can jump early in a download.
- Units are 1024-based but labelled `MB`/`GB` (the common convention).
- The Queue's overall bar has no speed; only per-row text does.
