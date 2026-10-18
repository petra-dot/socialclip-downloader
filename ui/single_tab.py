import datetime
import os
import urllib.request

from PyQt5 import QtWidgets, QtCore, QtGui
from yt_dlp import YoutubeDL

from utils.file_utils import (
    clean_title,
    get_uploader,
    make_unique_filepath,
    default_download_folder,
    output_code_for,
    restore_or,
    RESOLUTIONS,
    output_index_for,
    BEST_RESOLUTION,
    resolution_to_convert,
)
from utils.ydl_opts import strip_ansi
from utils.ui_helpers import looks_like_url, reveal_in_folder
from core.clip import resolve_range
from core.formats import download_format_label
from core.presets import Preset, PresetStore, default_presets_path
from ui.dialogs import manage_presets
from workers.download_worker import DownloadWorker
from sites.cookies import (
    cookie_box_value,
    cookie_dialog_dir,
    get_cookie_path,
    detect_platform,
    get_cookie_message,
)
from sites.collections import classify_url
from sites.errors import classify_error
from ui.style import make_heading, make_result_panel, primary_button_style, space


PLACEHOLDER = "-"


class FetchWorker(QtCore.QThread):
    finished_signal = QtCore.pyqtSignal(object, int)
    error_signal = QtCore.pyqtSignal(str, int)

    def __init__(self, url, cookies_path=None, seq=0):
        super().__init__()
        self.url = url
        self.cookies_path = cookies_path
        self.seq = seq

    def run(self):
        opts = {
            "skip_download": True,
            "noplaylist": True,
            "age_limit": 99,
            "no_color": True,
        }
        if self.cookies_path and os.path.isfile(self.cookies_path):
            opts["cookiefile"] = self.cookies_path
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            self.finished_signal.emit(info, self.seq)
        except Exception as e:
            self.error_signal.emit(strip_ansi(str(e)), self.seq)


class ThumbnailWorker(QtCore.QThread):
    done_signal = QtCore.pyqtSignal(object, int, str)

    # Many thumbnail CDNs (Facebook, Instagram, Douyin) return 403 to a request
    # with no User-Agent, which is why the preview showed "Failed to load".
    _HEADERS = {"User-Agent": "Mozilla/5.0"}

    def __init__(self, thumbnail_url, seq=0, cookies_path=None):
        super().__init__()
        self.thumbnail_url = thumbnail_url
        self.seq = seq
        self.cookies_path = cookies_path

    def _headers(self):
        headers = dict(self._HEADERS)
        # Some platforms only serve the thumbnail to a signed-in request.
        try:
            if self.cookies_path and os.path.isfile(self.cookies_path):
                with open(self.cookies_path, "r", encoding="utf-8", errors="ignore") as fh:
                    pairs = []
                    for line in fh:
                        if line.startswith("#") or not line.strip():
                            continue
                        parts = line.rstrip("\n").split("\t")
                        if len(parts) >= 7:
                            pairs.append("%s=%s" % (parts[5], parts[6]))
                    if pairs:
                        headers["Cookie"] = "; ".join(pairs)
        except Exception:
            pass
        return headers

    def run(self):
        try:
            request = urllib.request.Request(self.thumbnail_url, headers=self._headers())
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read()
        except Exception as e:
            self.done_signal.emit(None, self.seq, "download failed: %s" % e)
            return

        # Decode and scale with QImage: QPixmap may only be touched on the GUI
        # thread, and this runs in a worker. The slot turns it into a QPixmap.
        image = QtGui.QImage()
        if not image.loadFromData(data):
            self.done_signal.emit(None, self.seq, "not a decodable image")
            return

        # Scale in device pixels so the thumbnail is 120x68 layout pixels
        # regardless of display scaling (otherwise it shrinks under HiDPI).
        dpr = 1.0
        try:
            screen = QtGui.QGuiApplication.primaryScreen()
            if screen is not None:
                dpr = screen.devicePixelRatio()
        except Exception:
            pass
        scaled = image.scaled(
            int(120 * dpr),
            int(68 * dpr),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(dpr)
        self.done_signal.emit(scaled, self.seq, "")


class SingleTab(QtWidgets.QWidget):
    collection_requested = QtCore.pyqtSignal(str)

    def __init__(self, cookies_file_ref):
        super().__init__()
        self.cookies_file_ref = cookies_file_ref
        self.worker = None
        self.fetch_worker = None
        self.thumb_worker = None
        self._cached_info = None
        self._fetch_url = ""
        self._fetch_seq = 0
        self._thumb_seq = 0
        self._last_path = ""
        self._current_url = ""
        self._last_cookie_url = ""
        self._last_percent = -1
        self.settings = QtCore.QSettings()
        self.preset_store = PresetStore(default_presets_path())
        self.preset_store.load()
        self._applying_preset = False
        self.init_ui()

    def init_ui(self):
        main = QtWidgets.QVBoxLayout()
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(6)

        # URL row
        url_row = QtWidgets.QHBoxLayout()
        self.url_input = QtWidgets.QLineEdit()
        self.url_input.setAccessibleName("Video URL")
        self.url_input.setPlaceholderText("Paste video URL here")
        self.url_input.editingFinished.connect(self._on_url_changed)
        # Enter fetches, the desktop convention for a URL field.
        self.url_input.returnPressed.connect(self.on_fetch_metadata)
        self.url_input.installEventFilter(self)
        self._url_timer = QtCore.QTimer(self)
        self._url_timer.setSingleShot(True)
        self._url_timer.setInterval(600)
        self._url_timer.timeout.connect(self._maybe_autofetch)
        self.url_input.textChanged.connect(self._on_url_text_changed)
        url_label = QtWidgets.QLabel("URL:")
        url_label.setBuddy(self.url_input)
        url_row.addWidget(url_label)
        url_row.addWidget(self.url_input)
        self.fetch_meta_btn = QtWidgets.QPushButton("Fetch")
        self.fetch_meta_btn.clicked.connect(self.on_fetch_metadata)
        url_row.addWidget(self.fetch_meta_btn)
        main.addLayout(url_row)

        # --- Video Info (hidden until fetch) ---
        self.info_section = QtWidgets.QWidget()
        info_section_layout = QtWidgets.QVBoxLayout(self.info_section)
        info_section_layout.setContentsMargins(0, 0, 0, 0)
        info_section_layout.setSpacing(4)

        info_heading = QtWidgets.QLabel("Video Info")
        make_heading(info_heading)
        info_section_layout.addWidget(info_heading)

        meta_layout = QtWidgets.QHBoxLayout()
        self.thumbnail_label = QtWidgets.QLabel("No preview")
        self.thumbnail_label.setFixedSize(120, 68)
        self.thumbnail_label.setAlignment(QtCore.Qt.AlignCenter)
        meta_layout.addWidget(self.thumbnail_label)
        meta_right = QtWidgets.QVBoxLayout()
        self.meta_title = QtWidgets.QLabel(f"Title: {PLACEHOLDER}")
        self.meta_uploader = QtWidgets.QLabel(f"Uploader: {PLACEHOLDER}")
        self.meta_duration = QtWidgets.QLabel(f"Duration: {PLACEHOLDER}")
        self.meta_platform = QtWidgets.QLabel(f"Platform: {PLACEHOLDER}")
        meta_right.addWidget(self.meta_title)
        meta_right.addWidget(self.meta_uploader)
        meta_right.addWidget(self.meta_duration)
        meta_right.addWidget(self.meta_platform)
        meta_layout.addLayout(meta_right)
        info_section_layout.addLayout(meta_layout)

        self.info_section.setVisible(False)
        main.addWidget(self.info_section)

        # --- Output ---
        output_heading = QtWidgets.QLabel("Output")
        make_heading(output_heading)
        main.addWidget(output_heading)

        preset_row = QtWidgets.QHBoxLayout()
        preset_row.addWidget(QtWidgets.QLabel("Preset:"))
        self.preset_combo = QtWidgets.QComboBox()
        self.preset_combo.setAccessibleName("Download preset")
        self.preset_combo.currentIndexChanged.connect(self.on_preset_selected)
        preset_row.addWidget(self.preset_combo)
        self.preset_save_btn = QtWidgets.QPushButton("Save as preset...")
        self.preset_save_btn.clicked.connect(self.on_save_preset)
        preset_row.addWidget(self.preset_save_btn)
        self.preset_manage_btn = QtWidgets.QPushButton("Manage")
        self.preset_manage_btn.clicked.connect(self.on_manage_presets)
        preset_row.addWidget(self.preset_manage_btn)
        preset_row.addStretch(1)
        main.addLayout(preset_row)

        out_row = QtWidgets.QHBoxLayout()
        self.output_combo = QtWidgets.QComboBox()
        self.output_combo.setAccessibleName("Output format")
        for code in ("MP4", "MP3"):
            self.output_combo.addItem(download_format_label(code), code)
        output_label = QtWidgets.QLabel("Output:")
        output_label.setBuddy(self.output_combo)
        out_row.addWidget(output_label)
        out_row.addWidget(self.output_combo)
        out_row.addSpacing(space("lg"))

        self.resolution_combo = QtWidgets.QComboBox()
        self.resolution_combo.setAccessibleName("Target resolution")
        self.resolution_combo.addItem(BEST_RESOLUTION)
        self.resolution_combo.addItems(RESOLUTIONS)
        self.resolution_combo.currentIndexChanged.connect(self._sync_output_state)
        resolution_label = QtWidgets.QLabel("Resolution:")
        resolution_label.setBuddy(self.resolution_combo)
        out_row.addWidget(resolution_label)
        out_row.addWidget(self.resolution_combo)
        out_row.addStretch()
        main.addLayout(out_row)
        self.output_combo.currentIndexChanged.connect(self._sync_output_state)
        self._sync_output_state()

        # Everything past the format choice is optional, so it lives behind one
        # disclosure instead of competing with Download for attention.
        self.advanced_widget = QtWidgets.QWidget()
        advanced_layout = QtWidgets.QVBoxLayout(self.advanced_widget)
        advanced_layout.setContentsMargins(0, 0, 0, 0)

        self.checkbox_channel = QtWidgets.QCheckBox("Add channel/uploader to filename")
        advanced_layout.addWidget(self.checkbox_channel)
        self.checkbox_timestamp = QtWidgets.QCheckBox("Add timestamp to filename")
        advanced_layout.addWidget(self.checkbox_timestamp)

        sub_row = QtWidgets.QHBoxLayout()
        subtitles_label = QtWidgets.QLabel("Subtitles:")
        sub_row.addWidget(subtitles_label)
        self.subtitle_combo = QtWidgets.QComboBox()
        self.subtitle_combo.setAccessibleName("Subtitle delivery")
        from core.subtitles import DELIVERY_CHOICES
        for value, label in DELIVERY_CHOICES:
            self.subtitle_combo.addItem(label, value)
        sub_row.addWidget(self.subtitle_combo)
        subtitles_label.setBuddy(self.subtitle_combo)
        sub_row.addStretch(1)
        advanced_layout.addLayout(sub_row)

        save_layout = QtWidgets.QHBoxLayout()
        self.save_dir_input = QtWidgets.QLineEdit(
            restore_or(default_download_folder(), self.settings.value("single/save_dir"))
        )
        self.save_dir_input.setAccessibleName("Download folder")
        self.save_dir_input.editingFinished.connect(self._on_save_dir_changed)
        save_label = QtWidgets.QLabel("Folder:")
        save_label.setBuddy(self.save_dir_input)
        save_layout.addWidget(save_label)
        save_layout.addWidget(self.save_dir_input)
        browse_btn = QtWidgets.QPushButton("Browse")
        browse_btn.clicked.connect(self.on_browse)
        save_layout.addWidget(browse_btn)
        main.addLayout(save_layout)

        self.advanced_toggle = QtWidgets.QToolButton()
        self.advanced_toggle.setText("Advanced")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setArrowType(QtCore.Qt.RightArrow)
        self.advanced_toggle.setToolTip(
            "Subtitles, clip range, filename options, and cookies."
        )
        self.advanced_toggle.toggled.connect(self._on_advanced_toggled)
        main.addWidget(self.advanced_toggle)
        self.advanced_widget.setVisible(False)
        main.addWidget(self.advanced_widget)

        # Download bar
        download_bar = QtWidgets.QHBoxLayout()
        self.download_btn = QtWidgets.QPushButton("Download")
        self.download_btn.setDefault(True)
        self.download_btn.setAutoDefault(True)
        self.download_btn.setMinimumWidth(120)
        self.download_btn.setStyleSheet(primary_button_style())
        self.download_btn.clicked.connect(self.on_download)
        download_bar.addWidget(self.download_btn)
        main.addLayout(download_bar)

        # Keyboard path to cancel: Ctrl+. only acts while a download runs, so
        # it can never start one. The button itself already takes Enter/Space.
        self.cancel_shortcut = QtWidgets.QShortcut(
            QtGui.QKeySequence("Ctrl+."), self
        )
        self.cancel_shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.cancel_shortcut.activated.connect(self._on_cancel_shortcut)

        # Inline hint for recoverable mistakes, instead of a modal popup.
        self.hint_label = QtWidgets.QLabel("")
        self.hint_label.setVisible(False)
        self.hint_label.setWordWrap(True)
        main.addWidget(self.hint_label)

        self.clip_check = QtWidgets.QCheckBox("Download a clip (time range)")
        self.clip_check.toggled.connect(self._on_clip_toggled)
        advanced_layout.addWidget(self.clip_check)

        self.clip_row = QtWidgets.QWidget()
        clip_layout = QtWidgets.QHBoxLayout(self.clip_row)
        clip_layout.setContentsMargins(0, 0, 0, 0)
        self.clip_mode_combo = QtWidgets.QComboBox()
        self.clip_mode_combo.setAccessibleName("Clip range mode")
        self.clip_mode_combo.addItem("Start + End", "end")
        self.clip_mode_combo.addItem("Start + Duration", "duration")
        self.clip_mode_combo.currentIndexChanged.connect(self._on_clip_mode_changed)
        clip_layout.addWidget(self.clip_mode_combo)
        self.clip_start_input = QtWidgets.QLineEdit()
        self.clip_start_input.setAccessibleName("Clip start time")
        self.clip_start_input.setPlaceholderText("Start, e.g. 1:30")
        clip_layout.addWidget(self.clip_start_input)
        self.clip_end_label = QtWidgets.QLabel("End")
        clip_layout.addWidget(self.clip_end_label)
        self.clip_end_input = QtWidgets.QLineEdit()
        self.clip_end_input.setAccessibleName("Clip end time or duration")
        self.clip_end_input.setPlaceholderText("End, e.g. 2:00")
        clip_layout.addWidget(self.clip_end_input)
        self.clip_exact_check = QtWidgets.QCheckBox("Exact cut")
        self.clip_exact_check.setToolTip("Re-encode for a frame-accurate cut")
        clip_layout.addWidget(self.clip_exact_check)
        clip_layout.addStretch(1)
        self.clip_row.setVisible(False)
        advanced_layout.addWidget(self.clip_row)

        # --- Cookies ---
        cookies_row = QtWidgets.QHBoxLayout()
        cookies_label = QtWidgets.QLabel("Cookies file:")
        cookies_label.setMinimumWidth(130)
        cookies_row.addWidget(cookies_label)
        self.cookies_input = QtWidgets.QLineEdit(
            self.settings.value("single/cookies", "") or ""
        )
        self.cookies_input.setAccessibleName("Cookies file path")
        self.cookies_input.setPlaceholderText("Optional: auto-detected per platform")
        self.cookies_input.editingFinished.connect(self._on_cookies_changed)
        cookies_row.addWidget(self.cookies_input)
        cookies_label.setBuddy(self.cookies_input)
        browse_cookies_btn = QtWidgets.QPushButton("Browse")
        browse_cookies_btn.clicked.connect(self.on_browse_cookies)
        cookies_row.addWidget(browse_cookies_btn)
        clear_cookies_btn = QtWidgets.QPushButton("Clear")
        clear_cookies_btn.setMinimumWidth(50)
        clear_cookies_btn.clicked.connect(self._clear_cookies)
        cookies_row.addWidget(clear_cookies_btn)
        advanced_layout.addLayout(cookies_row)

        # The log is a details view: hidden by default, opened on request.
        # It used to take every spare pixel, which made developer chatter the
        # largest element on the tab.
        self._main_layout = main
        self.details_toggle = QtWidgets.QToolButton()
        self.details_toggle.setText("Activity")
        self.details_toggle.setCheckable(True)
        self.details_toggle.setArrowType(QtCore.Qt.RightArrow)
        self.details_toggle.setToolTip("Show the full activity log.")
        self.details_toggle.toggled.connect(self._on_details_toggled)
        main.addWidget(self.details_toggle)

        self.console_log = QtWidgets.QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setMinimumHeight(120)
        self.console_log.setMaximumHeight(120)
        self.console_log.setAccessibleName("Activity log")
        self.console_log.setVisible(False)
        main.addWidget(self.console_log)

        for widget in (self.output_combo, self.resolution_combo):
            widget.currentIndexChanged.connect(self._mark_custom)
        for widget in (self.checkbox_channel, self.checkbox_timestamp):
            widget.toggled.connect(self._mark_custom)

        # Two panes: the form on the left, the shared result panel on the right.
        form = QtWidgets.QWidget()
        form.setLayout(main)
        self.result_panel, self.panel_labels = make_result_panel()
        self.panel_labels["body"].setText(
            "Downloads appear here, with the file name, codecs, and resolution."
        )

        box = self.panel_labels["layout"]
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setVisible(False)
        box.insertWidget(box.count() - 1, self.progress_bar)
        self.progress_label = QtWidgets.QLabel("")
        self.progress_label.setAccessibleName("Download progress detail")
        box.insertWidget(box.count() - 1, self.progress_label)

        self.open_folder_btn = QtWidgets.QPushButton("Open folder")
        self.open_folder_btn.setVisible(False)
        self.open_folder_btn.clicked.connect(self._on_open_folder)
        box.insertWidget(box.count() - 1, self.open_folder_btn)

        panes = QtWidgets.QHBoxLayout()
        panes.setSpacing(space("lg"))
        panes.addWidget(form, 3)
        panes.addWidget(self.result_panel, 2)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(space("md"), space("md"), space("md"), space("md"))
        root.addLayout(panes)

        self._refresh_presets()

    def _current_preset_name(self):
        return self.settings.value("preset/last", "")

    def _refresh_presets(self):
        self._applying_preset = True
        self.preset_combo.clear()
        for preset in self.preset_store.all():
            self.preset_combo.addItem(preset.name, preset.name)
        self.preset_combo.addItem("Custom", None)
        last = self._current_preset_name()
        index = self.preset_combo.findData(last) if last else -1
        self.preset_combo.setCurrentIndex(index if index >= 0 else self.preset_combo.count() - 1)
        self._applying_preset = False
        if index >= 0:
            preset = self.preset_store.get(last)
            if preset:
                self._apply_preset(preset)

    def on_preset_selected(self, _index):
        if self._applying_preset:
            return
        name = self.preset_combo.currentData()
        if not name:
            return
        preset = self.preset_store.get(name)
        if preset:
            self._apply_preset(preset)

    def _apply_preset(self, preset):
        self._applying_preset = True
        index = output_index_for(preset.output)
        if index >= 0:
            self.output_combo.setCurrentIndex(index)
        self.resolution_combo.setCurrentText(
            preset.resolution if preset.convert else BEST_RESOLUTION)
        self.checkbox_channel.setChecked(preset.add_channel)
        self.checkbox_timestamp.setChecked(preset.add_timestamp)
        self.save_dir_input.setText(preset.save_dir or default_download_folder())
        self.cookies_input.setText(preset.cookies or "")
        self.cookies_file_ref["path"] = preset.cookies or ""
        self._applying_preset = False
        self._on_save_dir_changed()
        self._on_cookies_changed()
        self.settings.setValue("preset/last", preset.name)

    def _mark_custom(self, *_args):
        if self._applying_preset:
            return
        index = self.preset_combo.findData(None)
        if index >= 0 and self.preset_combo.currentIndex() != index:
            self._applying_preset = True
            self.preset_combo.setCurrentIndex(index)
            self._applying_preset = False

    def _current_settings_preset(self, name):
        return Preset(
            name=name,
            output=output_code_for(self.output_combo.currentText()),
            convert=resolution_to_convert(self.resolution_combo.currentText()),
            resolution=(self.resolution_combo.currentText()
                        if resolution_to_convert(self.resolution_combo.currentText())
                        else "1080"),
            add_channel=self.checkbox_channel.isChecked(),
            add_timestamp=self.checkbox_timestamp.isChecked(),
            save_dir=self.save_dir_input.text().strip(),
            cookies=self.cookies_input.text().strip(),
        )

    def on_save_preset(self):
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Save preset", "Preset name:"
        )
        name = (name or "").strip()
        if not ok or not name:
            return
        if self.preset_store.get(name) is not None and name in [
            p.name for p in self.preset_store.user()
        ]:
            confirm = QtWidgets.QMessageBox.question(
                self, "Overwrite preset", "Overwrite '%s'?" % name
            )
            if confirm != QtWidgets.QMessageBox.Yes:
                return
        if not self.preset_store.add(self._current_settings_preset(name)):
            self.show_hint("That name is a built-in preset; pick another.")
            return
        self.preset_store.save()
        self.settings.setValue("preset/last", name)
        self._refresh_presets()
        self.preset_combo.setCurrentIndex(self.preset_combo.findData(name))

    def on_manage_presets(self):
        if manage_presets(self, self.preset_store):
            self.preset_store.save()
            self._refresh_presets()

    def show_hint(self, text: str):
        self.hint_label.setText(text)
        self.hint_label.setVisible(bool(text))

    def _announce(self, label, text):
        """Set a label and, best effort, notify assistive tech of the change."""
        label.setText(text)
        label.setAccessibleName(text)
        try:
            from PyQt5 import QtGui
            event = QtGui.QAccessibleEvent(label, QtGui.QAccessible.NameChanged)
            QtGui.QAccessible.updateAccessibility(event)
        except Exception:
            pass

    def _on_cancel_shortcut(self):
        """Ctrl+. cancels a running download; a no-op when nothing runs."""
        if self.worker and self.worker.isRunning():
            self.on_download()

    def _on_clip_toggled(self, checked):
        self.clip_row.setVisible(checked)

    def _on_clip_mode_changed(self, _index):
        mode = self.clip_mode_combo.currentData()
        if mode == "duration":
            self.clip_end_label.setText("Duration")
            self.clip_end_input.setPlaceholderText("Duration, e.g. 0:30")
        else:
            self.clip_end_label.setText("End")
            self.clip_end_input.setPlaceholderText("End, e.g. 2:00")

    def _resolve_clip(self):
        if not self.clip_check.isChecked():
            return None
        spec, error = resolve_range(
            self.clip_start_input.text(), self.clip_end_input.text(),
            self.clip_end_input.text(), self.clip_mode_combo.currentData(),
            exact=self.clip_exact_check.isChecked(),
        )
        if error:
            self.show_hint(error)
            return False  # invalid: block the download
        return spec

    def log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.console_log.append(f"[{ts}] {msg}")
        sb = self.console_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_cookies_changed(self):
        path = self.cookies_input.text().strip()
        self.cookies_file_ref["path"] = path
        self.settings.setValue("single/cookies", path)

    def _clear_cookies(self):
        """Clear the field and the stored path, not just the visible text."""
        self.cookies_input.clear()
        self._on_cookies_changed()

    def _on_save_dir_changed(self):
        text = self.save_dir_input.text().strip()
        if text:
            self.settings.setValue("single/save_dir", text)

    def _on_url_changed(self):
        url = self.url_input.text().strip()
        if url == self._fetch_url or (not url and not self._fetch_url):
            return
        self._cancel_fetch()
        self._cancel_thumbnail()
        self.thumbnail_label.clear()
        self.thumbnail_label.setText("No preview")
        self.meta_title.setText(f"Title: {PLACEHOLDER}")
        self.meta_uploader.setText(f"Uploader: {PLACEHOLDER}")
        self.meta_duration.setText(f"Duration: {PLACEHOLDER}")
        self.meta_platform.setText(f"Platform: {PLACEHOLDER}")
        self.info_section.setVisible(False)
        self._cached_info = None
        self._fetch_url = ""
        self.fetch_meta_btn.setEnabled(True)
        self.fetch_meta_btn.setText("Fetch")

    def _on_url_text_changed(self, text):
        self.open_folder_btn.setVisible(False)
        self._last_path = ""
        self._sync_cookies_for_url(text)
        self._url_timer.start()

    def _sync_cookies_for_url(self, url):
        """Show the cookie file this URL will use, when the URL changes.

        Guarded on the URL so a manual Browse/typed choice is not clobbered
        mid-URL: only a change of URL re-fills the box.
        """
        url = (url or "").strip()
        if url == self._last_cookie_url:
            return
        self._last_cookie_url = url
        value = cookie_box_value(url, self.cookies_input.text().strip())
        if self.cookies_input.text() != value:
            self.cookies_input.setText(value)
            self._on_cookies_changed()

    def _maybe_autofetch(self):
        if not looks_like_url(self.url_input.text()):
            return
        if self.fetch_worker and self.fetch_worker.isRunning():
            return
        self.on_fetch_metadata()

    def _fill_from_clipboard(self):
        if self.url_input.text().strip():
            return
        text = QtWidgets.QApplication.clipboard().text()
        if text and looks_like_url(text):
            self.url_input.setText(text.strip())

    def showEvent(self, event):
        super().showEvent(event)
        self._fill_from_clipboard()

    def eventFilter(self, obj, event):
        if obj is self.url_input and event.type() == QtCore.QEvent.FocusIn:
            self._fill_from_clipboard()
        return super().eventFilter(obj, event)

    def _sync_output_state(self, *_args):
        """The resolution only applies to video, and only when a height is set."""
        is_video = self.output_combo.currentData() == "MP4"
        self.resolution_combo.setEnabled(is_video)
        if not is_video:
            self.resolution_combo.setCurrentText(BEST_RESOLUTION)
        self.resolution_combo.setToolTip(
            "Re-encode the download at this height." if is_video
            else "Audio output keeps its source resolution."
        )

    def _on_advanced_toggled(self, checked):
        self.advanced_widget.setVisible(checked)
        self.advanced_toggle.setArrowType(
            QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
        )

    def _on_details_toggled(self, checked):
        self.console_log.setVisible(checked)
        self.console_log.setMaximumHeight(16777215 if checked else 120)
        self._main_layout.setStretchFactor(self.console_log, 1 if checked else 0)
        self.details_toggle.setArrowType(
            QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
        )

    def _on_open_folder(self):
        if self._last_path:
            reveal_in_folder(self._last_path)
        else:
            self.log("Nothing to reveal yet.")

    def on_browse_cookies(self):
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select cookies.txt",
            cookie_dialog_dir(self.cookies_input.text()),
            "Text files (*.txt);;All files (*)",
        )
        if file:
            self.cookies_input.setText(file)
            self._on_cookies_changed()
            self.log(f"Cookies file set: {file}")

    def _get_cookies_path(self):
        cf = self.cookies_file_ref.get("path", "").strip()
        if cf and os.path.isfile(cf):
            return cf
        return None

    def on_browse(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose folder", self.save_dir_input.text()
        )
        if folder:
            self.save_dir_input.setText(folder)
            self._on_save_dir_changed()

    def _cancel_thumbnail(self):
        if self.thumb_worker and self.thumb_worker.isRunning():
            try:
                self.thumb_worker.done_signal.disconnect()
            except TypeError:
                pass

    def _update_info_display(self, info):
        if not info:
            self.log("Could not fetch metadata. The video may be private or unavailable.")
            return
        self._cached_info = info
        title = info.get("title") or info.get("id") or "video"
        uploader = get_uploader(info) or PLACEHOLDER
        self.meta_title.setText(f"Title: {title}")
        self.meta_uploader.setText(f"Uploader: {uploader}")

        self._cancel_thumbnail()
        thumbnail_url = info.get("thumbnail")
        if thumbnail_url:
            self._thumb_seq += 1
            self.thumbnail_label.setText("Loading...")
            self.thumb_worker = ThumbnailWorker(
                thumbnail_url, self._thumb_seq, cookies_path=self._get_cookies_path()
            )
            self.thumb_worker.done_signal.connect(self._on_thumbnail_loaded)
            self.thumb_worker.start()
        else:
            self.thumbnail_label.setText("No thumbnail")

        duration = info.get("duration")
        if duration:
            duration = int(duration)
            if duration >= 3600:
                hours = duration // 3600
                minutes = (duration % 3600) // 60
                seconds = duration % 60
                duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                minutes = duration // 60
                seconds = duration % 60
                duration_str = f"{minutes:02d}:{seconds:02d}"
            self.meta_duration.setText(f"Duration: {duration_str}")
        else:
            self.meta_duration.setText(f"Duration: {PLACEHOLDER}")

        platform = info.get("extractor") or info.get("webpage_url_domain") or "Unknown"
        self.meta_platform.setText(f"Platform: {platform}")
        self.info_section.setVisible(True)
        self.log("Metadata fetched.")

    def _on_thumbnail_loaded(self, image, seq, reason=""):
        if seq != self._thumb_seq:
            return
        if image is not None and not image.isNull():
            # The worker can only build a QImage; QPixmap belongs to this thread.
            pixmap = QtGui.QPixmap.fromImage(image)
            pixmap.setDevicePixelRatio(image.devicePixelRatio())
            self.thumbnail_label.setPixmap(pixmap)
        else:
            # Show the cause instead of a generic message, and log it so the
            # reason survives in the console.
            self.thumbnail_label.setText("No preview")
            if reason:
                self.log(f"Thumbnail unavailable: {reason}")

    def _cancel_fetch(self):
        if self.fetch_worker and self.fetch_worker.isRunning():
            try:
                self.fetch_worker.finished_signal.disconnect()
            except TypeError:
                pass
            try:
                self.fetch_worker.error_signal.disconnect()
            except TypeError:
                pass

    def on_fetch_metadata(self):
        url = self.url_input.text().strip()
        if not url:
            self.show_hint("Paste a video URL first.")
            return
        if classify_url(url) == "collection":
            self.show_hint("This is a playlist or channel; opening the Queue.")
            self.collection_requested.emit(url)
            return
        if not looks_like_url(url):
            self.show_hint("That does not look like a URL.")
            return
        self.show_hint("")
        self._url_timer.stop()
        if self.fetch_worker and self.fetch_worker.isRunning():
            self.log("Already fetching. Waiting for current request...")
            return
        self._fetch_seq += 1
        self._fetch_url = url
        self._sync_cookies_for_url(url)
        self.log("Fetching metadata...")
        self.fetch_meta_btn.setEnabled(False)
        self.fetch_meta_btn.setText("Fetching...")
        cookies_path = self._get_cookies_path()
        self.fetch_worker = FetchWorker(url, cookies_path, self._fetch_seq)
        self.fetch_worker.finished_signal.connect(self._on_fetch_finished)
        self.fetch_worker.error_signal.connect(self._on_fetch_error)
        self.fetch_worker.start()

    def _on_fetch_finished(self, info, seq):
        self.fetch_meta_btn.setEnabled(True)
        self.fetch_meta_btn.setText("Fetch")
        if seq != self._fetch_seq:
            return
        self._update_info_display(info)

    def _on_fetch_error(self, error_msg, seq):
        self.fetch_meta_btn.setEnabled(True)
        self.fetch_meta_btn.setText("Fetch")
        if seq != self._fetch_seq:
            return
        url = self.url_input.text().strip()
        category, message = classify_error(error_msg, url)
        if category == "blocked":
            self.log(message)
            extra = get_cookie_message(detect_platform(url) if url else "")
            if extra:
                self.log(extra)
        elif category in ("format", "ffmpeg"):
            self.log(message)
        else:
            self.log(f"Metadata fetch failed: {message}")

    def on_download(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.download_btn.setEnabled(False)
            self.download_btn.setText("Cancelling...")
            self.log("Cancelling the download...")
            return
        url = self.url_input.text().strip()
        if not url:
            self.show_hint("Paste a video URL first.")
            return
        self._current_url = url
        if classify_url(url) == "collection":
            self.collection_requested.emit(url)
            return

        info = self._cached_info
        if not info:
            self.show_hint("Click Fetch to load the video info before downloading.")
            return
        self.show_hint("")

        clip = self._resolve_clip()
        if clip is False:
            return
        self.show_hint("")

        save_dir = self.save_dir_input.text().strip() or default_download_folder()
        os.makedirs(save_dir, exist_ok=True)

        title = info.get("title") or info.get("id") or "video"
        uploader = get_uploader(info) or ""
        vid_id = info.get("id") or ""

        base_filename = clean_title(title)
        if self.checkbox_channel.isChecked() and uploader:
            base_filename += "_" + clean_title(uploader)
        if self.checkbox_timestamp.isChecked():
            base_filename += "_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        tmp_opts = {
            "skip_download": True,
            "noplaylist": True,
        }
        cf = self._get_cookies_path()
        if cf:
            tmp_opts["cookiefile"] = cf
        with YoutubeDL(tmp_opts) as ydl_tmp:
            predicted = ydl_tmp.prepare_filename(info)
        _, pred_name = os.path.split(predicted)
        _, pred_ext = os.path.splitext(pred_name)
        ext = pred_ext.lstrip(".") or "mp4"

        final_path = make_unique_filepath(save_dir, base_filename, ext, fallback_id=vid_id)
        final_base = os.path.splitext(os.path.basename(final_path))[0]
        final_outtmpl = os.path.join(save_dir, final_base + ".%(ext)s")

        output_type = self.output_combo.currentData() or "MP4"
        choice = self.resolution_combo.currentText()
        convert = output_type == "MP4" and resolution_to_convert(choice)
        target_resolution = int(choice) if convert else 0

        if not self.cookies_input.text().strip():
            auto_cookie = get_cookie_path(url)
            if auto_cookie:
                self.log(f"Auto-detected cookies: {auto_cookie}")

        # The button doubles as Cancel while a download runs.
        self.download_btn.setText("Cancel")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.panel_labels["body"].setText("")
        self.panel_labels["ready"].setVisible(False)
        self.open_folder_btn.setVisible(False)
        self.progress_label.setText("")
        self._last_percent = -1
        self.log(f"Downloading as: {final_base} (H.264/AAC MP4).")
        self.worker = DownloadWorker(
            url, final_outtmpl, convert, target_resolution, output_type,
            cookies_file=self._get_cookies_path(), clip=clip,
            subtitles=self.subtitle_combo.currentData(),
            cookies_from_browser=self.settings.value("cookies/browser", "") or "",
        )
        self.worker.status_signal.connect(self.log)
        self.worker.progress_signal.connect(self._on_progress)
        self.worker.path_signal.connect(self._on_worker_path)
        self.worker.result_signal.connect(self._on_worker_result)
        self.worker.finished_signal.connect(self.on_worker_finished)
        self.worker.start()

    def _on_worker_path(self, path):
        self._last_path = path or ""

    def _on_progress(self, p):
        from core.progress import format_progress
        self.progress_bar.setValue(int(p.percent))
        text = format_progress(p)
        whole = int(p.percent)
        if whole != self._last_percent:
            # Announce once per whole percent, so a screen reader is not
            # flooded by every speed/tick update.
            self._last_percent = whole
            self._announce(self.progress_label, text)
        else:
            self.progress_label.setText(text)

    def _show_result(self, result):
        from core.progress import format_bytes
        from ui.style import token
        body = self.panel_labels["body"]
        ready = self.panel_labels["ready"]
        ok = getattr(result, "status", "") == "ok" and result.path
        if ok:
            parts = [os.path.basename(result.path)]
            if result.extension:
                parts.append(result.extension.upper())
            if result.height:
                parts.append("%dp" % result.height)
            if result.bytes:
                parts.append(format_bytes(result.bytes))
            self._announce(body, "  ·  ".join(parts))
            body.setStyleSheet("")
            ready.setText("Ready for CapCut, Premiere Pro, and DaVinci Resolve.")
            ready.setStyleSheet("color: %s;" % token("accent"))
            ready.setVisible(True)
            self.open_folder_btn.setVisible(True)
        else:
            self._announce(body, result.message or "The download did not finish.")
            category = getattr(result, "error_category", "")
            cancelled = category == "cancelled"
            body.setStyleSheet(
                "color: %s;" % token("text_muted" if cancelled else "error")
            )
            if cancelled:
                ready.setVisible(False)
            else:
                hint = result.message or "The download did not finish."
                if category == "blocked":
                    extra = get_cookie_message(
                        detect_platform(self._current_url) if self._current_url else ""
                    )
                    if extra:
                        hint = "%s %s" % (hint, extra)
                ready.setText(hint)
                ready.setStyleSheet("color: %s;" % token("text_muted"))
                ready.setVisible(True)
            self.open_folder_btn.setVisible(False)

    def _on_worker_result(self, result):
        self._show_result(result)

    def on_worker_finished(self, msg: str):
        self.log(msg)
        self.download_btn.setText("Download")
        self.download_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setText("")
        if not self._last_path:
            self.panel_labels["body"].setText(msg or "The download did not finish.")
            self.panel_labels["ready"].setVisible(False)

    def refresh_state_colors(self):
        """Re-color the result panel after a theme change."""
        ready = self.panel_labels["ready"]
        if not ready.text():
            return
        from ui.style import token
        ready.setStyleSheet("color: %s;" % token("accent"))
