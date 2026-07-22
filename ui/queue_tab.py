from PyQt5 import QtWidgets, QtCore

from dlqueue.manager import QueueManager
from dlqueue.models import DownloadStatus


class QueueTab(QtWidgets.QWidget):
    def __init__(self, cookies_file_ref):
        super().__init__()
        self.cookies_file_ref = cookies_file_ref
        self.manager = QueueManager()
        self._item_widgets = {}
        self.init_ui()
        self._connect_signals()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QtWidgets.QHBoxLayout()
        queue_heading = QtWidgets.QLabel("Queue")
        queue_heading.setStyleSheet("font-weight: bold; font-size: 12px;")
        header.addWidget(queue_heading)
        header.addStretch()
        self.queue_count_label = QtWidgets.QLabel("0 items")
        header.addWidget(self.queue_count_label)
        layout.addLayout(header)

        self.queue_scroll = QtWidgets.QScrollArea()
        self.queue_scroll.setWidgetResizable(True)
        self.queue_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.queue_list = QtWidgets.QWidget()
        self.queue_list.setLayout(QtWidgets.QVBoxLayout())
        self.queue_list.layout().setAlignment(QtCore.Qt.AlignTop)
        self.queue_list.layout().setSpacing(4)
        self.queue_scroll.setWidget(self.queue_list)
        layout.addWidget(self.queue_scroll, 1)

        ctrl_row = QtWidgets.QHBoxLayout()
        self.pause_btn = QtWidgets.QPushButton("Pause Queue")
        self.pause_btn.clicked.connect(self._toggle_pause)
        ctrl_row.addWidget(self.pause_btn)
        self.clear_btn = QtWidgets.QPushButton("Clear Finished")
        self.clear_btn.clicked.connect(self._clear_finished)
        ctrl_row.addWidget(self.clear_btn)
        self.retry_all_btn = QtWidgets.QPushButton("Retry All Failed")
        self.retry_all_btn.clicked.connect(self._retry_all)
        ctrl_row.addWidget(self.retry_all_btn)
        layout.addLayout(ctrl_row)

        sched_heading = QtWidgets.QLabel("Schedule & Limits")
        sched_heading.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(sched_heading)

        max_row = QtWidgets.QHBoxLayout()
        max_lbl = QtWidgets.QLabel("Max concurrent downloads:")
        max_row.addWidget(max_lbl)
        self.max_concurrent_spin = QtWidgets.QSpinBox()
        self.max_concurrent_spin.setRange(1, 10)
        self.max_concurrent_spin.setValue(2)
        self.max_concurrent_spin.valueChanged.connect(self.manager.set_max_concurrent)
        max_row.addWidget(self.max_concurrent_spin)
        max_row.addStretch()
        layout.addLayout(max_row)

        self.throttle_check = QtWidgets.QCheckBox("Throttle downloads by time window")
        layout.addWidget(self.throttle_check)

        time_row = QtWidgets.QHBoxLayout()
        time_row.setContentsMargins(24, 0, 0, 0)
        time_row.addWidget(QtWidgets.QLabel("Only download from"))
        self.throttle_start = QtWidgets.QTimeEdit(QtCore.QTime(22, 0))
        time_row.addWidget(self.throttle_start)
        time_row.addWidget(QtWidgets.QLabel("to"))
        self.throttle_end = QtWidgets.QTimeEdit(QtCore.QTime(8, 0))
        time_row.addWidget(self.throttle_end)
        time_row.addStretch()
        layout.addLayout(time_row)

        self.console_log = QtWidgets.QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setFixedHeight(120)
        layout.addWidget(self.console_log)

    def _connect_signals(self):
        self.manager.item_added.connect(self._on_item_added)
        self.manager.status_changed.connect(self._on_status_changed)
        self.manager.progress.connect(self._on_progress)

    def log(self, msg: str):
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.console_log.append(f"[{ts}] {msg}")
        sb = self.console_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def add_url(self, url: str, options: dict = None) -> str:
        item_id = self.manager.enqueue(url, options)
        self.log(f"Queued: {url}")
        return item_id

    def _on_item_added(self, item_id: str):
        item = next((i for i in self.manager.items if i.id == item_id), None)
        if not item:
            return

        card = QtWidgets.QFrame()
        card.setFrameShape(QtWidgets.QFrame.StyledPanel)
        card_layout = QtWidgets.QHBoxLayout(card)
        card_layout.setContentsMargins(8, 4, 8, 4)

        status_label = QtWidgets.QLabel("\u25CB")
        status_label.setFixedWidth(20)
        card_layout.addWidget(status_label)

        info_layout = QtWidgets.QVBoxLayout()
        url_label = QtWidgets.QLabel(item.url[:60] + ("..." if len(item.url) > 60 else ""))
        info_layout.addWidget(url_label)
        status_text = QtWidgets.QLabel("Queued")
        info_layout.addWidget(status_text)
        card_layout.addLayout(info_layout, 1)

        progress_bar = QtWidgets.QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setFixedWidth(120)
        progress_bar.setFixedHeight(18)
        progress_bar.setVisible(False)
        card_layout.addWidget(progress_bar)

        btn_layout = QtWidgets.QVBoxLayout()
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(lambda checked, iid=item_id: self.manager.cancel(iid))
        btn_layout.addWidget(cancel_btn)

        retry_btn = QtWidgets.QPushButton("Retry")
        retry_btn.setFixedWidth(80)
        retry_btn.setVisible(False)
        retry_btn.clicked.connect(lambda checked, iid=item_id: self.manager.retry(iid))
        btn_layout.addWidget(retry_btn)

        card_layout.addLayout(btn_layout)

        self._item_widgets[item_id] = {
            "card": card,
            "status_label": status_label,
            "status_text": status_text,
            "progress_bar": progress_bar,
            "cancel_btn": cancel_btn,
            "retry_btn": retry_btn,
        }
        self.queue_list.layout().addWidget(card)
        self._update_count()

    def _on_status_changed(self, item_id: str, status: str):
        w = self._item_widgets.get(item_id)
        if not w:
            return
        if status == "downloading":
            w["status_label"].setText("\u25B6")
            w["status_text"].setText("Downloading...")
            w["progress_bar"].setVisible(True)
        elif status == "completed":
            w["status_label"].setText("\u2713")
            w["status_text"].setText("Completed")
            w["progress_bar"].setVisible(False)
            w["cancel_btn"].setVisible(False)
        elif status == "failed":
            w["status_label"].setText("\u2717")
            w["status_text"].setText("Failed")
            w["progress_bar"].setVisible(False)
            w["cancel_btn"].setVisible(False)
            w["retry_btn"].setVisible(True)
        elif status == "cancelled":
            w["status_label"].setText("\u2014")
            w["status_text"].setText("Cancelled")
            w["progress_bar"].setVisible(False)
            w["cancel_btn"].setVisible(False)
        elif status == "queued":
            w["status_label"].setText("\u25CB")
            w["status_text"].setText("Queued")
            w["progress_bar"].setVisible(False)

    def _on_progress(self, item_id: str, pct: int):
        w = self._item_widgets.get(item_id)
        if w:
            w["progress_bar"].setValue(pct)

    def _toggle_pause(self):
        if self.manager._paused:
            self.manager.resume()
            self.pause_btn.setText("Pause Queue")
            self.log("Queue resumed")
        else:
            self.manager.pause()
            self.pause_btn.setText("Resume Queue")
            self.log("Queue paused")

    def _clear_finished(self):
        self.manager.clear_finished()
        for item_id in list(self._item_widgets.keys()):
            item = next((i for i in self.manager.items if i.id == item_id), None)
            if item is None:
                w = self._item_widgets.pop(item_id, None)
                if w:
                    w["card"].deleteLater()
        self._update_count()

    def _retry_all(self):
        for item in self.manager.items:
            if item.status == DownloadStatus.FAILED:
                self.manager.retry(item.id)
        self.log("Retrying all failed items")

    def _update_count(self):
        self.queue_count_label.setText(f"{len(self.manager.items)} items")
