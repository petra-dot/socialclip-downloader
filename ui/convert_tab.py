import datetime
import os

from PyQt5 import QtWidgets, QtCore

from core import formats
from utils.file_utils import default_download_folder, RESOLUTIONS
from utils.ui_helpers import reveal_in_folder
from workers.convert_queue_worker import ConvertQueueWorker
from ui.style import (
    make_heading,
    make_result_panel,
    space,
    token,
)


class ConvertTab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        # The tab owns the drop so an unaccepted drop from the table viewport
        # propagates up to dragEnterEvent/dropEvent below.
        self.setAcceptDrops(True)
        self.worker = None
        self._last_output = ""
        self.settings = QtCore.QSettings()
        self.init_ui()

    def init_ui(self):
        main = QtWidgets.QVBoxLayout()
        # No bottom margin: the activity log runs to the pane's bottom so its
        # edge lines up with the result panel's.
        main.setContentsMargins(space("md"), space("md"), space("md"), 0)
        main.setSpacing(space("sm"))

        from core.convert_queue import ConvertQueue, ConvertStore

        self.store = ConvertStore()
        self.store.load()
        self.queue = ConvertQueue(self.store)
        self.queue.jobs[:] = self.store.jobs

        heading = QtWidgets.QLabel("Convert")
        make_heading(heading)
        main.addWidget(heading)

        toolbar = QtWidgets.QHBoxLayout()
        self.add_files_btn = QtWidgets.QPushButton("Add files…")
        self.add_files_btn.clicked.connect(self.on_add_files)
        self.clear_finished_btn = QtWidgets.QPushButton("Clear finished")
        self.clear_finished_btn.clicked.connect(self.on_clear_finished)
        self.retry_failed_btn = QtWidgets.QPushButton("Retry failed")
        self.retry_failed_btn.clicked.connect(self.on_retry_failed)
        for button in (self.add_files_btn, self.clear_finished_btn,
                       self.retry_failed_btn):
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        main.addLayout(toolbar)

        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setAccessibleName("Conversion list")
        self.table.setHorizontalHeaderLabels(["File", "Status", "Detail"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_menu)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        # Bulk actions for a multi-selection, above the table as in the Queue.
        self.bulk_bar = QtWidgets.QWidget()
        bulk = QtWidgets.QHBoxLayout(self.bulk_bar)
        bulk.setContentsMargins(0, 0, 0, 0)
        self.bulk_label = QtWidgets.QLabel("")
        bulk.addWidget(self.bulk_label)
        bulk.addStretch(1)
        for text, slot in (("Retry", self.on_retry_selected),
                           ("Remove", self.on_remove_selected),
                           ("Clear finished", self.on_clear_finished)):
            button = QtWidgets.QPushButton(text)
            button.clicked.connect(slot)
            bulk.addWidget(button)
        self.bulk_bar.setVisible(False)
        main.addWidget(self.bulk_bar)
        main.addWidget(self.table, 1)

        main.addSpacing(space("lg"))
        conv_heading = QtWidgets.QLabel("Options for new items")
        make_heading(conv_heading)
        main.addWidget(conv_heading)
        conv_opts = QtWidgets.QHBoxLayout()
        self.conv_output_combo = QtWidgets.QComboBox()
        self.conv_output_combo.setAccessibleName("Convert to format")
        for fmt in formats.for_kind("video") + formats.for_kind("audio"):
            self.conv_output_combo.addItem(fmt.label, fmt.key)
        saved_output = self.settings.value("convert/output")
        idx = self.conv_output_combo.findData(saved_output)
        self.conv_output_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.conv_output_combo.currentIndexChanged.connect(self._on_conv_output_changed)
        conv_output_label = QtWidgets.QLabel("Output:")
        conv_output_label.setBuddy(self.conv_output_combo)
        conv_opts.addWidget(conv_output_label)
        conv_opts.addWidget(self.conv_output_combo)
        self.conv_res_combo = QtWidgets.QComboBox()
        self.conv_res_combo.setAccessibleName("Convert target resolution")
        self.conv_res_combo.addItems(RESOLUTIONS)
        saved_res = self.settings.value("convert/resolution")
        self.conv_res_combo.setCurrentText(saved_res if saved_res in RESOLUTIONS else "1080")
        self.conv_res_combo.currentTextChanged.connect(self._on_conv_res_changed)
        conv_res_label = QtWidgets.QLabel("Resolution:")
        conv_res_label.setBuddy(self.conv_res_combo)
        conv_opts.addWidget(conv_res_label)
        conv_opts.addWidget(self.conv_res_combo)
        self.copy_combo = QtWidgets.QComboBox()
        self.copy_combo.setAccessibleName("Stream handling")
        self.copy_combo.addItem("Auto", None)
        self.copy_combo.addItem("Copy streams", True)
        self.copy_combo.addItem("Re-encode", False)
        self.copy_combo.currentIndexChanged.connect(self._on_conv_copy_changed)
        streams_label = QtWidgets.QLabel("Streams:")
        streams_label.setBuddy(self.copy_combo)
        conv_opts.addWidget(streams_label)
        conv_opts.addWidget(self.copy_combo)
        conv_opts.addStretch(1)
        self._update_conv_controls()
        main.addLayout(conv_opts)

        # The action and the bulk apply sit on their own row. With three
        # label/combo pairs above, the options row has no width left for a long
        # button label, so Qt elides it to "Apply to all pendin".
        start_row = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Convert")
        self.start_btn.clicked.connect(self.on_start)
        start_row.addWidget(self.start_btn)
        self.apply_options_btn = QtWidgets.QPushButton("Apply to all pending")
        self.apply_options_btn.clicked.connect(self.on_apply_options)
        start_row.addWidget(self.apply_options_btn)
        start_row.addStretch(1)
        main.addLayout(start_row)

        # Inline hint for recoverable mistakes, instead of a modal popup.
        self.hint_label = QtWidgets.QLabel("")
        self.hint_label.setVisible(False)
        self.hint_label.setWordWrap(True)
        main.addWidget(self.hint_label)

        # The log is shown by default at a compact height; the toggle minimizes
        # it.
        main.addSpacing(space("lg"))
        self.details_toggle = QtWidgets.QToolButton()
        self.details_toggle.setText("Activity")
        self.details_toggle.setCheckable(True)
        self.details_toggle.setToolButtonStyle(
            QtCore.Qt.ToolButtonTextBesideIcon)
        self.details_toggle.setToolTip("Show or hide the activity log.")
        self.details_toggle.toggled.connect(self._on_details_toggled)
        main.addWidget(self.details_toggle)

        self._main_layout = main
        self.console_log = QtWidgets.QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setMinimumHeight(120)
        self.console_log.setAccessibleName("Conversion log")
        main.addWidget(self.console_log, 1)   # grows to the pane's bottom

        # The rows pack to the top. While the log is shown it takes the spare
        # height, so this spacer is slack; when the log is minimized the spacer
        # takes it, so the rows never spread.
        main.addStretch(1)
        self._bottom_stretch = main.count() - 1
        # Set the initial state directly rather than through the toggle's slot:
        # the slot re-stretches the layout, which forces a full relayout while
        # the tree is still being built.
        self._main_layout.setStretch(self._bottom_stretch, 0)
        self.details_toggle.blockSignals(True)
        self.details_toggle.setChecked(True)
        self.details_toggle.blockSignals(False)
        self.details_toggle.setArrowType(QtCore.Qt.DownArrow)
        self.details_toggle.setFixedWidth(self.details_toggle.sizeHint().width())

        # Two panes: the form on the left, the shared result panel on the right.
        form = QtWidgets.QWidget()
        form.setLayout(main)
        self.result_panel, self.panel_labels = make_result_panel()
        self.open_folder_btn = QtWidgets.QPushButton("Open folder")
        self.open_folder_btn.clicked.connect(self._on_open_folder)
        self.open_folder_btn.setVisible(False)
        box = self.panel_labels["layout"]
        box.insertWidget(box.count() - 1, self.open_folder_btn)

        panes = QtWidgets.QHBoxLayout()
        panes.setSpacing(space("lg"))
        panes.addWidget(form, 3)
        panes.addWidget(self.result_panel, 2)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(space("md"), space("md"), space("md"), space("md"))
        root.addLayout(panes)

        # Paint the empty state now; it otherwise only appears on a selection
        # change, leaving the panel body blank at startup.
        self._show_detail(None)

    def show_hint(self, text: str):
        self.hint_label.setText(text)
        self.hint_label.setVisible(bool(text))

    def log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.console_log.append(f"[{ts}] {msg}")
        sb = self.console_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_conv_output_changed(self, _index):
        key = self.conv_output_combo.currentData()
        if key:
            self.settings.setValue("convert/output", key)
        self._update_conv_controls()

    def _on_conv_copy_changed(self, _index):
        self._update_conv_controls()

    def _update_conv_controls(self):
        fmt = formats.get(self.conv_output_combo.currentData())
        is_audio = fmt is not None and fmt.kind == "audio"
        # GIF has a fixed recipe (hardcoded scale=320); the combo must not
        # advertise a resolution it silently ignores.
        is_gif = fmt is not None and fmt.key == "gif"
        force_copy = self.copy_combo.currentData() is True
        self.conv_res_combo.setEnabled(not (is_audio or is_gif or force_copy))

    def _on_conv_res_changed(self, text):
        self.settings.setValue("convert/resolution", text)

    def _on_open_folder(self):
        reveal_in_folder(self._last_output)

    def refresh_state_colors(self):
        """Re-color the result panel after a theme change."""
        ready = self.panel_labels["ready"]
        if not ready.text():
            return
        ready.setStyleSheet("color: %s;" % token("accent"))

    def _on_details_toggled(self, checked):
        """Show or hide the log; whichever is visible takes the spare height."""
        self.console_log.setVisible(checked)
        self._main_layout.setStretchFactor(self.console_log, 1 if checked else 0)
        self._main_layout.setStretch(self._bottom_stretch, 0 if checked else 1)
        self.details_toggle.setArrowType(
            QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
        )

    def on_add_files(self):
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select media files", default_download_folder(),
            "Media files (*.mp4 *.mov *.mkv *.avi *.webm *.mp3 *.m4a *.wav *.aac "
            "*.flac *.ogg *.opus *.gif);;All files (*)")
        if files:
            self._add_paths(files)

    def _new_item_options(self):
        """The options baked into a row when it is added."""
        fmt = self.conv_output_combo.currentData()
        target_res = (int(self.conv_res_combo.currentText())
                      if self.conv_res_combo.isEnabled() else 0)
        return {"target_format": fmt, "resolution": target_res,
                "copy_streams": self.copy_combo.currentData()}

    def on_apply_options(self):
        ids = [job.id for job in self.queue.jobs if job.state == "pending"]
        changed = self.queue.set_options(ids, self._new_item_options())
        if not changed:
            self.show_hint("No pending files to update.")
            return
        self._save()
        self.refresh_table()

    def on_start(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel_all()
            self.start_btn.setEnabled(False)
            self.start_btn.setText("Cancelling…")
            return
        if not self.queue.pending_count():
            self.show_hint("Add at least one file first.")
            return
        self.show_hint("")
        self.start_btn.setText("Cancel all")
        self.start_btn.setEnabled(True)
        self.worker = ConvertQueueWorker(self.queue, self.store)
        self.worker.job_signal.connect(self._on_job)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _on_job(self, payload):
        self.refresh_table()
        self._sync_buttons()

    def _on_finished(self, message):
        self.log(message)
        self.start_btn.setText("Convert")
        self.start_btn.setEnabled(True)
        self.refresh_table()

    def _add_paths(self, paths):
        kept = [p for p in paths if os.path.isfile(p)]
        added = self.queue.add(kept, self._new_item_options())
        if not added:
            self.show_hint("Those files are already in the list."
                           if kept else "No usable files were added.")
            return
        self.show_hint("")
        self._save()
        self.refresh_table()
        self._select_ids([job.id for job in added])

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        self._add_paths(paths)
        event.acceptProposedAction()

    def on_clear_finished(self):
        self.queue.clear_finished()
        self._save()
        self.refresh_table()

    def on_retry_failed(self):
        if not self.queue.retry_failed():
            self.show_hint("No failed files to retry.")
            return
        self._save()
        self.refresh_table()

    def _on_selection_changed(self):
        jobs = self._selected_jobs()
        self._sync_buttons()
        self._show_detail(jobs[0] if jobs else None)
        if len(jobs) < 2:
            self.bulk_bar.setVisible(False)
            return
        self.bulk_label.setText("%d selected" % len(jobs))
        self.bulk_bar.setVisible(True)

    def _show_detail(self, job):
        from ui.style import token
        body = self.panel_labels["body"]
        ready = self.panel_labels["ready"]
        if job is None:
            body.setText("Select a file to see its details.")
            ready.setVisible(False)
            self.open_folder_btn.setVisible(False)
            return
        lines = [os.path.basename(job.path), format_label(job.target_format)]
        if job.resolution:
            lines.append("%dp" % job.resolution)
        body.setText("  ·  ".join(lines) + "\n" + (job.output_path or "-"))
        ready.setText(job.message or state_label(job.state))
        ready.setStyleSheet("color: %s;" % (
            token("ok") if job.state == "done" else token("text_muted")))
        ready.setVisible(True)
        self._last_output = job.output_path
        self.open_folder_btn.setVisible(bool(job.output_path))

    def on_retry_selected(self):
        for job in self._selected_jobs():
            self.queue.retry_failed(job.id)
        self._save()
        self.refresh_table()

    def on_remove_selected(self):
        for job in self._selected_jobs():
            self.queue.remove(job.id)
        self._save()
        self.refresh_table()

    def _on_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        if index.row() not in {i.row()
                               for i in self.table.selectionModel().selectedRows()}:
            self.table.selectRow(index.row())
        menu = QtWidgets.QMenu(self)
        edit = menu.addAction("Edit options…")
        retry = menu.addAction("Retry")
        remove = menu.addAction("Remove")
        cancel = menu.addAction("Cancel")
        chosen = menu.exec_(self.table.viewport().mapToGlobal(pos))
        if chosen is edit:
            self._edit_selected_options()
        elif chosen is retry:
            self.on_retry_selected()
        elif chosen is remove:
            self.on_remove_selected()
        elif chosen is cancel:
            if self.worker and self.worker.isRunning():
                for job in self._selected_jobs():
                    self.worker.cancel(job.id)

    def _edit_selected_options(self):
        jobs = [job for job in self._selected_jobs() if job.state == "pending"]
        if not jobs:
            self.show_hint("Only pending files can be edited.")
            return
        changed = self.queue.set_options(
            [job.id for job in jobs], self._new_item_options())
        if not changed:
            self.show_hint("Nothing to update.")
            return
        self._save()
        self.refresh_table()
        self.show_hint("Updated %d file(s) from the options above." % changed)

    def _sync_buttons(self):
        from core.convert_queue import (
            STATUS_FAILED, STATUS_PENDING, TERMINAL_STATES)
        states = {job.state for job in self.queue.jobs}
        self.retry_failed_btn.setEnabled(STATUS_FAILED in states)
        self.clear_finished_btn.setEnabled(bool(states.intersection(TERMINAL_STATES)))
        self.apply_options_btn.setEnabled(STATUS_PENDING in states)

    def refresh_table(self):
        self.table.setRowCount(0)
        for job in self.queue.jobs:
            self._insert_row(job)

    def _insert_row(self, job):
        from ui.style import make_chip
        row = self.table.rowCount()
        self.table.insertRow(row)
        name = os.path.basename(job.path)
        name_item = QtWidgets.QTableWidgetItem(name)
        name_item.setToolTip(job.path)
        name_item.setData(QtCore.Qt.UserRole, job.id)
        self.table.setItem(row, 0, name_item)
        self.table.setCellWidget(row, 1, make_chip(
            state_label(job.state), state_kind(job.state)))
        self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(detail_for(job)))

    def _selected_jobs(self):
        ids = {self.table.item(index.row(), 0).data(QtCore.Qt.UserRole)
               for index in self.table.selectionModel().selectedRows()}
        return [job for job in self.queue.jobs if job.id in ids]

    def _select_ids(self, ids):
        wanted = set(ids)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(QtCore.Qt.UserRole) in wanted:
                item.setSelected(True)

    def _save(self):
        self.store.jobs = list(self.queue.jobs)
        self.store.save()


def state_label(state: str) -> str:
    return (state or "").capitalize()


def state_kind(state: str) -> str:
    return {"done": "ok", "failed": "error",
            "running": "busy"}.get(state, "muted")


def format_label(key: str) -> str:
    """Registry label for a format key, falling back to the upper-cased key."""
    fmt = formats.get(key)
    return fmt.label if fmt is not None else key.upper()


def detail_for(job) -> str:
    if job.state == "done" and job.output_path:
        return os.path.basename(job.output_path)
    if job.state == "failed":
        return job.message or "Failed."
    if job.state == "running":
        return job.message or "Converting…"
    label = format_label(job.target_format)
    parts = [label]
    if job.resolution:
        parts.append("%dp" % job.resolution)
    return "  ·  ".join(parts) + "  ·  queued"
