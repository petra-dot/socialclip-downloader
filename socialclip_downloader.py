import sys

__version__ = "0.6.0"

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

    app = QtWidgets.QApplication(sys.argv)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()