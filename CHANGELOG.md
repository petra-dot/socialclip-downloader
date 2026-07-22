# Changelog

## v0.4.0 - 2026-07-23
### Added
- Dark theme UI with full QSS stylesheet
- Sidebar navigation replacing QTabWidget
- Queue system with concurrent download control and scheduling
- Douyin cookie auto-detection
- Collapsible cookie section in download tab
- Progressive video info section visibility

### Changed
- Redesigned single download tab to card-based layout
- Switched to Fusion style for consistent widget rendering
- Updated typography hierarchy and widget sizing
- Migrated project structure to modular packages

### Fixed
- Checkbox rendering on Windows dark theme
- Output section layout and spacing
- Throttle control layout in queue tab

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
