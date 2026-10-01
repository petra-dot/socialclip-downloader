import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets  # noqa: E402

from core.manifest import DownloadResult  # noqa: E402
from workers.download_worker import DownloadWorker  # noqa: E402


def _run(monkeypatch, result):
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr("core.download.download_one", lambda *a, **k: result)
    worker = DownloadWorker("https://a.com/1", "C:/o.%(ext)s", False, 1080, "MP4")
    paths, messages = [], []
    worker.path_signal.connect(paths.append)
    worker.finished_signal.connect(messages.append)
    worker.run()
    return paths, messages


def test_path_signal_emits_final_path_on_success(monkeypatch):
    paths, messages = _run(monkeypatch, DownloadResult(
        status="ok", url="https://a.com/1", path="C:/out/clip.mp3",
        message="MP3 saved"))
    assert paths == ["C:/out/clip.mp3"]
    assert messages == ["MP3 saved"]


def test_path_signal_empty_on_error(monkeypatch):
    paths, messages = _run(monkeypatch, DownloadResult(
        status="error", url="https://a.com/1", message="boom",
        error_category="other"))
    assert paths == [""]
    assert messages == ["boom"]
