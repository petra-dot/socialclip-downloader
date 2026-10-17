# Download History - Design

Status: proposed
Date: 2026-10-18
Applies to: `core/history.py` (new), `core/download.py`, `ui/history_tab.py` (new),
`ui/main_window.py`, `utils/ui_helpers.py`, `tests/test_history.py` (new)

## Problem

The app downloads files and then forgets them. The Queue keeps `path`, `bytes`,
and `height` per job, but only while the job exists in `queue.json`; clearing
finished jobs loses the record. **Single-tab downloads are recorded nowhere at
all**, and the CLI records nothing. There is no way to see what you downloaded,
where it went, how big it was, or what format it is - and no way to play, reveal,
or delete it from the app. A file deleted outside the app leaves no trace that it
ever existed.

## Goal

A persistent, queryable record of every **completed** download, from the Download
tab, the Queue, and the CLI, showing its location, size, format, and other facts,
with an honest status when the file is no longer on disk, and actions to play it,
reveal it, delete the file, or forget the entry.

## Non-goals

- **No in-app media player.** "Play" hands the file to the operating system's
  default application. This avoids `QtMultimedia`, its per-OS codec differences,
  and bundling its plugins in the frozen builds.
- **No ffprobe at download time.** Height and duration come free from the
  download result; the real container and codec detail is probed on demand, so a
  download costs no extra subprocess and stored data cannot go stale.
- **No re-download action**, no cross-machine sync, no import/export.
- **No merging of repeated URLs.** A history is a log, not a set: downloading the
  same URL twice is two entries.
- **No searching by filename.** Status is matched on the stored path, so a file
  you moved or renamed reads as missing rather than being hunted for.

## Decisions taken

1. **Recording happens in `core.download.download_one`**, once, so the Download
   tab, the Queue, and the CLI all record with no call-site changes and no way to
   forget. This is the same lesson as the cookie fix: resolve it in the shared
   path, not at each caller.
2. **The store is `history.json` in the per-user data directory**
   (`core.paths.data_dir()`), following the existing `QueueStore` pattern:
   atomic write, tolerant load.
3. **An unknown key never drops an entry.** The load path ignores fields it does
   not recognise and keeps the record, the same rule `Queue._coerce_jobs` learned.
4. **Status is derived, never stored.** The tab `stat`s each file when it loads,
   so the status cannot go stale.
5. **Deleting a file keeps the record.** The file is removed and the entry is
   marked `removed_at`; a separate **Remove from history** drops the entry.
6. **Every destructive action confirms first**, and only ever touches a path the
   history recorded.
7. **Playback is delegated to the OS**, through one Qt-free helper.
8. **The tab is a sortable table with search and filters**, matching how the
   Queue tab already reads.

## Architecture

### `core/history.py` (new, Qt-free)

```python
@dataclass
class HistoryEntry:
    id: str
    title: str
    url: str
    platform: str
    path: str
    bytes: int = 0
    extension: str = ""        # "mp4" | "mp3"
    height: int = 0            # 0 when not applicable
    duration_seconds: int = 0
    source: str = ""           # "single" | "queue"
    created_at: str = ""
    removed_at: str = ""       # set only by an in-app delete

def entry_from_result(result, source="") -> HistoryEntry
def status_of(entry, exists=None) -> str        # "ok"|"missing"|"deleted"
def search(entries, text) -> list               # pure
def filter_entries(entries, platform=None, extension=None) -> list   # pure
def sort_entries(entries, key, descending=False) -> list             # pure

class HistoryStore:
    def __init__(self, path=None)
    def load(self) -> None
    def save(self) -> None
    def add(self, entry) -> HistoryEntry
    def remove(self, entry_id) -> bool
    def mark_deleted(self, entry_id) -> bool
    def entries(self) -> list
```

- `entry_from_result` takes a `core.manifest.DownloadResult` and maps it almost
  1:1, because that dataclass already carries `title`, `url`, `platform` (filled
  by `detect_platform`), `path`, `extension`, `height`, `bytes`, and
  `duration_seconds`. Only `source` comes from the caller, and `created_at` is
  stamped here. There is no need to re-derive the platform or the title.
- The MP4/MP3 distinction shown in the UI comes from `extension`
  (`mp3` -> `MP3`, else `MP4`); it is not a separate stored field.
- `status_of(entry, exists=None)`: `"deleted"` when `removed_at` is set, else
  `"ok"` when the path is a file, else `"missing"`. `exists` is injectable, so it
  is pure for tests.
- The `search`/`filter_entries`/`sort_entries` helpers are pure and carry the
  test suite.
- `HistoryStore` mirrors `QueueStore`: `load()` never raises and never drops an
  unrecognised-key entry; `save()` writes atomically (temp file + `os.replace`).

### `core/download.py`

On a successful download, after the final path is known and all post-processing
has finished, build an entry and append it. The store is injectable so tests need
no filesystem:

```python
def download_one(..., history=None):
    ...
    if history is not None and result_ok:
        history.add(entry_from_result(result, source=source))
```

Callers pass a store; the GUI and CLI pass the real one. Recording never fails a
download: a store error is swallowed and logged, because losing a history line
must never lose a file.

### `utils/ui_helpers.py`

```python
def open_file(path) -> bool:
    """Hand `path` to the OS default application. Qt-free. False on failure."""
```
`os.startfile` on Windows, `open` on macOS, `xdg-open` on Linux, always with an
argument list and never `shell=True`.

### `ui/history_tab.py` (new)

A `QWidget` mirroring `ui/batch_tab.py`'s shape:

- A search `QLineEdit`, a platform combo, and a format combo (All / MP4 / MP3).
- A `QTableWidget` with columns **Title, Platform, Format, Size, Date, Status**;
  clicking a header sorts (reusing `sort_entries`).
- Buttons for **Play**, **Open folder**, **Delete file**, **Remove from history**,
  and **Details**, plus the same actions on a right-click context menu.
- A **Details** dialog showing the stored facts - including the height and
  duration the download result already carried - and, on demand, the ffprobe
  result from `core/probe.py` for the real container, video codec, and audio
  codec. A probe failure is reported inline, never as a crash.
- Rows whose status is not `ok` grey out Play / Open folder / Delete file and keep
  Remove from history enabled.
- A **Clear history** action, with a confirm.

### `ui/main_window.py`

A fourth tab: **Download · Queue · Convert · History**. The History tab is
constructed once and refreshed when shown, so it always reflects the filesystem
at the moment you look at it.

## Data flow

```
download_one(...)  ->  success
      |
      +-> entry_from_result(result, source)
      +-> HistoryStore.add(entry)  ->  atomic save to <data dir>/history.json

History tab shown
      +-> HistoryStore.load()
      +-> for each entry: status_of(entry)      # stat, cheap
      +-> search / filter / sort                # pure helpers
      +-> table rows; non-ok rows greyed

Play      -> open_file(path)                     # OS default app
Delete    -> confirm -> os.remove(path) -> mark_deleted(entry_id)
Remove    -> confirm -> HistoryStore.remove(entry_id)
Details   -> stored facts + core.probe.probe(path) on demand
```

## Platform behaviour

| Concern | Windows | macOS | Linux |
|---|---|---|---|
| Play | `os.startfile` | `open` | `xdg-open` |
| Reveal | existing `reveal_in_folder` | same | same |
| Data dir | `%LOCALAPPDATA%\SocialClip Downloader` | `~/Library/Application Support/...` | `$XDG_DATA_HOME/socialclip` |

## Safety

- **No action ever touches a path that is not in the history.** The store is the
  only source of paths, and Delete re-checks the file exists first.
- **Every destructive action confirms**, naming the file, and says whether the
  record is kept (Delete) or dropped (Remove).
- **A missing file is never deleted** - it is already gone, and the action is
  disabled.
- `open_file` uses an argument list and never `shell=True`, so a filename with
  shell metacharacters cannot execute anything.
- History is a **local** file in the per-user data dir; nothing is sent anywhere.
- Recording a history line **can never fail a download**.

## Testing

`tests/test_history.py` (new, pure):
- `entry_from_result`: a full result, a result with no resolution (MP3), a result
  with a missing title, and an unknown platform URL.
- `status_of`: present file, absent file, `removed_at` set, and an injected
  `exists` for purity.
- `search`: matches the title case-insensitively, no match, empty query.
- `filter_entries`: by platform, by format, both, neither, and an unknown value.
- `sort_entries`: by each column, ascending and descending, and a stable order for
  equal keys.
- `HistoryStore`: append and reload round-trips; an entry with an **unknown key is
  kept**; a corrupt file loads as empty rather than raising; `remove` and
  `mark_deleted` return the right booleans; `save` is atomic (no partial file).

`tests/test_ui_helpers.py`: `open_file` returns False for a missing path and never
raises.

The tab itself is verified offscreen, as the rest of the UI is; no Qt unit tests.

## Risks

1. **`history.json` grows without bound.** A few thousand entries is about a
   megabyte, so this is acceptable for a long time; `Clear history` exists, and a
   size cap can be added if it ever matters.
2. **A moved or renamed file reads as missing.** Matching on the stored path is
   deliberate - hunting by filename would risk acting on the wrong file - but it
   means a user who reorganises their folders sees stale "Missing" rows. They can
   Remove those entries.
3. **The OS may have no default app for a format**, so Play can fail. `open_file`
   returns a boolean and the tab reports the failure rather than doing nothing.
4. **`removed_at` and `missing` are two ways of saying "not on disk".** Keeping
   both tells the user *they* deleted it versus it vanishing; if that distinction
   proves confusing in use, collapse them into one `Not found`.
5. **Recording inside `core/download.py` adds a side effect to the core.** It is
   injected and swallowed on failure, but it does mean the core now knows about a
   store. The alternative - recording at three call sites - is the bug class this
   release was spent fixing.
