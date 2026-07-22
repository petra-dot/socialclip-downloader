# SocialClip Downloader

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![yt-dlp](https://img.shields.io/badge/yt--dlp-latest-green.svg)](https://github.com/yt-dlp/yt-dlp)
[![PyQt5](https://img.shields.io/badge/PyQt5-latest-orange.svg)](https://pypi.org/project/PyQt5/)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A desktop application for downloading videos and audio from YouTube, Douyin, and other supported sites. Built with PyQt5 and yt-dlp. All processing is done locally on your machine.

## Screenshot

![App Screenshot](docs/screenshots/app_main.png)

## Features

- Download single videos as MP4 or MP3
- Batch download with queue management
- Resolution targeting (720p, 1080p, 1440p, 2160p)
- Video info preview with thumbnail
- Real-time progress tracking
- File converter (MP4 to MP3, MP4 to WAV, resolution conversion)
- Dark theme UI with sidebar navigation
- Concurrent download control and scheduling
- Filename sanitization with optional channel/timestamp naming
- Cookie-based authentication for YouTube

## Installation

### Prerequisites

1. **Python 3.8+**: Download from [python.org](https://www.python.org/downloads/)
2. **Node.js**: Required for YouTube downloads. Install from [nodejs.org](https://nodejs.org)
3. **FFmpeg**: Required for media processing. Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH

### Setup

```bash
git clone https://github.com/petra-dot/socialclip-downloader.git
cd socialclip-downloader
pip install -r requirements.txt
```

### Verify Dependencies

```bash
node --version
ffmpeg -version
ffprobe -version
```

## Usage

```bash
python main.py
```

Or on Windows, double-click `run.bat`.

## Build EXE (Windows)

Run `build.bat`. The executable will be in the `dist/` folder. Note: FFmpeg and Node.js must be installed separately by the end user.

## YouTube Cookie Authentication

YouTube may require cookies for certain videos. To use cookies:

1. Install the "Get cookies.txt LOCALLY" browser extension (Firefox or Chrome).
2. Log in to YouTube in your browser.
3. Export cookies using the extension.
4. In the app, click "Browse..." under Cookies and select the exported file.

Cookies are never committed to the repository (gitignored).

## Project Structure

```
socialclip-downloader/
├── assets/
│   └── icon.ico
├── dlqueue/
│   ├── __init__.py
│   ├── manager.py
│   └── models.py
├── docs/
│   └── screenshots/
│       └── app_main.png
├── sites/
│   ├── __init__.py
│   └── cookies.py
├── ui/
│   ├── __init__.py
│   ├── main_window.py
│   ├── single_tab.py
│   ├── batch_tab.py
│   ├── convert_tab.py
│   └── queue_tab.py
├── utils/
│   ├── __init__.py
│   ├── file_utils.py
│   └── ydl_opts.py
├── workers/
│   ├── __init__.py
│   ├── batch_worker.py
│   ├── convert_worker.py
│   └── download_worker.py
├── build.bat
├── LICENSE
├── main.py
├── README.md
├── requirements.txt
├── run.bat
├── socialclip_downloader.py
└── socialclip_downloader.spec
```

## Contributing

Contributions are welcome. Fork the repo and submit a pull request.

1. Fork the repository.
2. Create a new branch (`git checkout -b feature-branch`).
3. Commit your changes (`git commit -m 'Add some feature'`).
4. Push to the branch (`git push origin feature-branch`).
5. Open a pull request.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
