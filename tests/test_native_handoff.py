import socialclip_downloader as entry


def test_hand_off_returns_false_with_no_window_running():
    assert entry._hand_off({"urls": ["https://youtu.be/x"]}, {}) is False


def test_hand_off_returns_true_when_a_window_listens():
    from PyQt5.QtCore import QCoreApplication

    from ui.ipc import IpcServer

    app = QCoreApplication.instance() or QCoreApplication([])
    server = IpcServer()
    assert server.listen()
    try:
        assert entry._hand_off(
            {"urls": ["https://youtu.be/x"], "start": False}, {}
        ) is True
        app.processEvents()
    finally:
        server.close()
