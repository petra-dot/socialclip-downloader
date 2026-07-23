# Changelog

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
