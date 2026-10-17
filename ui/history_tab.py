import os

from PyQt5 import QtCore, QtGui, QtWidgets

from core.history import (
    HistoryStore, STATUS_OK, filter_entries, search, sort_entries, status_of,
)
from core.probe import probe_media
from core.progress import format_bytes
from utils.ui_helpers import open_file, reveal_in_folder

_COLUMNS = ("Title", "Platform", "Format", "Size", "Date", "Status")
_SORT_FOR_COLUMN = ("title", "platform", "extension", "bytes", "created_at",
                    "status")
_STATUS_LABELS = {"ok": "OK", "missing": "Not found", "deleted": "Deleted by you"}
_MUTED = "#8a8a8a"


class HistoryTab(QtWidgets.QWidget):
    """Every completed download, with a status checked against the disk."""

    def __init__(self, store=None, parent=None):
        super().__init__(parent)
        self.store = store if store is not None else HistoryStore()
        self._entries = []
        self._statuses = {}
        self._sort_key = "created_at"
        self._sort_desc = True
        self._build()
        self.refresh()

    # -- construction ------------------------------------------------------
    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)

        bar = QtWidgets.QHBoxLayout()
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Search title...")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self.refresh)
        self.platform_box = QtWidgets.QComboBox()
        self.platform_box.currentIndexChanged.connect(self.refresh)
        self.format_box = QtWidgets.QComboBox()
        self.format_box.addItems(["All formats", "MP4", "MP3"])
        self.format_box.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.search_box, 1)
        bar.addWidget(self.platform_box)
        bar.addWidget(self.format_box)
        layout.addLayout(bar)

        self.table = QtWidgets.QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header)
        self.table.itemSelectionChanged.connect(self._sync_buttons)
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_menu)
        layout.addWidget(self.table, 1)

        buttons = QtWidgets.QHBoxLayout()
        self.play_btn = QtWidgets.QPushButton("Play")
        self.play_btn.clicked.connect(self.play)
        self.folder_btn = QtWidgets.QPushButton("Open folder")
        self.folder_btn.clicked.connect(self.open_folder)
        self.details_btn = QtWidgets.QPushButton("Details")
        self.details_btn.clicked.connect(self.show_details)
        self.delete_btn = QtWidgets.QPushButton("Delete file")
        self.delete_btn.clicked.connect(self.delete_file)
        self.forget_btn = QtWidgets.QPushButton("Remove from history")
        self.forget_btn.clicked.connect(self.remove_entry)
        self.clear_btn = QtWidgets.QPushButton("Clear history")
        self.clear_btn.clicked.connect(self.clear_history)
        for button in (self.play_btn, self.folder_btn, self.details_btn):
            buttons.addWidget(button)
        buttons.addStretch(1)
        for button in (self.delete_btn, self.forget_btn, self.clear_btn):
            buttons.addWidget(button)
        layout.addLayout(buttons)

    # -- data --------------------------------------------------------------
    def refresh(self):
        """Reload from disk and re-derive every status."""
        self.store.load()
        entries = self.store.entries()
        self._statuses = {e.id: status_of(e) for e in entries}

        platforms = sorted({e.platform for e in entries if e.platform})
        self._sync_combo(self.platform_box, ["All platforms"] + platforms)

        entries = search(entries, self.search_box.text())
        fmt = self.format_box.currentText()
        entries = filter_entries(
            entries,
            platform=None if self.platform_box.currentIndex() <= 0
            else self.platform_box.currentText(),
            extension=None if fmt == "All formats" else fmt,
        )
        self._entries = sort_entries(entries, self._sort_key, self._sort_desc,
                                     self._statuses)
        self._fill_table()
        self._sync_buttons()

    def _sync_combo(self, combo, items):
        """Keep the selection while the option list changes."""
        if [combo.itemText(i) for i in range(combo.count())] == items:
            return
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(items)
        index = combo.findText(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _fill_table(self):
        self.table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            status = self._statuses.get(entry.id, "")
            cells = (
                entry.title or "(untitled)",
                entry.platform or "-",
                (entry.extension or "-").upper(),
                format_bytes(entry.bytes) if entry.bytes else "-",
                (entry.created_at or "")[:10],
                _STATUS_LABELS.get(status, status),
            )
            for col, text in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(text)
                item.setData(QtCore.Qt.UserRole, entry.id)
                if status != STATUS_OK:
                    item.setForeground(QtGui.QBrush(QtGui.QColor(_MUTED)))
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()

    # -- selection ---------------------------------------------------------
    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        entry_id = self.table.item(rows[0].row(), 0).data(QtCore.Qt.UserRole)
        for entry in self._entries:
            if entry.id == entry_id:
                return entry
        return None

    def _sync_buttons(self):
        entry = self._selected()
        usable = bool(entry) and self._statuses.get(entry.id) == STATUS_OK
        for button in (self.play_btn, self.folder_btn, self.delete_btn):
            button.setEnabled(usable)
        self.details_btn.setEnabled(bool(entry))
        self.forget_btn.setEnabled(bool(entry))
        self.clear_btn.setEnabled(bool(self._entries))

    def _on_header(self, index):
        key = _SORT_FOR_COLUMN[index]
        if key == self._sort_key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key, self._sort_desc = key, False
        self.refresh()

    # -- actions -----------------------------------------------------------
    def play(self):
        entry = self._selected()
        if entry and not open_file(entry.path):
            QtWidgets.QMessageBox.warning(
                self, "Cannot play",
                "No application is set to open this file type.",
            )

    def open_folder(self):
        entry = self._selected()
        if entry:
            reveal_in_folder(entry.path)

    def delete_file(self):
        entry = self._selected()
        if not entry or self._statuses.get(entry.id) != STATUS_OK:
            return
        name = os.path.basename(entry.path)
        answer = QtWidgets.QMessageBox.question(
            self, "Delete file",
            "Delete %s from disk?\n\nThe history entry is kept." % name,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            os.remove(entry.path)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Delete failed", str(exc))
            return
        self.store.mark_deleted(entry.id)
        self.refresh()

    def remove_entry(self):
        entry = self._selected()
        if not entry:
            return
        answer = QtWidgets.QMessageBox.question(
            self, "Remove from history",
            "Remove this entry from the history?\n\nThe file is not deleted.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        self.store.remove(entry.id)
        self.refresh()

    def clear_history(self):
        if not self._entries:
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

    def show_details(self):
        entry = self._selected()
        if not entry:
            return
        lines = [
            ("Title", entry.title or "(untitled)"),
            ("URL", entry.url or "-"),
            ("Platform", entry.platform or "-"),
            ("File", entry.path or "-"),
            ("Format", (entry.extension or "-").upper()),
            ("Resolution", "%dp" % entry.height if entry.height else "-"),
            ("Duration", _duration(entry.duration_seconds)),
            ("Size", format_bytes(entry.bytes) if entry.bytes else "-"),
            ("Downloaded", entry.created_at or "-"),
            ("Source", entry.source or "-"),
            ("Status", _STATUS_LABELS.get(self._statuses.get(entry.id, ""), "-")),
        ]
        if self._statuses.get(entry.id) == STATUS_OK:
            probed = probe_media(entry.path) or {}
            lines += [
                ("Container", probed.get("container") or "-"),
                ("Video codec", probed.get("vcodec") or "-"),
                ("Audio codec", probed.get("acodec") or "-"),
            ]
        text = "\n".join("%s: %s" % (name, value) for name, value in lines)
        QtWidgets.QMessageBox.information(self, "Download details", text)

    def _on_menu(self, pos):
        if self._selected() is None:
            return
        menu = QtWidgets.QMenu(self)
        for button in (self.play_btn, self.folder_btn, self.details_btn,
                       self.delete_btn, self.forget_btn):
            action = menu.addAction(button.text())
            action.setEnabled(button.isEnabled())
            action.triggered.connect(button.click)
        menu.exec_(self.table.viewport().mapToGlobal(pos))


def _duration(seconds: int) -> str:
    if not seconds:
        return "-"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%d:%02d" % (minutes, secs)
