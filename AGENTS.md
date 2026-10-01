# AGENTS.md

## Project

SocialClip Downloader: PyQt5 desktop app that downloads video/audio from
yt-dlp-supported sites (YouTube, Douyin, Instagram, Twitter/X, TikTok,
Bilibili, Facebook, and anything else yt-dlp handles). All processing is
local. No telemetry, no server.

## Stack

- Python 3.8+ (CI tests 3.9/3.10/3.11; dev machine runs 3.14)
- PyQt5 (GUI), yt-dlp (extraction/download), ffmpeg/ffprobe (external binaries)
- PyInstaller (packaging)

## Layout

```
socialclip_downloader.py   entry point + __version__
cli.py                     `socialclip` CLI (download/convert/doctor/manifest-schema/queue)
core/                      Qt-free logic shared by GUI and CLI (manifest, download, convert, formats, probe, queue, pipeline)
core/doctor.py             health report builder (ffmpeg, cookies, network); schema 1.1
core/formats.py            curated output-format registry (containers, codecs, remux allow-lists)
core/probe.py              single ffprobe call -> {vcodec, acodec, height, container}
core/queue.py              persistent download queue + QueueStore (thread-free)
sites/cookies.py           platform detection, cookie file lookup, error copy
sites/errors.py            classify_error() -> (category, friendly message)
ui/main_window.py          QTabWidget shell holding the three tabs
ui/dialogs.py              first-run welcome + Doctor report dialogs
ui/single_tab.py           Fetch -> metadata cache -> Download (also FetchWorker)
ui/batch_tab.py            QueueTab: persistent Queue tab (add/paste, pause/resume/cancel)
ui/convert_tab.py          local file format/resolution conversion
workers/download_worker.py single download + MP3/resolution post-process
workers/queue_worker.py    drives a Queue: one job at a time, saves after each
workers/convert_worker.py  local file conversion
utils/ffmpeg.py            ffmpeg/ffprobe discovery (env, PATH, common dirs)
utils/ydl_opts.py          yt-dlp opts, ffmpeg helpers, ANSI strip
utils/file_utils.py        filename sanitizing, unique paths, shared combos
utils/ui_helpers.py        looks_like_url, reveal_in_folder (Qt-free)
docs/plans/                implementation plans
docs/specs/                design specs
tests/                     pytest suite for pure logic
```

`core/` is Qt-free by rule: it must not import PyQt5/PySide so the CLI can use it
without a display. Enforced by `tests/test_core_isolation.py`. `core/queue.py`
is additionally **thread-free**: it only holds data and pure logic; the worker
(`workers/queue_worker.py`) owns the thread.

## Commands

```bash
python socialclip_downloader.py     # run the app
pip install -r requirements.txt     # runtime deps
pip install -r requirements-dev.txt # pytest + flake8
.\run.bat                           # Windows launcher
./run.sh                            # macOS/Linux launcher
.\build.bat                         # PyInstaller onefile build (Windows)
python -m pytest -q                 # tests
python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
```

## CI

- `python-package.yml` : flake8 + pytest on push/PR
- `gitleaks.yml` : secret scan (flags Netscape cookie exports)
- `release.yml` : on `v*` tag, builds Windows/macOS/Linux onefile binaries
  and attaches them to the GitHub Release. macOS/Linux builds are unproven
  locally (only Windows was validated); expect the first tag to be the test.
The `tests/` suite covers pure logic only (cookies, file utils, error
classification). GUI and worker threads are not unit-tested; keep new pure
helpers testable. CI lints and runs pytest.

## Conventions

- UI strings user-facing; keep them plain and helpful.
- Worker threads report through Qt signals; the GUI never runs network/ffmpeg
  work on the main thread.
- Reuse the shared combos in `utils/file_utils.py` (`OUTPUT_FORMATS`,
  `RESOLUTIONS`) instead of hardcoding lists; convert-tab formats come from
  the `core/formats.py` registry.
- Remux legality is defined by the per-format allow-lists in `core/formats.py`
  (`remux_v` / `remux_a`), never by ad-hoc compatibility checks in the
  converter. `core.convert.plan_conversion` is pure and gets the test suite.
- `core.convert.convert_file` keeps the legacy three-format path
  (`output_type` in MP3/WAV/MP4 + optional resolution) byte-identical. The
  format path (`target_format`) is additive; do not rewrite the legacy branch.
- Route any new user-facing error copy through
  `sites.errors.classify_error`; do not re-add keyword lists to the workers.
- Cancel is a callable checked in the yt-dlp progress hook
  (`core.download.download_one(cancel=...)`), not a Qt signal; a cancelled run
  returns `error_category == "cancelled"`, a distinct category from the six in
  `sites/errors.py` and a terminal queue state.
- The **doctor report** `schema_version` is `"1.1"`; the **download result**
  contract stays `"1.0"`. They are independent numbers, bump them separately.
- Conventional Commits (feat/fix/chore/docs). Never commit to `main` on shared
  work without the user asking.

## Gotchas

- ffmpeg/ffprobe are located by `utils/ffmpeg.py` (`ffmpeg_path()` /
  `ffprobe_path()`): env override `SOCIALCLIP_FFMPEG` or `FFMPEG_LOCATION`,
  then PATH, then common install dirs. `_nle_ydl_opts` passes the path to
  yt-dlp as `ffmpeg_location`. Facebook and other multi-stream sources still
  fail if ffmpeg is absent. Install: `winget install Gyan.FFmpeg` (Win),
  `brew install ffmpeg` (mac).
- Cookie auto-detect uses `os.getcwd()` (`sites/cookies.py:get_cookie_path`),
  which breaks when the app launches from another directory.
- `ydl_opts.py` postprocessor key uses yt-dlp's intentional misspelling
  `ffmpegvideoconvertor` and `preferedformat`. Do not "fix" the spelling.
- Duration from yt-dlp can be a float; coerce to `int` before `:02d` formatting.

## Adding a platform

1. `sites/cookies.py`: add to `PLATFORM_PATTERNS`, `PLATFORM_NAMES`,
   `get_cookie_message`.
2. `README.md`: supported sites + cookie filename.
That is usually all; workers and UI are URL-generic.
