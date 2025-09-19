# 🎥 SocialClip Downloader (PyQt5 + yt-dlp)

A simple GUI tool to download videos or audio (MP4 / MP3) from popular platforms like YouTube, TikTok, Instagram, Twitter/X, Facebook, Reddit, and more.  
Built with **Python + PyQt5 + yt-dlp**, includes resolution conversion and minimalistic status console.

This is a test project for learning purposes.

---

## ✨ Features

- Paste any video URL and auto-detect source.
- Download best quality or convert to chosen resolution (720p, 1080p, 2K, 4K).
- Convert to MP3 audio easily.
- Custom save directory.
- Minimalistic console for status updates.

---

## 🛠 Installation

### Prerequisites

1. **Python**: Make sure Python (version 3.7 or higher) is installed on your system.  
   Download Python: [https://www.python.org/downloads/](https://www.python.org/downloads/)

2. **pip**: Ensure `pip` (Python's package manager) is installed. It usually comes with Python. You can check by running:

   ```bash
   python -m pip --version
   ```

3. **FFmpeg**: Install FFmpeg and add it to your system's PATH.  
   Download FFmpeg: [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)

### Steps

1. Clone this repo:

   ```bash
   git clone https://github.com/petra-dot/socialclip-downloader-gui.git
   cd socialclip-downloader-gui
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Verify that FFmpeg is correctly installed by running:
   ```bash
   ffmpeg -version
   ```

---

## ▶️ Run

```bash
python socialclip_downloader.py
```

---

## 📦 Build as EXE (Windows)

1. Install PyInstaller:

   ```bash
   pip install pyinstaller
   ```

2. Build the executable:

   ```bash
   pyinstaller --onefile --noconsole video_downloader.py
   ```

   The `.exe` file will appear in the `dist/` directory.

---

## 🤝 Contributing

Contributions are welcome! If you'd like to improve this project, please fork the repository and submit a pull request. For major changes, please open an issue first to discuss what you would like to change.

1. Fork the repository.
2. Create a new branch (`git checkout -b feature-branch`).
3. Commit your changes (`git commit -m 'Add some feature'`).
4. Push to the branch (`git push origin feature-branch`).
5. Open a pull request.

---

## 🙏 Acknowledgments

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) for the powerful video downloading capabilities.
- [PyQt5](https://riverbankcomputing.com/software/pyqt/intro) for the GUI framework.
- [FFmpeg](https://ffmpeg.org/) for media processing.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
