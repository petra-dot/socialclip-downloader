# Changelog

## v0.9.0 - 2026-10-01
### Added
- Persistent download queue (`core/queue.py`): `Queue`/`QueueStore` hold jobs
  as plain data (no threads), saved to `queue.json` in the app config
  directory. Set `SOCIALCLIP_QUEUE` to override the path. The GUI Queue tab
  and the CLI share the same file
- `socialclip queue add|list|run|clear` commands, each with `--json` output;
  `run` processes pending jobs one at a time and saves after each
- Queue tab (`ui/batch_tab.py:QueueTab`), replacing the old Batch tab: a URL
  table with per-item status plus **Add URLs**, **Paste**, **Pause**/**Resume**,
  **Cancel**, and **Clear finished**
- `workers/queue_worker.py` drives the queue on a `QThread`, one job at a time,
  reporting through Qt signals
- Mid-download cancel: `core.download.download_one` takes a `cancel` callable
  checked in the yt-dlp progress hook and a new `cancelled` error category,
  distinct from the six in `sites/errors.py` and a terminal queue state

### Changed
- The Batch tab is now the Queue tab; the per-URL progress model is replaced by
  a persistent, resumable queue

### Removed
- `workers/batch_worker.py` (superseded by `workers/queue_worker.py`)

## v0.8.0 - 2026-10-01
### Added
- Doctor health report (`core/doctor.py`) covering ffmpeg presence/version,
  per-platform cookie files, and network reachability. `socialclip doctor`
  renders it as text and `--json` as structured output; the report carries its
  own `schema_version` `"1.1"` (the download result contract stays `"1.0"`)
- First-run welcome dialog with the default save folder, ffmpeg status, and
  cookie guidance; a **Doctor** action in the Help menu opens the full report
  (`ui/dialogs.py`)
- Single tab: auto-fetch on a pasted URL, clipboard fill on focus/show, and an
  **Open folder** button that reveals the final artifact
- Batch tab: per-URL table showing each item's status, plus a bulk **Paste**
  action that appends URLs from the clipboard
- New pure helpers: `utils/ui_helpers.py` (`looks_like_url`,
  `reveal_in_folder`) and cookie lookup helpers in `sites/cookies.py`

### Deferred
- Batch tab per-item percentage progress (`running <pct>%`): v0.8 rows are
  state-only; the per-item percentage in the row is a follow-up

## v0.7.0 - 2026-10-01
### Added
- Headless `core/` package (Qt-free) shared by the GUI and the CLI:
  `core.download.download_one`, `core.convert.convert_file`, `core.manifest`
  (versioned JSON contract), `core.pipeline`
- `socialclip` command-line tool: `download`, `convert`, `doctor`,
  `manifest-schema`, with `--json` structured output and documented exit codes
  (0 ok, 1 failure, 2 usage, 3 missing dependency)
- Console binary per OS in the release workflow, alongside the GUI binary
- Error categories extended: `network`, `not_found`

### Fixed
- Platform detection matched substrings, so any URL containing `x.com`
  (e.g. `app.box.com`) was misdetected as Twitter; detection now parses the
  hostname and matches anchored patterns
- `socialclip download` re-encoded anything above 1080p by default; conversion
  is now opt-in via `--convert`, matching the GUI checkbox
- The ffmpeg-missing warning used `print()`, invisible in the `--windowed`
  build; it is now a dialog
- Batch downloads could not be stopped; a Cancel button is now wired to the
  worker
- `ffmpeg_location` is only passed to yt-dlp when the resolved path exists
- GUI download/convert lost their skip and success status messages after the
  core refactor

## v0.6.1 - 2026-10-01
### Added
- Per-OS release binaries (Windows/macOS/Linux) built by GitHub Actions
- HiDPI scaling and settings persistence (save dir, cookies, convert options,
  window geometry)
- macOS/Linux launcher (`run.sh`)

### Fixed
- ffmpeg is now located via env override / PATH / common install dirs, and the
  resolved path is passed to yt-dlp (installations outside PATH now work)
- Cookie file lookup falls back to the app directory when the launch directory
  has none
- Shared `classify_error` used by all download paths (consistent messages)

## v0.6.0 - 2026-09-02
### Added
- Facebook support (videos, Reels, single and batch download)
- Facebook cookie auto-detection and platform-aware error messages

### Fixed
- Duration display crash when yt-dlp returns float duration
- ffmpeg-not-found errors now show clear install instructions instead of raw traceback

## v0.5.0 - 2026-07-23
### Changed
- Restored default Qt theme (removed dark QSS + Fusion style)
- Replaced sidebar + header with QTabWidget layout
- Removed queue system (dlqueue module)
- Simplified all tab layouts to flat design (no card wrappers)
- Consolidated entry point to single `socialclip_downloader.py`

### Added
- Platform cookie auto-detection for YouTube, Douyin, Instagram, Twitter/X, TikTok, Bilibili
- Platform-aware error messages (shows correct site name, not generic "YouTube")
- Cookie UI in batch tab (was missing entirely)
- Shared combo constants (`OUTPUT_FORMATS`, `RESOLUTIONS`, `CONV_OUTPUT_FORMATS`)

### Fixed
- `clean_title` now preserves non-ASCII characters (Chinese, etc.)
- False "success" messages after ffmpeg failure in all workers
- `ydl.prepare_filename()` called outside context manager in batch worker
- Stale worker signals firing after URL change (sequence guards)
- Multiple workers starting on rapid button clicks
- Auto-cookies overwriting manual cookie selection
- `editingFinished` clearing cached metadata on focus loss

## v0.3.0 - 2026-03-16
### Added
- Added `run.bat` to simplify launching the app.
- Added cookie authentication support (cookies.txt) in `DownloadWorker` and GUI.

### Fixed
- Improved error handling and code readability.
- Updated `.gitignore` to improve organization.

## v0.2.0 - 2025-12-24
### Added
- Initial GUI with yt-dlp backend.
- MP3 conversion support.
- Resolution targeting for downloads.

## v0.1.0 - 2025-09-20
- First working version
