from PyQt5 import QtWidgets, QtCore

from ui.single_tab import SingleTab
from ui.batch_tab import BatchTab
from ui.convert_tab import ConvertTab
from ui.dialogs import show_welcome, show_doctor


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        from socialclip_downloader import __version__
        self.setWindowTitle(f"SocialClip Downloader v{__version__}")
        self.setMinimumSize(820, 520)
        self.cookies_file = {"path": ""}
        self.init_ui()
        self._restore_geometry()

        settings = QtCore.QSettings()
        if not settings.value("first_run_done"):
            show_welcome(self)
            settings.setValue("first_run_done", True)

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        menubar = QtWidgets.QMenuBar(self)
        help_menu = menubar.addMenu("Help")
        help_menu.addAction("Doctor", lambda: show_doctor(self))
        layout.addWidget(menubar)

        self.tabs = QtWidgets.QTabWidget()
        self.single_tab = SingleTab(self.cookies_file)
        self.batch_tab = BatchTab(self.cookies_file)
        self.convert_tab = ConvertTab()
        self.tabs.addTab(self.single_tab, "Download")
        self.tabs.addTab(self.batch_tab, "Batch")
        self.tabs.addTab(self.convert_tab, "Convert")
        layout.addWidget(self.tabs)

    def _restore_geometry(self):
        settings = QtCore.QSettings()
        geometry = settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        QtCore.QSettings().setValue("window/geometry", self.saveGeometry())
        super().closeEvent(event)
