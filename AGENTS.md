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
sites/cookies.py           platform detection, cookie file lookup, error copy
sites/errors.py            classify_error() -> (category, friendly message)
ui/main_window.py          QTabWidget shell holding the three tabs
ui/single_tab.py           Fetch -> metadata cache -> Download (also FetchWorker)
ui/batch_tab.py            one-URL-per-line bulk download
ui/convert_tab.py          local file format/resolution conversion
workers/download_worker.py single download + MP3/resolution post-process
workers/batch_worker.py    loop over URLs, per-item error handling
workers/convert_worker.py  local file conversion
workers/pipeline.py        plan_postprocess() decision table
utils/ffmpeg.py            ffmpeg/ffprobe discovery (env, PATH, common dirs)
utils/ydl_opts.py          yt-dlp opts, ffmpeg helpers, ANSI strip
utils/file_utils.py        filename sanitizing, unique paths, shared combos
tests/                     pytest suite for pure logic
```

## Commands

```bash
python socialclip_downloader.py     # run the app
pip install -r requirements.txt     # runtime deps
pip install -r requirements-dev.txt # pytest + flake8
.\run.bat                           # Windows launcher
.\build.bat                         # PyInstaller onefile build (Windows)
python -m pytest -q                 # tests
python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
```

The `tests/` suite covers pure logic only (cookies, file utils, error
classification). GUI and worker threads are not unit-tested; keep new pure
helpers testable. CI lints and runs pytest.

## Conventions

- UI strings user-facing; keep them plain and helpful.
- Worker threads report through Qt signals; the GUI never runs network/ffmpeg
  work on the main thread.
- Reuse the shared combos in `utils/file_utils.py` (`OUTPUT_FORMATS`,
  `RESOLUTIONS`, `CONV_OUTPUT_FORMATS`) instead of hardcoding lists.
- Route any new user-facing error copy through
  `sites.errors.classify_error`; do not re-add keyword lists to the workers.
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
