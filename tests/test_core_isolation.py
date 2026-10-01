import pathlib


def test_core_has_no_qt_imports():
    core_dir = pathlib.Path(__file__).resolve().parent.parent / "core"
    offenders = []
    for path in core_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "PyQt5" in text or "PySide" in text:
            offenders.append(str(path))
    assert offenders == []
