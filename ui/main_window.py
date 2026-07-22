from PyQt5 import QtWidgets

from ui.single_tab import SingleTab
from ui.batch_tab import BatchTab
from ui.convert_tab import ConvertTab
from ui.queue_tab import QueueTab


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        from socialclip_downloader import __version__
        self.setWindowTitle(f"SocialClip Downloader v{__version__}")
        self.setMinimumSize(820, 520)
        self.cookies_file = {"path": ""}
        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QtWidgets.QTabWidget()
        self.single_tab = SingleTab(self, self.cookies_file)
        self.batch_tab = BatchTab(self.cookies_file)
        self.convert_tab = ConvertTab()
        self.queue_tab = QueueTab(self.cookies_file)
        self.tabs.addTab(self.single_tab, "Download")
        self.tabs.addTab(self.batch_tab, "Batch")
        self.tabs.addTab(self.convert_tab, "Convert")
        self.tabs.addTab(self.queue_tab, "Queue")
        layout.addWidget(self.tabs)
