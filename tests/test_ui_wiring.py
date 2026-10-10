"""Guards against a recurring bug class: Qt classes imported from the wrong
module. QPixmap, QIcon, and QKeySequence all live in QtGui, not QtWidgets or
QtCore, and the mistake only surfaces at construction time.
"""

import pathlib

from PyQt5 import QtCore, QtGui, QtWidgets

from ui.style import THEMES

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
