import os
import sys

__version__ = "0.9.0"

try:
    from PyQt5 import QtWidgets, QtCore, QtGui
except Exception:
    QtWidgets = None
    QtCore = None
    QtGui = None

try:
    from yt_dlp import YoutubeDL
except Exception:
    YoutubeDL = None


def _asset_path(name: str) -> str:
    """Resolve a bundled asset for both a source run and a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidate = os.path.join(base, "assets", name)
        if os.path.isfile(candidate):
            return candidate
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "assets", name)


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

    # Must be set before QApplication is constructed, otherwise it is a no-op.
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)

    app = QtWidgets.QApplication(sys.argv)
    app.setOrganizationName("petra-dot")
    app.setApplicationName("SocialClip Downloader")

    icon_path = _asset_path("icon.ico")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QtGui.QIcon(icon_path))

    from utils.ffmpeg import find_ffmpeg
    if not find_ffmpeg():
        # print() is invisible in the --windowed build (no stdout), so warn in the GUI.
        QtWidgets.QMessageBox.warning(
            None,
            "ffmpeg not found",
            "ffmpeg was not found on PATH or in common install locations.\n\n"
            "Downloads that need merging or conversion will fail.\n\n"
            "Install it with:\n"
            "  Windows: winget install Gyan.FFmpeg\n"
            "  macOS:   brew install ffmpeg\n"
            "  Linux:   sudo apt install ffmpeg",
        )

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
