from PyQt5 import QtWidgets, QtCore, QtGui

from ui.single_tab import SingleTab
from ui.batch_tab import QueueTab
from ui.convert_tab import ConvertTab
from ui.dialogs import show_welcome, show_doctor
from ui.style import THEMES, THEME_LABELS, apply_theme


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        from socialclip_downloader import __version__
        self.__version__ = __version__
        self.setWindowTitle(f"SocialClip Downloader v{__version__}")
        self.setMinimumSize(820, 520)
        self.cookies_file = {"path": ""}
        self.settings = QtCore.QSettings()
        self.init_ui()
        self._restore_geometry()
        self._apply_saved_theme()

        if not self.settings.value("first_run_done"):
            show_welcome(self)
            self.settings.setValue("first_run_done", True)

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._build_menubar())

        self.tabs = QtWidgets.QTabWidget()
        self.single_tab = SingleTab(self.cookies_file)
        self.batch_tab = QueueTab(self.cookies_file)
        self.convert_tab = ConvertTab()
        self.tabs.addTab(self.single_tab, "Download")
        self.tabs.addTab(self.batch_tab, "Queue")
        self.tabs.addTab(self.convert_tab, "Convert")
        self.tabs.setAccessibleName("Main sections")
        layout.addWidget(self.tabs)

        # Ctrl+1/2/3 switch tabs, the desktop convention.
        for index in range(3):
            shortcut = QtWidgets.QShortcut(
                QtGui.QKeySequence("Ctrl+%d" % (index + 1)), self
            )
            shortcut.activated.connect(
                lambda i=index: self.tabs.setCurrentIndex(i)
            )

        self.single_tab.collection_requested.connect(self._route_collection)

    def _route_collection(self, url):
        self.tabs.setCurrentWidget(self.batch_tab)
        self.batch_tab.expand_collection_url(url)

    def _build_menubar(self):
        menubar = QtWidgets.QMenuBar(self)

        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self._action("&Paste URL", self.paste_url, "Ctrl+V"))
        file_menu.addAction(
            self._action("&Open download folder", self.open_download_folder, "Ctrl+O")
        )
        file_menu.addSeparator()
        file_menu.addAction(self._action("&Quit", self.close, "Ctrl+Q"))

        view_menu = menubar.addMenu("&View")
        theme_menu = view_menu.addMenu("&Theme")
        self._theme_actions = {}
        for mode in THEMES:
            action = QtWidgets.QAction(
                THEME_LABELS.get(mode, mode.capitalize()), self, checkable=True
            )
            action.triggered.connect(lambda _c, m=mode: self.set_theme(m))
            theme_menu.addAction(action)
            self._theme_actions[mode] = action

        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self._action("&Doctor", lambda: show_doctor(self)))
        help_menu.addAction(self._action("&About", self.show_about))

        return menubar

    def _action(self, text, slot, shortcut=None):
        action = QtWidgets.QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QtGui.QKeySequence(shortcut))
        return action

    def paste_url(self):
        text = QtWidgets.QApplication.clipboard().text().strip()
        if not text:
            return
        self.tabs.setCurrentWidget(self.single_tab)
        self.single_tab.url_input.setText(text)
        self.single_tab.url_input.setFocus()

    def open_download_folder(self):
        from utils.ui_helpers import reveal_in_folder
        from utils.file_utils import default_download_folder

        folder = self.single_tab.save_dir_input.text().strip() or default_download_folder()
        reveal_in_folder(folder)

    def set_theme(self, mode: str):
        self.settings.setValue("ui/theme", mode)
        app = QtWidgets.QApplication.instance()
        if app is not None:
            apply_theme(app, mode)
        self._sync_theme_actions(mode)

    def _apply_saved_theme(self):
        mode = self.settings.value("ui/theme", "system")
        app = QtWidgets.QApplication.instance()
        if app is not None:
            apply_theme(app, mode)
        self._sync_theme_actions(mode)

    def _sync_theme_actions(self, mode: str):
        for name, action in getattr(self, "_theme_actions", {}).items():
            action.setChecked(name == mode)

    def show_about(self):
        QtWidgets.QMessageBox.about(
            self,
            "About SocialClip Downloader",
            "<b>SocialClip Downloader v%s</b><br><br>"
            "Download video and audio from YouTube, TikTok, Instagram, "
            "Facebook, Bilibili, Douyin and other yt-dlp sites.<br><br>"
            "Built with PyQt5 and yt-dlp. All processing is local: no "
            "accounts, no telemetry.<br><br>"
            "Licensed under MIT. Download only what you have the right to."
            % self.__version__,
        )

    def _restore_geometry(self):
        geometry = self.settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        self.settings.setValue("window/geometry", self.saveGeometry())
        super().closeEvent(event)
