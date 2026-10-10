"""Regression guard for the thumbnail bug.

``QtWidgets.QPixmap`` does not exist (QPixmap is in QtGui), so every thumbnail
raised AttributeError, the bare ``except`` swallowed it, and the preview showed
"Failed to load" for every video.

These tests are static on purpose: instantiating Qt widgets under pytest can
hang in some environments, and the bug they guard against is a wrong import,
which a static check catches just as well.
"""

import pathlib

from PyQt5 import QtGui, QtWidgets

SINGLE_TAB = (
    pathlib.Path(__file__).resolve().parent.parent / "ui" / "single_tab.py"
)


def test_pixmap_lives_in_qtgui_not_qtwidgets():
    assert hasattr(QtGui, "QPixmap")
    assert not hasattr(QtWidgets, "QPixmap")


def test_source_never_uses_qtwidgets_pixmap():
    text = SINGLE_TAB.read_text(encoding="utf-8")
    assert "QtWidgets.QPixmap" not in text, (
        "QtWidgets has no QPixmap; this raises AttributeError on every thumbnail"
    )
    assert "QtGui.QPixmap" in text


def test_worker_sends_a_user_agent():
    from ui.single_tab import ThumbnailWorker

    worker = ThumbnailWorker("https://example.com/t.png", 1)
    assert worker._headers().get("User-Agent")


def test_headers_include_cookies_when_provided(tmp_path):
    from ui.single_tab import ThumbnailWorker

    cookie_file = tmp_path / "youtube_cookies.txt"
    # A plain comment line and one tab-separated cookie row: enough to exercise
    # the parser without embedding a real cookie-file marker in the source
    # (which the gitleaks scan correctly flags).
    cookie_file.write_text(
        "# comment line, must be skipped\n"
        ".youtube.com\tTRUE\t/\tFALSE\t0\tSID\tabc123\n"
    )
    worker = ThumbnailWorker(
        "https://example.com/t.png", 1, cookies_path=str(cookie_file)
    )
    headers = worker._headers()
    assert "Cookie" in headers
    assert "SID=abc123" in headers["Cookie"]


def test_thumbnail_failure_surfaces_a_reason():
    """The handler must log a cause rather than a bare 'Failed to load'."""
    text = SINGLE_TAB.read_text(encoding="utf-8")
    assert "Thumbnail unavailable" in text
    assert 'setText("Failed to load")' not in text
