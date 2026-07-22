from PyQt5 import QtWidgets, QtCore

from ui.single_tab import SingleTab
from ui.batch_tab import BatchTab
from ui.convert_tab import ConvertTab
from ui.queue_tab import QueueTab


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        from socialclip_downloader import __version__
        self.setWindowTitle(f"SocialClip Downloader v{__version__}")
        self.setMinimumSize(900, 600)
        self.cookies_file = {"path": ""}
        self._version = __version__
        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar
        self.sidebar = QtWidgets.QListWidget()
        self.sidebar.setFixedWidth(170)
        self.sidebar.setObjectName("sidebar")
        items = [
            ("\u24d3", "Download"),    # ⤓
            ("\u2630", "Batch"),       # ☰
            ("\u21bb", "Convert"),     # ↻
            ("\u23f1", "Schedule"),    # ⏱
        ]
        for icon, label in items:
            item = QtWidgets.QListWidgetItem(f"  {icon}  {label}")
            item.setSizeHint(QtCore.QSize(170, 52))
            self.sidebar.addItem(item)
        self.sidebar.setCurrentRow(0)
        layout.addWidget(self.sidebar)

        # Right side: header + content
        right = QtWidgets.QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        # Header bar
        header = QtWidgets.QFrame()
        header.setObjectName("headerBar")
        header.setFixedHeight(44)
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)
        title = QtWidgets.QLabel(f"SocialClip Downloader v{self._version}")
        title.setObjectName("headerTitle")
        header_layout.addWidget(title)
        right.addWidget(header)

        # Content stack
        self.stack = QtWidgets.QStackedWidget()
        self.single_tab = SingleTab(self, self.cookies_file)
        self.batch_tab = BatchTab(self.cookies_file)
        self.convert_tab = ConvertTab()
        self.queue_tab = QueueTab(self.cookies_file)
        self.stack.addWidget(self.single_tab)   # index 0
        self.stack.addWidget(self.batch_tab)     # index 1
        self.stack.addWidget(self.convert_tab)   # index 2
        self.stack.addWidget(self.queue_tab)     # index 3
        right.addWidget(self.stack, 1)

        layout.addLayout(right, 1)

        # Connect sidebar
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
