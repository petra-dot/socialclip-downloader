"""Guards against a recurring bug class: Qt classes imported from the wrong
module. QPixmap, QIcon, and QKeySequence all live in QtGui, not QtWidgets or
QtCore, and the mistake only surfaces at construction time.
"""

import pathlib

from PyQt5 import QtCore, QtGui, QtWidgets

from ui.style import THEMES, THEME_LABELS

UI_DIR = pathlib.Path(__file__).resolve().parent.parent / "ui"

# (wrong reference, the module that actually owns it)
WRONG_REFS = (
    "QtWidgets.QPixmap",
    "QtWidgets.QIcon",
    "QtWidgets.QKeySequence",
    "QtCore.QPixmap",
    "QtCore.QIcon",
    "QtCore.QKeySequence",
)


def test_wrong_module_references_absent_from_ui():
    offenders = []
    for path in UI_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for ref in WRONG_REFS:
            if ref in text:
                offenders.append("%s: %s" % (path.name, ref))
    assert not offenders, offenders


def test_the_qt_classes_are_where_we_claim():
    assert hasattr(QtGui, "QPixmap")
    assert hasattr(QtGui, "QIcon")
    assert hasattr(QtGui, "QKeySequence")
    assert not hasattr(QtWidgets, "QPixmap")
    assert not hasattr(QtWidgets, "QKeySequence")
    assert not hasattr(QtCore, "QKeySequence")


def test_theme_modes_are_the_three_expected():
    assert THEMES == ("system", "light", "dark")


def test_every_theme_mode_has_a_label():
    assert set(THEME_LABELS) == set(THEMES)
    assert THEME_LABELS["system"] == "Default"


def test_dark_theme_applies_the_palette_under_fusion():
    # Windows' native style ignores most of a custom QPalette, which made the
    # dark theme light-on-light. The dark branch must switch to Fusion first.
    src = (UI_DIR / "style.py").read_text(encoding="utf-8")
    assert 'setStyle("Fusion")' in src


def test_convert_worker_announces_output_path():
    from workers.convert_worker import ConvertFileWorker

    assert hasattr(ConvertFileWorker, "output_signal")
    assert hasattr(ConvertFileWorker, "finished_signal")


def test_update_workers_expose_their_signals():
    from workers.update_worker import UpdateCheckWorker, UpdateDownloadWorker

    assert hasattr(UpdateCheckWorker, "done_signal")
    assert hasattr(UpdateCheckWorker, "error_signal")
    assert hasattr(UpdateDownloadWorker, "progress_signal")
    assert hasattr(UpdateDownloadWorker, "done_signal")
    assert hasattr(UpdateDownloadWorker, "error_signal")


def test_expand_worker_exposes_its_signals():
    from workers.expand_worker import ExpandWorker

    assert hasattr(ExpandWorker, "done_signal")
    assert hasattr(ExpandWorker, "error_signal")
