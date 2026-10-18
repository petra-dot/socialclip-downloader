import datetime
import os
import subprocess
import sys

from PyQt5 import QtWidgets, QtCore, QtGui

from ui.single_tab import SingleTab
from ui.batch_tab import QueueTab
from ui.convert_tab import ConvertTab
from ui.history_tab import HistoryTab
from ui.dialogs import show_welcome, show_doctor
from ui.style import THEMES, THEME_LABELS, apply_theme
from ui.update_indicator import UpdateButton
from ui.dialogs import show_update_ready
from core.paths import data_dir
from utils.ui_helpers import reveal_in_folder
from workers.maintenance_worker import (
    MaintenanceCheckWorker, MaintenanceRepairWorker,
)
from workers.update_worker import UpdateCheckWorker, UpdateDownloadWorker
from core.updater import (
    cleanup_update_temp, is_newer, select_asset, update_temp_path,
)


def _within_a_day(stamp: str) -> bool:
    """True when `stamp` (ISO 8601) is less than a day old. Pure."""
    try:
        when = datetime.datetime.fromisoformat(stamp)
        age = datetime.datetime.now() - when
    except (ValueError, TypeError):
        return False
    return age < datetime.timedelta(hours=24)


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
        self._maintenance_worker = None
        self._repair_worker = None
        cleanup_update_temp()

        self._apply_app_theme()        # before init_ui: nothing to re-polish
        self.init_ui()
        # Resolve every layout now, while no window is on screen. Otherwise the
        # whole tree lays out inside the first paint, which shows as a blank
        # frame before the interface appears.
        for index in range(self.tabs.count()):
            page = self.tabs.widget(index)
            if page.layout() is not None:
                page.layout().activate()
        if self.layout() is not None:
            self.layout().activate()
        self._restore_geometry()
        self._sync_theme_actions(self.settings.value("ui/theme", "system"))
        self._refresh_theme_colors()

        if not self.settings.value("first_run_done"):
            show_welcome(self)
            self.settings.setValue("first_run_done", True)

        QtCore.QTimer.singleShot(4000, self.check_for_updates)

    def start_background_work(self):
        """Run the startup checks once the first frame is painted.

        Importing yt-dlp and spawning ffmpeg for the component check both stall
        the machine for a moment. Done while the window is mapping, that stall
        shows as a blank frame before the interface draws.
        """
        self._warn_if_ytdlp_stale()
        self._check_components()

    def init_ui(self):
        from ui.style import space
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._build_menubar())

        self.tabs = QtWidgets.QTabWidget()
        self.single_tab = SingleTab(self.cookies_file)
        self.batch_tab = QueueTab(self.cookies_file)
        self.convert_tab = ConvertTab()
        self.history_tab = HistoryTab()
        self.tabs.addTab(self.single_tab, "Download")
        self.tabs.addTab(self.batch_tab, "Queue")
        self.tabs.addTab(self.convert_tab, "Convert")
        self.tabs.addTab(self.history_tab, "History")
        self.tabs.setAccessibleName("Main sections")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.update_button = UpdateButton(self)
        self.update_button.clicked.connect(self._on_update_button)
        self.tabs.setCornerWidget(self.update_button, QtCore.Qt.TopRightCorner)

        layout.addWidget(self.tabs)
        layout.setSpacing(space("sm"))

        # Ctrl+1/2/3/4 switch tabs, the desktop convention.
        for index in range(4):
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

    def _on_tab_changed(self, index):
        """Refresh History when it is shown, so its status is never stale."""
        if self.tabs.widget(index) is self.history_tab:
            self.history_tab.refresh()

    def _build_menubar(self):
        menubar = QtWidgets.QMenuBar(self)

        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self._action("&Paste URL", self.paste_url, "Ctrl+V"))
        file_menu.addAction(
            self._action("&Open download folder", self.open_download_folder, "Ctrl+O")
        )
        file_menu.addAction(self._action("&Cookies...", self.open_cookies))
        file_menu.addAction(self._action(
            "Open data folder", lambda: reveal_in_folder(data_dir())
        ))
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
        help_menu.addAction(self._action(
            "&Health", lambda: show_doctor(self, on_repair=self._repair_components)
        ))
        help_menu.addAction(self._action(
            "Check components", lambda: self._check_components(force=True)
        ))
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

    def _warn_if_ytdlp_stale(self):
        """Say once, in the activity log, when yt-dlp has gone stale.

        YouTube extraction breaks as yt-dlp ages, and a frozen build cannot
        update the copy it ships, so the user needs to hear it from us.
        """
        from utils.ytdlp import is_stale, version_age_days, ytdlp_version
        version = ytdlp_version()
        if not version or not is_stale(version):
            return
        age = version_age_days(version)
        self.single_tab.log(
            "yt-dlp %s is %s days old. YouTube extraction breaks when it is "
            "stale; update with: pip install -U yt-dlp" % (version, age)
        )

    def open_cookies(self):
        from ui.dialogs import CookiesDialog
        dialog = CookiesDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.settings.setValue("cookies/browser", dialog.chosen_browser())

    def log(self, message):
        self.single_tab.log(message)

    def _check_components(self, force=False):
        """Check components at most once a day; repair what is broken."""
        if self._maintenance_worker and self._maintenance_worker.isRunning():
            self.log("Component check already running")
            return
        if not force:
            last = self.settings.value("maintenance/last_check", "") or ""
            if last and _within_a_day(last):
                return
        self._maintenance_worker = MaintenanceCheckWorker()
        self._maintenance_worker.done_signal.connect(self._on_components_checked)
        self._maintenance_worker.error_signal.connect(self._on_check_error)
        self._maintenance_worker.start()

    def _on_components_checked(self, components):
        from core.maintenance import plan_repairs
        self.settings.setValue(
            "maintenance/last_check", datetime.datetime.now().isoformat()
        )
        keys = plan_repairs(components)
        if not keys:
            return
        if self._repair_worker and self._repair_worker.isRunning():
            self.log("A repair is already running")
            return
        self.log("Repairing: %s" % ", ".join(keys))
        self._start_repair(keys)

    def _on_repair_done(self, components):
        from core.maintenance import plan_repairs
        remaining = plan_repairs(components)
        self.log(
            "Repair finished" if not remaining
            else "Still needs attention: %s" % ", ".join(remaining)
        )

    def _on_check_error(self, message):
        self.log("Component check failed: %s" % message)

    def _on_repair_error(self, message):
        self.log("Repair failed: %s" % message)

    def _start_repair(self, keys):
        self._repair_worker = MaintenanceRepairWorker(keys)
        self._repair_worker.done_signal.connect(self._on_repair_done)
        self._repair_worker.error_signal.connect(self._on_repair_error)
        self._repair_worker.progress_signal.connect(
            lambda key, detail: self.log("%s: %s" % (key, detail))
        )
        self._repair_worker.start()

    def _repair_components(self, keys):
        if self._repair_worker and self._repair_worker.isRunning():
            self.log("A repair is already running")
            return
        self.log("Repairing: %s" % ", ".join(keys))
        self._start_repair(keys)

    def set_theme(self, mode: str):
        self.settings.setValue("ui/theme", mode)
        app = QtWidgets.QApplication.instance()
        if app is not None:
            apply_theme(app, mode)
        self._sync_theme_actions(mode)
        self._refresh_theme_colors()

    def _apply_app_theme(self):
        """Set the application style and palette.

        Called before any widget is built: switching the application style
        re-polishes every existing widget, and doing that to a built tree makes
        the window flash once at its pre-layout size before it is shown.
        """
        mode = self.settings.value("ui/theme", "system")
        app = QtWidgets.QApplication.instance()
        if app is not None:
            apply_theme(app, mode)
        return mode

    def _refresh_theme_colors(self):
        """Re-apply state colors after a theme change.

        Row brushes and inline stylesheets hold literal hex colors, so a
        palette switch does not reach them on its own.
        """
        self.batch_tab.refresh_table()
        self.single_tab.refresh_state_colors()
        self.convert_tab.refresh_state_colors()

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
