from PyQt5 import QtWidgets

from ui.single_tab import SingleTab
from ui.batch_tab import BatchTab
from ui.convert_tab import ConvertTab


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        from socialclip_downloader import __version__
        self.setWindowTitle(f"SocialClip Downloader v{__version__}")
        self.setMinimumSize(820, 520)
        self.cookies_file = {"path": ""}
        self.init_ui()

    def init_ui(self):
        self.tabs = QtWidgets.QTabWidget()
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().addWidget(self.tabs)

        self.single_tab = SingleTab(self, self.cookies_file)
        self.tabs.addTab(self.single_tab, "Single Download")

        self.batch_tab = BatchTab(self.cookies_file)
        self.tabs.addTab(self.batch_tab, "Batch Download")

        self.convert_tab = ConvertTab()
        self.tabs.addTab(self.convert_tab, "Convert File")
