import os
import subprocess
import sys

from PyQt5 import QtWidgets, QtCore, QtGui

from ui.single_tab import SingleTab
from ui.batch_tab import QueueTab
from ui.convert_tab import ConvertTab
from ui.dialogs import show_welcome, show_doctor
from ui.style import THEMES, THEME_LABELS, apply_theme
from ui.update_indicator import UpdateButton
from ui.dialogs import show_update_ready
from workers.update_worker import UpdateCheckWorker, UpdateDownloadWorker
from core.updater import (
    cleanup_update_temp, is_newer, select_asset, update_temp_path,
)


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        from socialclip_downloader import __version__
        self.__version__ = __version__
        self.setWindowTitle(f"SocialClip Downloader v{__version__}")
        self.setMinimumSize(820, 520)
        self.cookies_file = {"path": ""}
        self.settings = QtCore.QSettings()

        self._update_release = None
        self._update_asset = None
        self._update_path = ""
        self._update_state = "idle"
        self._check_worker = None
        self._download_worker = None
        cleanup_update_temp()

        self.init_ui()
        self._restore_geometry()
        self._apply_saved_theme()

        if not self.settings.value("first_run_done"):
            show_welcome(self)
            self.settings.setValue("first_run_done", True)

        QtCore.QTimer.singleShot(4000, self.check_for_updates)

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._build_menubar())

        header = QtWidgets.QHBoxLayout()
        header.addStretch(1)
        self.update_button = UpdateButton(self)
        self.update_button.clicked.connect(self._on_update_button)
        header.addWidget(self.update_button)
        layout.addLayout(header)

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
        help_menu.addAction(self._action("Check for updates", lambda: self.check_for_updates(force=True)))
        help_menu.addAction(self._action("&Doctor", lambda: show_doctor(self)))
        help_menu.addAction(self._action("&About", self.show_about))

        return menubar

    def _action(self, text, slot, shortcut=None):
        action = QtWidgets.QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QtGui.QKeySequence(shortcut))
        return action

    def check_for_updates(self, force=False):
        if self._update_state in ("downloading", "ready"):
            return
        if not force:
            last = self.settings.value("update/last_check", "")
            if last:
                try:
                    from datetime import datetime, timedelta, timezone
                    when = datetime.fromisoformat(last)
                    if datetime.now(timezone.utc) - when < timedelta(hours=24):
                        return
                except ValueError:
                    pass
        if self._check_worker and self._check_worker.isRunning():
            return
        from socialclip_downloader import __version__
        self._check_worker = UpdateCheckWorker(__version__)
        self._check_worker.done_signal.connect(self._on_update_available)
        self._check_worker.error_signal.connect(self._on_update_error)
        self._check_worker.start()

    def _stamp_check(self):
        from datetime import datetime, timezone
        self.settings.setValue("update/last_check", datetime.now(timezone.utc).isoformat())

    def _on_update_available(self, release):
        if self._update_state in ("downloading", "ready"):
            return
        self._stamp_check()
        if release is None:
            self._update_state = "idle"
            self.update_button.set_state("hidden")
            return
        from socialclip_downloader import __version__
        if not is_newer(release.version, __version__):
            self._update_state = "idle"
            self.update_button.set_state("hidden")
            return
        self._update_release = release
        self._update_asset = select_asset(release.assets)
        self._update_state = "available"
        self.update_button.set_state("available", version=release.version)

    def _on_update_error(self, message):
        self._stamp_check()
        self._update_state = "error"
        self.update_button.set_state("error", detail=message)

    def _on_update_button(self):
        state = self._update_state
        if state == "available":
            self._start_update_download()
        elif state == "downloading":
            if self._download_worker:
                self._download_worker.cancel()
            self._update_state = "available"
            self.update_button.set_state("available", version=self._update_release.version)
        elif state == "ready":
            self._install_update()
        elif state == "error":
            self.check_for_updates(force=True)

    def _start_update_download(self):
        if (not getattr(sys, "frozen", False) or sys.platform != "win32"
                or self._update_asset is None):
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(self._update_release.page_url))
            return
        self._update_path = update_temp_path(self._update_release.version)
        self._update_state = "downloading"
        self.update_button.set_state("downloading", detail="0%")
        self._download_worker = UpdateDownloadWorker(self._update_asset, self._update_path)
        self._download_worker.progress_signal.connect(
            lambda pct: self.update_button.set_state("downloading", detail="%d%%" % pct)
        )
        self._download_worker.done_signal.connect(self._on_update_downloaded)
        self._download_worker.error_signal.connect(self._on_update_error)
        self._download_worker.start()

    def _on_update_downloaded(self, path):
        self._update_state = "ready"
        self.update_button.set_state("ready", version=self._update_release.version)

    def _install_update(self):
        if not show_update_ready(self, self._update_release.version):
            return
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) if os.name == "nt" else 0
        subprocess.Popen(
            [self._update_path, "--apply-update", "--target", sys.executable],
            creationflags=flags, close_fds=True,
        )
        QtWidgets.QApplication.quit()

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
