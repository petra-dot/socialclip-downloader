# SocialClip Downloader

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![yt-dlp](https://img.shields.io/badge/yt--dlp-latest-green.svg)](https://github.com/yt-dlp/yt-dlp)
[![PyQt5](https://img.shields.io/badge/PyQt5-latest-orange.svg)](https://pypi.org/project/PyQt5/)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Desktop application for downloading videos and audio from YouTube, Douyin, Instagram, Twitter/X, TikTok, Bilibili, Facebook, and other yt-dlp-supported sites. Built with PyQt5 and yt-dlp. All processing is local.

## Features

- **Single download** — fetch metadata, preview thumbnail, download as MP4 or MP3
- **Batch download** — paste multiple URLs, bulk download with per-file conversion
- **File converter** — convert MP4 to MP3/WAV, downscale resolution
- **Resolution targeting** — 720p, 1080p, 1440p, 2160p
- **Auto cookie detection** — per-platform cookie files (`douyin_cookies.txt`, `youtube_cookies.txt`, etc.) are picked up automatically
- **Platform-aware error messages** — shows the correct site name in blocked/cookie errors
- **Filename options** — append channel name and/or timestamp

## Supported Sites

YouTube, Douyin, Instagram, Twitter/X, TikTok, Bilibili, Facebook, and anything yt-dlp supports.

## Installation

### Prerequisites

1. **Python 3.8+**: Download from [python.org](https://www.python.org/downloads/)
2. **FFmpeg**: Required for media processing. Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH

### Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
python socialclip_downloader.py
```

Or double-click `run.bat` on Windows.

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
│   └── cookies.py
├── ui/
│   ├── __init__.py
│   ├── main_window.py
│   ├── single_tab.py
│   ├── batch_tab.py
│   └── convert_tab.py
├── utils/
│   ├── __init__.py
│   ├── file_utils.py
│   └── ydl_opts.py
├── workers/
│   ├── __init__.py
│   ├── batch_worker.py
│   ├── convert_worker.py
│   └── download_worker.py
├── socialclip_downloader.py
├── requirements.txt
├── run.bat
├── build.bat
└── socialclip_downloader.spec
```

## License

MIT. See [LICENSE](LICENSE).
