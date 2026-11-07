import os

import pytest

import socialclip_downloader as entry


@pytest.fixture(autouse=True)
def isolated_ipc(monkeypatch):
    # A real app may be running and owning the default name.
    monkeypatch.setenv("SOCIALCLIP_IPC", "socialclip-test-%d" % os.getpid())


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
