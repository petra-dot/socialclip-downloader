import sys

__version__ = "0.4.0"

PYQT_IMPORT_ERROR = None
YTDLP_IMPORT_ERROR = None
try:
    from PyQt5 import QtWidgets, QtCore
except Exception as e:
    QtWidgets = None
    QtCore = None
    PYQT_IMPORT_ERROR = e

try:
    from yt_dlp import YoutubeDL
except Exception as e:
    YoutubeDL = None
    YTDLP_IMPORT_ERROR = e


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
    from pathlib import Path

    app = QtWidgets.QApplication(sys.argv)

    qss_path = Path(__file__).parent / "ui" / "styles" / "dark.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()