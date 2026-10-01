# SocialClip Downloader

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![yt-dlp](https://img.shields.io/badge/yt--dlp-latest-green.svg)](https://github.com/yt-dlp/yt-dlp)
[![PyQt5](https://img.shields.io/badge/PyQt5-latest-orange.svg)](https://pypi.org/project/PyQt5/)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Desktop application for downloading videos and audio from YouTube, Douyin, Instagram, Twitter/X, TikTok, Bilibili, Facebook, and other yt-dlp-supported sites. Built with PyQt5 and yt-dlp. All processing is local.

![SocialClip Downloader](docs/screenshots/app_main.png)

## Features

- **Single download** — paste a URL and metadata is fetched automatically; preview thumbnail, download as MP4 or MP3, then **Open folder** to reveal the saved file
- **Queue** — add multiple URLs (type them, or **Paste** from the clipboard), then run them one at a time with pause, resume, per-item cancel, and cancel-all; the queue is saved to disk so it survives a restart
- **File converter** — convert a local file to any registry format; video targets can be downscaled to a chosen resolution (never upscaled)
- **Doctor** — first-run welcome and a **Doctor** report (ffmpeg, cookies, network reachability) from the Help menu
- **Resolution targeting** — 720p, 1080p, 1440p, 2160p
- **Auto cookie detection** — per-platform cookie files (`douyin_cookies.txt`, `youtube_cookies.txt`, etc.) are picked up automatically
- **Platform-aware error messages** — shows the correct site name in blocked/cookie errors
- **Filename options** — append channel name and/or timestamp

## Supported Sites

YouTube, Douyin, Instagram, Twitter/X, TikTok, Bilibili, Facebook, and anything yt-dlp supports.

## Installation

### Option A: Download a release binary (no Python needed)

Grab the build for your OS from the
[releases page](https://github.com/petra-dot/socialclip-downloader/releases):

- Windows: `socialclip-downloader-windows.exe`
- macOS: `socialclip-downloader-macos`
- Linux: `socialclip-downloader-linux`

ffmpeg is bundled, so no separate install is needed.

**macOS (unsigned binary).** The build is not code-signed or notarized, so
Gatekeeper will block it on first launch ("cannot be opened because the
developer cannot be verified"). Pick one:

- Right-click the file, choose **Open**, then **Open** again; or
- `xattr -dr com.apple.quarantine socialclip-downloader-macos` in Terminal; or
- System Settings → Privacy & Security → **Open Anyway**.

**Linux.** Mark it executable: `chmod +x socialclip-downloader-linux`.

### Option B: Run from source

1. **Python 3.8+**: Download from [python.org](https://www.python.org/downloads/)
2. **FFmpeg**: Required for media processing. Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH, or set `SOCIALCLIP_FFMPEG` to its path

```bash
pip install -r requirements.txt
```

## Usage

```bash
python socialclip_downloader.py
```

Launchers: `run.bat` (Windows), `run.sh` (macOS/Linux).

## Command-line usage

The same engine is available headless through `cli.py`, and as a console
binary (`socialclip-windows.exe`, `socialclip-macos`, `socialclip-linux`) on
the [releases page](https://github.com/petra-dot/socialclip-downloader/releases).

```bash
socialclip download URL [--format mp4|mp3] [--resolution 1080] [--output DIR] [--cookies FILE]
socialclip convert FILE [--to KEY] [--copy|--no-copy]
socialclip doctor
socialclip manifest-schema
socialclip queue add URL [URL ...]
socialclip queue list
socialclip queue run
socialclip queue clear
```

- `download` — fetch one URL and save it as MP4 or MP3.
- `convert` — convert a local file to a registry format key: `mp4`, `mkv`,
  `webm`, `mov`, `avi`, `gif`, `mp3`, `m4a`, `wav`, `flac`, `ogg`, `opus`,
  `aac`, or `wma`. Streams are auto-remuxed when they already fit the
  container; `--copy` forces a stream copy, `--no-copy` forces a re-encode.
  Without `--to` it falls back to the legacy MP3 path. In the GUI, video
  format targets can also be downscaled to the chosen resolution.
- `doctor` — health report: ffmpeg presence/version, cookie files found, and
  network reachability. Exits `0` when ffmpeg is found, `3` otherwise.
- `manifest-schema` — print the JSON Schema for the result manifest.
- `queue add|list|run|clear` — manage a persistent download queue:
  - `add` — append one or more URLs as pending jobs.
  - `list` — print each job's state and URL.
  - `run` — process pending jobs one at a time, saving after each.
  - `clear` — remove every job from the queue.

Add `--json` to `download`, `convert`, or `doctor` for machine-readable output:
exactly one JSON object on stdout, human-readable text on stderr.

The doctor report carries its own `schema_version` (`"1.1"`), independent of the
download result contract (`"1.0"`).

```console
$ socialclip doctor --json
{"schema_version": "1.1", "ffmpeg": {"found": true, "path": "/usr/bin/ffmpeg", "version": "ffmpeg version 6.1 Copyright (c) 2000-2024 the FFmpeg developers"}, "cookies": [{"platform": "YouTube", "found": false, "path": null}], "network": {"ok": true, "detail": "reachable"}}
```

- `ffmpeg` — `{found, path, version}`; `path`/`version` are `null` when absent.
- `cookies` — one entry per supported platform: `{platform, found, path}`.
- `network` — `{ok, detail}`; `ok` is `true`/`false`/`null` and never raises.

The `queue` commands also take `--json` (`add`/`clear` report a count, `list`
reports the jobs, `run` reports a summary):

```console
$ socialclip queue list --json
{"schema_version": "1.0", "jobs": [{"id": "9f2c...", "url": "https://...", "state": "pending", "message": "", "path": null}]}
```

A job's state is one of `pending`, `running`, `done`, `failed`, `cancelled`,
or `paused`. **Cancelled** is its own outcome (and the `/cancelled` error
category): stopping a download that the queue itself started never removes or
overwrites a file that already existed, it only cleans up the partial file it
created.

The queue is stored as JSON in the app config directory (`queue.json`, next to
the auto-detected cookie files). Set `SOCIALCLIP_QUEUE` to a path to override
it; the GUI **Queue** tab and the CLI commands share the same file.

From source, use `python cli.py <command>` instead of `socialclip`.

## Queue

The **Queue** tab (which replaced the old Batch tab in v0.9) holds a table of
URLs with per-item status. **Add URLs** or **Paste** to enqueue, then **Start**
to download them one at a time. While running you can **Pause**/**Resume**,
**Cancel** the current item, or **Clear finished** to drop everything in a
terminal state (`done`, `failed`, `cancelled`). The queue is reloaded on
startup, so unfinished jobs are still there after a restart.

## Cookie Authentication

Some sites block downloads without cookies. For each platform you use:

1. Install the "Get cookies.txt LOCALLY" browser extension.
2. Log in to the site, export cookies, and save as `<platform>_cookies.txt` in the app directory.
3. The app auto-detects cookie files on fetch. You can also set a custom path via the **Browse** button.

Supported names: `youtube_cookies.txt`, `douyin_cookies.txt`, `instagram_cookies.txt`, `twitter_cookies.txt`, `tiktok_cookies.txt`, `bilibili_cookies.txt`, `facebook_cookies.txt`.

## Project Structure

```
socialclip-downloader/
├── assets/
│   └── icon.ico
├── sites/
│   ├── __init__.py
│   ├── cookies.py
│   └── errors.py
├── core/
│   ├── __init__.py
│   ├── queue.py
│   ├── download.py
│   ├── convert.py
│   ├── manifest.py
│   ├── doctor.py
│   └── pipeline.py
├── ui/
│   ├── __init__.py
│   ├── main_window.py
│   ├── single_tab.py
│   ├── batch_tab.py
│   └── convert_tab.py
├── utils/
│   ├── __init__.py
│   ├── file_utils.py
│   ├── ffmpeg.py
│   └── ydl_opts.py
├── workers/
│   ├── __init__.py
│   ├── queue_worker.py
│   ├── convert_worker.py
│   ├── download_worker.py
│   └── pipeline.py
├── tests/
├── socialclip_downloader.py
├── requirements.txt
├── requirements-dev.txt
├── run.bat
├── run.sh
├── build.bat
└── socialclip_downloader.spec
```

## License

MIT. See [LICENSE](LICENSE).
