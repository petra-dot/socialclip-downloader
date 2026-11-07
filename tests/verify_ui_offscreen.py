"""Offscreen UI checks. Not collected by pytest (name is not test_*)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SOCIALCLIP_DATA", os.path.join(
    os.environ.get("TEMP", "/tmp"), "socialclip-ui-verify"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5 import QtWidgets, QtCore  # noqa: E402


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setOrganizationName("petra-dot")
    app.setApplicationName("petra-dot-test")

    from ui.single_tab import SingleTab
    from ui.batch_tab import QueueTab
    from ui.convert_tab import ConvertTab
    from ui.history_tab import HistoryTab

    single = SingleTab({"path": ""})
    single.output_combo.setCurrentIndex(1)
    assert not single.resolution_combo.isEnabled(), "audio must not offer a resolution"
    single.output_combo.setCurrentIndex(0)
    assert single.resolution_combo.isEnabled(), "video must offer a resolution"
    # `isHidden()` is the explicit-hide state; `isVisible()` is always False
    # here because the widget is never shown offscreen.
    assert not single.console_log.isHidden(), "the activity log starts shown"
    single.details_toggle.setChecked(False)
    assert single.console_log.isHidden(), "the toggle minimizes the log"
    single.details_toggle.setChecked(True)

    queue = QueueTab({"path": ""})
    assert queue.batch_table.selectionMode() == \
        QtWidgets.QAbstractItemView.ExtendedSelection
    assert queue._bulk_bar.isHidden()

    convert = ConvertTab()
    assert convert.table.rowCount() == 0, "the list starts empty"
    assert convert.table.selectionMode() == \
        QtWidgets.QAbstractItemView.ExtendedSelection
    assert convert.bulk_bar.isHidden()
    assert convert.start_btn.text() == "Convert"
    assert convert.console_log.isHidden() is False

    HistoryTab()

    from ui.ipc import IpcServer, send_to_primary

    ipc = IpcServer()
    assert ipc.listen(), "the first instance takes the socket name"
    assert send_to_primary({"action": "show"}, timeout_ms=1000), \
        "a second launch reaches the running instance"
    ipc.close()
    assert not send_to_primary({"action": "show"}, timeout_ms=200), \
        "nothing answers once the instance closes"

    print("offscreen UI: ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
