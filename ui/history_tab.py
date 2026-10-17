"""History tab: every completed download, checked against the disk.

One tab for three jobs: find a file to play, read a complete record, and
reclaim disk space. The summary bar carries the totals and the actions, the
table carries the scannable rows, and the detail pane carries the full record
of the selected row (replacing the old Details dialog).
"""

import os

from PyQt5 import QtCore, QtGui, QtWidgets

from core.history import (
    HistoryStore, STATUS_DELETED, STATUS_MISSING, STATUS_OK,
    filter_entries, format_date, platform_label, search, sort_entries, status_of,
)
from core.progress import format_bytes
from ui.platform_icons import icon_for_url, platform_icon
from ui.style import danger_text_style, make_heading, state_color
from utils.ui_helpers import open_file, reveal_in_folder
from workers.probe_worker import ProbeWorker

_COLUMNS = ("Title", "Platform", "Format", "Size", "Date", "Status")
_SORT_FOR_COLUMN = ("title", "platform", "extension", "bytes", "created_at",
                    "status")
_STATUS_LABELS = {STATUS_OK: "OK", STATUS_MISSING: "Not found",
                  STATUS_DELETED: "Deleted by you"}
_STATUS_TONES = {STATUS_OK: "ok", STATUS_MISSING: "warn", STATUS_DELETED: "muted"}

_TITLE, _PLATFORM, _FORMAT, _SIZE, _DATE, _STATUS = range(6)
_FORMAT_WIDTH = 72
_STATUS_WIDTH = 132
_ICON_SIZE = 18
_ROW_HEIGHT = 34

_DETAIL_FIELDS = ("Title", "URL", "Path", "Platform", "Format", "Resolution",
                  "Duration", "Size", "Downloaded", "Source", "Status",
                  "Container", "Video codec", "Audio codec")
_CODEC_FIELDS = ("Container", "Video codec", "Audio codec")


def _chip(text, color=None):
    """A rounded pill label, centered in a cell container.

    The container holds the pill at its content width instead of letting the
    border stretch across the whole column. `color` also tints the text; with
    no color the chip is a neutral tag that inherits the theme text.
    """
    label = QtWidgets.QLabel(text)
    border = color or state_color("muted")
    css = "border: 1px solid %s; border-radius: 8px; padding: 1px 8px;" % border
    if color:
        css += " color: %s; font-weight: 600;" % color
    label.setStyleSheet(css)
    label.setAlignment(QtCore.Qt.AlignCenter)
    holder = QtWidgets.QWidget()
    row = QtWidgets.QHBoxLayout(holder)
    row.setContentsMargins(4, 0, 4, 0)
    row.addStretch(1)
    row.addWidget(label)
    row.addStretch(1)
    holder.label = label
    return holder


class HistoryTab(QtWidgets.QWidget):
    """Every completed download, with a status checked against the disk."""

    def __init__(self, store=None, parent=None):
        super().__init__(parent)
        self.store = store if store is not None else HistoryStore()
        self._entries = []
        self._statuses = {}
        self._probe_cache = {}
        self._probe_tasks = {}
        self._probe_pool = QtCore.QThreadPool.globalInstance()
        self._sort_key = "created_at"
        self._sort_desc = True
        self._build()
        self.refresh()

    # -- construction ------------------------------------------------------
    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        layout.addLayout(self._build_summary_bar())
        layout.addLayout(self._build_filters())
        layout.addWidget(self._build_table(), 1)
        layout.addWidget(self._build_detail_pane())

    def _build_summary_bar(self):
        bar = QtWidgets.QHBoxLayout()
        self.summary_label = QtWidgets.QLabel("")
        self.summary_label.setAccessibleName("History summary")
        make_heading(self.summary_label)
        bar.addWidget(self.summary_label)
        bar.addStretch(1)

        self.play_btn = QtWidgets.QPushButton("Play")
        self.play_btn.setAccessibleName("Play the selected download")
        self.play_btn.clicked.connect(self.play)
        self.folder_btn = QtWidgets.QPushButton("Open folder")
        self.folder_btn.setAccessibleName("Reveal the selected download in its folder")
        self.folder_btn.clicked.connect(self.open_folder)
        bar.addWidget(self.play_btn)
        bar.addWidget(self.folder_btn)

        # The destructive pair is separated from the primaries and carries the
        # error colour, so it never reads as a default button.
        bar.addSpacing(16)
        self.delete_btn = QtWidgets.QPushButton("Delete file")
        self.delete_btn.setAccessibleName("Delete the selected file from disk")
        self.delete_btn.clicked.connect(self.delete_file)
        self.forget_btn = QtWidgets.QPushButton("Remove from history")
        self.forget_btn.setAccessibleName("Remove the selected entry from history")
        self.forget_btn.clicked.connect(self.remove_entries)
        for button in (self.delete_btn, self.forget_btn):
            bar.addWidget(button)
        self._style_action_buttons()

        self.clear_action = QtWidgets.QAction("Clear history", self)
        self.clear_action.triggered.connect(self.clear_history)
        overflow = QtWidgets.QToolButton()
        overflow.setText("More")
        overflow.setAccessibleName("More history actions")
        overflow.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        menu = QtWidgets.QMenu(overflow)
        menu.addAction(self.clear_action)
        overflow.setMenu(menu)
        bar.addWidget(overflow)
        return bar

    def _style_action_buttons(self):
        """Mark the destructive pair red; re-applied so a theme change lands."""
        style = danger_text_style()
        self.delete_btn.setStyleSheet(style)
        self.forget_btn.setStyleSheet(style)

    def _build_filters(self):
        bar = QtWidgets.QHBoxLayout()
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Search title...")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setAccessibleName("Search history by title")
        self.search_box.textChanged.connect(self.refresh)
        self.platform_box = QtWidgets.QComboBox()
        self.platform_box.setAccessibleName("Filter history by platform")
        self.platform_box.currentIndexChanged.connect(self.refresh)
        self.format_box = QtWidgets.QComboBox()
        self.format_box.setAccessibleName("Filter history by format")
        self.format_box.addItems(["All formats", "MP4", "MP3"])
        self.format_box.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.search_box, 1)
        bar.addWidget(self.platform_box)
        bar.addWidget(self.format_box)
        return bar

    def _build_table(self):
        self.table = QtWidgets.QTableWidget(0, len(_COLUMNS))
        self.table.setAccessibleName("Download history")
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setTextElideMode(QtCore.Qt.ElideRight)
        self.table.setIconSize(QtCore.QSize(_ICON_SIZE, _ICON_SIZE))
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(_ROW_HEIGHT)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_menu)

        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(_TITLE, QtWidgets.QHeaderView.Stretch)
        for column in (_PLATFORM, _SIZE, _DATE):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(_FORMAT, QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(_STATUS, QtWidgets.QHeaderView.Fixed)
        self.table.setColumnWidth(_FORMAT, _FORMAT_WIDTH)
        self.table.setColumnWidth(_STATUS, _STATUS_WIDTH)
        header.sectionClicked.connect(self._on_header)

        # Guidance drawn over the table while it has nothing to show.
        self._empty = QtWidgets.QWidget(self.table.viewport())
        empty_layout = QtWidgets.QVBoxLayout(self._empty)
        empty_layout.addStretch(1)
        self._empty_label = QtWidgets.QLabel("")
        self._empty_label.setAlignment(QtCore.Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet("color: %s;" % state_color("muted"))
        empty_layout.addWidget(self._empty_label)
        self._clear_filters_btn = QtWidgets.QPushButton("Clear filters")
        self._clear_filters_btn.clicked.connect(self.clear_filters)
        empty_layout.addWidget(self._clear_filters_btn,
                               alignment=QtCore.Qt.AlignCenter)
        empty_layout.addStretch(1)
        self._empty.setVisible(False)
        self.table.viewport().installEventFilter(self)
        return self.table

    def _build_detail_pane(self):
        frame = QtWidgets.QFrame()
        frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        frame.setBackgroundRole(QtGui.QPalette.AlternateBase)
        frame.setAutoFillBackground(True)
        outer = QtWidgets.QVBoxLayout(frame)
        outer.setContentsMargins(12, 8, 12, 8)

        self._detail_placeholder = QtWidgets.QLabel(
            "Select a download to see its full record."
        )
        self._detail_placeholder.setStyleSheet("color: %s;" % state_color("muted"))
        outer.addWidget(self._detail_placeholder)

        self._detail_grid = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(self._detail_grid)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(3)
        grid.setColumnStretch(1, 1)
        self._detail_values = {}
        for row, name in enumerate(_DETAIL_FIELDS):
            key = QtWidgets.QLabel(name + ":")
            key.setStyleSheet("color: %s;" % state_color("muted"))
            key.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignTop)
            value = QtWidgets.QLabel("-")
            value.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            value.setWordWrap(True)
            grid.addWidget(key, row, 0)
            grid.addWidget(value, row, 1)
            self._detail_values[name] = (key, value)
        self._detail_grid.setVisible(False)
        outer.addWidget(self._detail_grid)
        return frame

    # -- data --------------------------------------------------------------
    def refresh(self):
        """Reload from disk and re-derive every status."""
        self._style_action_buttons()
        self.store.load()
        entries = self.store.entries()
        self._statuses = {e.id: status_of(e) for e in entries}

        platforms = sorted({e.platform for e in entries if e.platform})
        self._sync_platform_combo(platforms)

        entries = search(entries, self.search_box.text())
        fmt = self.format_box.currentText()
        entries = filter_entries(
            entries,
            platform=self.platform_box.currentData(),
            extension=None if fmt == "All formats" else fmt,
        )
        self._entries = sort_entries(entries, self._sort_key, self._sort_desc,
                                     self._statuses)
        self._fill_table()
        self._sync_buttons()
        self._show_details(self._current_entry())
        self._update_empty_state()

    def _sync_platform_combo(self, keys):
        """Show display names, keep the raw key as each item's data."""
        items = [("All platforms", None)]
        items += [(platform_label(key), key) for key in keys]
        current = self.platform_box.currentData()
        if [self.platform_box.itemData(i)
                for i in range(self.platform_box.count())] == [d for _, d in items]:
            return
        self.platform_box.blockSignals(True)
        self.platform_box.clear()
        for label, data in items:
            self.platform_box.addItem(label, data)
        index = self.platform_box.findData(current) if current else 0
        self.platform_box.setCurrentIndex(index if index >= 0 else 0)
        self.platform_box.blockSignals(False)

    def _fill_table(self):
        self.table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            status = self._statuses.get(entry.id, "")
            icon = (icon_for_url(entry.url, _ICON_SIZE) if entry.url
                    else platform_icon(entry.platform, _ICON_SIZE))
            self._set_row(row, entry, status, icon)
        self.table.clearSelection()

    def _set_row(self, row, entry, status, icon):
        muted = status != STATUS_OK
        title = entry.title or "(untitled)"
        title_item = QtWidgets.QTableWidgetItem(title)
        title_item.setIcon(icon)
        title_item.setToolTip(title)
        self._put(row, _TITLE, title_item, entry, muted)

        platform_item = QtWidgets.QTableWidgetItem(
            platform_label(entry.platform) or "-"
        )
        self._put(row, _PLATFORM, platform_item, entry, muted)

        size_item = QtWidgets.QTableWidgetItem(
            format_bytes(entry.bytes) if entry.bytes else "-"
        )
        size_item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self._put(row, _SIZE, size_item, entry, muted)

        date_item = QtWidgets.QTableWidgetItem(format_date(entry.created_at))
        self._put(row, _DATE, date_item, entry, muted)

        self.table.setCellWidget(
            row, _FORMAT, _chip((entry.extension or "-").upper())
        )
        self.table.setCellWidget(
            row, _STATUS, _chip(_STATUS_LABELS.get(status, status),
                                state_color(_STATUS_TONES.get(status, "muted")))
        )

    def _put(self, row, column, item, entry, muted):
        """A text cell carrying the row's entry id and the muted brush."""
        item.setData(QtCore.Qt.UserRole, entry.id)
        if muted:
            item.setForeground(QtGui.QBrush(QtGui.QColor(state_color("muted"))))
        self.table.setItem(row, column, item)

    # -- selection ---------------------------------------------------------
    def _selected_entries(self):
        rows = sorted({index.row()
                       for index in self.table.selectionModel().selectedRows()})
        by_id = {entry.id: entry for entry in self._entries}
        out = []
        for row in rows:
            item = self.table.item(row, _TITLE)
            if item is not None and item.data(QtCore.Qt.UserRole) in by_id:
                out.append(by_id[item.data(QtCore.Qt.UserRole)])
        return out

    def _current_entry(self):
        entries = self._selected_entries()
        return entries[0] if entries else None

    def _on_selection_changed(self):
        self._sync_buttons()
        self._show_details(self._current_entry())

    def _sync_buttons(self):
        selection = self._selected_entries()
        ok_selected = [e for e in selection
                       if self._statuses.get(e.id) == STATUS_OK]
        single_ok = len(selection) == 1 and len(ok_selected) == 1
        self.play_btn.setEnabled(single_ok)
        self.folder_btn.setEnabled(single_ok)
        self.delete_btn.setEnabled(bool(ok_selected))
        self.forget_btn.setEnabled(bool(selection))
        self.clear_action.setEnabled(bool(self.store.entries()))
        self.summary_label.setText(self._summary_text())

    def _summary_text(self):
        entries = self._entries
        total = sum(e.bytes or 0 for e in entries)
        missing = sum(1 for e in entries
                      if self._statuses.get(e.id) == STATUS_MISSING)
        parts = ["%d download%s" % (len(entries), "" if len(entries) == 1 else "s")]
        if total:
            parts.append(format_bytes(total))
        if missing:
            parts.append("%d not found" % missing)
        text = "  ·  ".join(parts)
        selection = self._selected_entries()
        if len(selection) > 1:
            chosen = sum(e.bytes or 0 for e in selection)
            text += "    |    %d selected · %s" % (len(selection),
                                                   format_bytes(chosen))
        return text

    def _on_header(self, index):
        key = _SORT_FOR_COLUMN[index]
        if key == self._sort_key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key, self._sort_desc = key, False
        self.refresh()

    # -- detail pane -------------------------------------------------------
    def _start_probe(self, path):
        """Probe `path` on the thread pool; one in flight per path."""
        if not path or path in self._probe_tasks:
            return
        task = ProbeWorker(path)
        task.signals.done.connect(self._on_probed)
        self._probe_tasks[path] = task
        self._probe_pool.start(task)

    def _on_probed(self, path, info):
        self._probe_tasks.pop(path, None)
        self._probe_cache[path] = info or {}
        entry = self._current_entry()
        if entry is not None and entry.path == path:
            self._show_details(entry)

    def _show_details(self, entry):
        if entry is None:
            self._detail_placeholder.setVisible(True)
            self._detail_grid.setVisible(False)
            return
        status = self._statuses.get(entry.id, "")
        fields = {
            "Title": entry.title or "(untitled)",
            "URL": entry.url or "-",
            "Path": entry.path or "-",
            "Platform": platform_label(entry.platform) or "-",
            "Format": (entry.extension or "-").upper(),
            "Resolution": "%dp" % entry.height if entry.height else "-",
            "Duration": _duration(entry.duration_seconds),
            "Size": format_bytes(entry.bytes) if entry.bytes else "-",
            "Downloaded": entry.created_at or "-",
            "Source": entry.source or "-",
            "Status": _STATUS_LABELS.get(status, status) or "-",
        }
        probe = status == STATUS_OK
        if probe:
            probed = self._probe_cache.get(entry.path)
            if probed is None:
                # ffprobe is a subprocess with a cold-start cost, so probe it
                # off the UI thread and fill the codecs in when it answers.
                for name in _CODEC_FIELDS:
                    fields[name] = "…"
                self._start_probe(entry.path)
            else:
                fields["Container"] = probed.get("container") or "-"
                fields["Video codec"] = probed.get("vcodec") or "-"
                fields["Audio codec"] = probed.get("acodec") or "-"
        for name, (key, value) in self._detail_values.items():
            if name in _CODEC_FIELDS:
                key.setVisible(probe)
                value.setVisible(probe)
            value.setText(fields.get(name, "-"))
        self._detail_placeholder.setVisible(False)
        self._detail_grid.setVisible(True)

    # -- empty state -------------------------------------------------------
    def _update_empty_state(self):
        if self._entries:
            self._empty.setVisible(False)
            return
        self._empty.setGeometry(self.table.viewport().rect())
        if self.store.entries():
            self._empty_label.setText("No downloads match")
            self._clear_filters_btn.setVisible(True)
        else:
            self._empty_label.setText(
                "No downloads yet.\n\n"
                "Every finished download appears here with its size, format, "
                "and whether the file is still on disk."
            )
            self._clear_filters_btn.setVisible(False)
        self._empty.setVisible(True)
        self._empty.raise_()

    def clear_filters(self):
        self.search_box.clear()
        self.platform_box.setCurrentIndex(0)
        self.format_box.setCurrentIndex(0)
        self.refresh()

    def eventFilter(self, obj, event):
        if obj is self.table.viewport() and event.type() == QtCore.QEvent.Resize:
            self._empty.setGeometry(self.table.viewport().rect())
        return super().eventFilter(obj, event)

    # -- actions -----------------------------------------------------------
    def play(self):
        entry = self._current_entry()
        if entry and not open_file(entry.path):
            QtWidgets.QMessageBox.warning(
                self, "Cannot play",
                "No application is set to open this file type.",
            )

    def open_folder(self):
        entry = self._current_entry()
        if entry:
            reveal_in_folder(entry.path)

    def delete_file(self):
        """Delete every selected, still-present file. Confirms once."""
        entries = [e for e in self._selected_entries()
                   if self._statuses.get(e.id) == STATUS_OK]
        if not entries:
            return
        if len(entries) == 1:
            detail = os.path.basename(entries[0].path)
        else:
            total = sum(e.bytes or 0 for e in entries)
            detail = "%d files (%s)" % (len(entries), format_bytes(total))
        answer = QtWidgets.QMessageBox.question(
            self, "Delete file",
            "Delete %s from disk?\n\nThe history entries are kept." % detail,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        failed = []
        for entry in entries:
            try:
                os.remove(entry.path)
            except OSError as exc:
                failed.append("%s: %s" % (os.path.basename(entry.path), exc))
                continue
            self.store.mark_deleted(entry.id)
        if failed:
            QtWidgets.QMessageBox.warning(
                self, "Some files were not deleted", "\n".join(failed)
            )
        self.refresh()

    def remove_entries(self):
        """Drop the selected entries from history. Never touches a file."""
        entries = self._selected_entries()
        if not entries:
            return
        if len(entries) == 1:
            question = "Remove this entry from the history?"
        else:
            question = "Remove %d entries from the history?" % len(entries)
        answer = QtWidgets.QMessageBox.question(
            self, "Remove from history",
            "%s\n\nThe files are not deleted." % question,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        for entry in entries:
            self.store.remove(entry.id)
        self.refresh()

    def clear_history(self):
        if not self.store.entries():
            return
        answer = QtWidgets.QMessageBox.question(
            self, "Clear history",
            "Remove every entry from the history?\n\nNo files are deleted.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        for entry in self.store.entries():
            self.store.remove(entry.id)
        self.refresh()

    def _on_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        # Right-clicking an unselected row should act on that row, not on
        # whatever happened to be selected before.
        if index.row() not in {i.row()
                               for i in self.table.selectionModel().selectedRows()}:
            self.table.selectRow(index.row())
        entry = self._current_entry()
        if entry is None:
            return
        menu = QtWidgets.QMenu(self)
        for button in (self.play_btn, self.folder_btn, self.delete_btn,
                       self.forget_btn):
            action = menu.addAction(button.text())
            action.setEnabled(button.isEnabled())
            action.triggered.connect(button.click)
        menu.addSeparator()
        menu.addAction(self.clear_action)
        menu.exec_(self.table.viewport().mapToGlobal(pos))


def _duration(seconds: int) -> str:
    if not seconds:
        return "-"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%d:%02d" % (minutes, secs)
