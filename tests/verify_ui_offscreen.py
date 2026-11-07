"""Offscreen UI checks. Not collected by pytest (name is not test_*)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SOCIALCLIP_DATA", os.path.join(
    os.environ.get("TEMP", "/tmp"), "socialclip-ui-verify"))
# A real app may be running and owning the default IPC name.
os.environ["SOCIALCLIP_IPC"] = "socialclip-ui-verify"

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

    clipboard = QtWidgets.QApplication.clipboard()
    single.url_input.clear()
    clipboard.setText("https://www.youtube.com/feed/subscriptions")
    single._fill_from_clipboard()
    assert single.url_input.text() == "", "a feed page must not prefill"
    clipboard.setText("https://www.youtube.com/@somechannel")
    single._fill_from_clipboard()
    assert single.url_input.text() == "", "a channel page must not prefill"
    clipboard.setText("https://www.youtube.com/watch?v=abcdefghijk")
    single._fill_from_clipboard()
    assert single.url_input.text().endswith("abcdefghijk"), "a video link must prefill"
    single.url_input.clear()

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

    from core.history import HistoryEntry, HistoryStore

    HistoryStore().add(HistoryEntry(
        title="seen before", url="https://www.youtube.com/watch?v=zzzzzzzzzzz"
    ))
    single.url_input.clear()
    single.show_hint("")
    clipboard.setText("https://www.youtube.com/watch?v=zzzzzzzzzzz")
    single._fill_from_clipboard()
    assert "already" in single.hint_label.text().lower(), "known link must be noted"
    single.url_input.clear()
    clipboard.setText("https://www.youtube.com/watch?v=abcdefghijk")
    single._fill_from_clipboard()
    assert single.hint_label.text() == "", "an unknown link clears the note"
    single.url_input.clear()

    from ui.extension_setup import ExtensionSetupDialog

    setup = ExtensionSetupDialog()
    assert setup._stack.count() == 4, "one setup page per browser"
    assert setup.windowTitle() == "Browser extension setup"
    setup.close()

    from ui.ipc import IpcServer, send_to_primary

    ipc = IpcServer()
    assert ipc.listen(), "the first instance takes the socket name"
    assert send_to_primary({"action": "show"}, timeout_ms=1000), \
        "a second launch reaches the running instance"
    ipc.close()
    assert not send_to_primary({"action": "show"}, timeout_ms=200), \
        "nothing answers once the instance closes"

    # A step button must pass the browser name, not the clicked bool.
    opened = []
    setup._open_page = lambda name: opened.append(name)
    openers = [b for b in setup.findChildren(QtWidgets.QPushButton)
               if b.text().startswith("Open ")]
    assert openers, "a step offers to open the browser page"
    openers[0].clicked.emit(False)
    assert opened and opened[0] in ("Chrome", "Edge", "Brave", "Firefox"), opened

    print("offscreen UI: ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
