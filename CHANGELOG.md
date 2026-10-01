# Changelog

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
