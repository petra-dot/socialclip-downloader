import sys

__version__ = "0.6.1"

try:
    from PyQt5 import QtWidgets, QtCore
except Exception:
    QtWidgets = None
    QtCore = None

try:
    from yt_dlp import YoutubeDL
except Exception:
    YoutubeDL = None


def main():
    missing = []
    if YoutubeDL is None:
        missing.append("yt-dlp (Python package 'yt-dlp') - install with: pip install yt-dlp")
    if QtWidgets is None or QtCore is None:
        missing.append("PyQt5 - install with: pip install PyQt5")
    if missing:
        print("Missing required dependencies:")
        for m in missing:
            print(" - ", m)
        print("Or install all via: pip install -r requirements.txt")
        sys.exit(1)

    from ui.main_window import MainWindow

    from utils.ffmpeg import find_ffmpeg
    if not find_ffmpeg():
        print("Warning: ffmpeg was not found on PATH or in common install locations.")
        print("Downloads that need merging or conversion will fail. Install with:")
        print("  Windows: winget install Gyan.FFmpeg")
        print("  macOS:   brew install ffmpeg")
        print("  Linux:   sudo apt install ffmpeg")

    # Must be set before QApplication is constructed, otherwise it is a no-op.
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)

    app = QtWidgets.QApplication(sys.argv)
    app.setOrganizationName("petra-dot")
    app.setApplicationName("SocialClip Downloader")

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
