# 🎥 SocialClip Downloader (PyQt5 + yt-dlp)

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![yt-dlp](https://img.shields.io/badge/yt--dlp-latest-green.svg)](https://github.com/yt-dlp/yt-dlp)
[![PyQt5](https://img.shields.io/badge/PyQt5-latest-orange.svg)](https://pypi.org/project/PyQt5/)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Open Source](https://img.shields.io/badge/open%20source-yes-green.svg)](https://github.com/petra-dot/socialclip-downloader)

A free, open source desktop app to download videos and audio locally — no sketchy websites, no ads, no data collection.

## 📸 Screenshot

![App Screenshot](docs/screenshots/app_main.png)


## ✨ Features

- Single URL download (MP4 or MP3)
- Batch download — paste multiple URLs, downloads run in queue
- Resolution targeting: 720p, 1080p, 1440p, 2160p — no upscaling ever
- Video info preview: thumbnail, title, uploader, duration, platform
- Real-time progress bar during download
- Auto filename sanitization
- Optional: append channel name or timestamp to filename
- Built-in local file converter (MP4 → MP3, MP4 → WAV, resolution conversion)
- YouTube bot-detection bypass via cookies.txt
- Clear error messages — no silent failures
- 100% local — nothing is uploaded, no accounts needed, no tracking

## 🛠 Installation

### Prerequisites

1. **Python**: Version 3.8 or higher. Download from [python.org](https://www.python.org/downloads/).
2. **pip**: Included with Python. Verify with `python -m pip --version`.
3. **Node.js**: Required for YouTube video downloads. yt-dlp uses it to solve YouTube's JS challenge. Download the LTS version from [nodejs.org](https://nodejs.org). Verify with `node --version`.
4. **FFmpeg**: Install and add to PATH. Download from [ffmpeg.org](https://ffmpeg.org/download.html). Verify with `ffmpeg -version`.

### Steps

1. Clone the repo:
   ```bash
   git clone https://github.com/petra-dot/socialclip-downloader.git
   cd socialclip-downloader
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Verify everything is working:
   ```bash
   node --version
   ffmpeg -version
   ffprobe -version
   ```

## ▶️ Run

```bash
python socialclip_downloader.py
```

## 🖱️ Run via Batch File (Windows)

Create a `run.bat` file in the project root with this content:

```batch
@echo off
python socialclip_downloader.py
pause
```

- Ensure Python is added to your system PATH during installation.

## 📦 Build as EXE (Windows)

1. Run `build.bat`.
2. The EXE appears in the `dist/` folder.
3. Note: FFmpeg and Node.js must be installed separately by the end user.
4. Note: cookies.txt is never bundled.

## 🍪 YouTube Cookie Authentication

YouTube blocks automated downloads. Use cookies.txt to bypass this.

### Why Needed
- Avoids bot detection and "Sign in to confirm" errors.
- Required for age-restricted or private videos.

### Setup Steps
1. Create a throwaway Google account (not your main one).
2. Install Firefox or Brave browser.
3. Install the "Get cookies.txt LOCALLY" extension from the browser add-ons store.
4. Log in to YouTube with your throwaway account.
5. Visit youtube.com, click the extension icon, and export cookies.txt.
6. In the app, click "Browse..." under Cookies and select your cookies.txt file.

### Security Notes
- cookies.txt is gitignored — never commit it.
- Use a throwaway account, never your personal Google account.
- Re-export cookies.txt when downloads start failing again (cookies expire after a few weeks).

## 🗂️ Project Structure

```
socialclip-downloader/
├── assets/
│   └── icon.ico
├── docs/
│   └── screenshots/
│       └── app_main.png
├── build.bat
├── LICENSE
├── README.md
├── README_BUILD.md
├── requirements.txt
├── run.bat
├── socialclip_downloader.py
└── socialclip_downloader.spec
```

## 🤝 Contributing

Contributions are welcome! Fork the repo and submit a pull request. For major changes, open an issue first.

1. Fork the repository.
2. Create a new branch (`git checkout -b feature-branch`).
3. Commit your changes (`git commit -m 'Add some feature'`).
4. Push to the branch (`git push origin feature-branch`).
5. Open a pull request.

## 🙏 Acknowledgments

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) for the powerful video downloading capabilities.
- [PyQt5](https://riverbankcomputing.com/software/pyqt/intro) for the GUI framework.
- [FFmpeg](https://ffmpeg.org/) for media processing.
- [Node.js](https://nodejs.org) for YouTube JS challenge solving.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.