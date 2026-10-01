import pathlib


def test_download_worker_uses_core():
    src = pathlib.Path(__file__).resolve().parent.parent / "workers" / "download_worker.py"
    text = src.read_text(encoding="utf-8")
    assert "core.download" in text
    assert "classify_error" not in text  # logic moved to the core


def test_batch_worker_uses_core():
    src = pathlib.Path(__file__).resolve().parent.parent / "workers" / "batch_worker.py"
    text = src.read_text(encoding="utf-8")
    assert "core.download" in text
    assert "workers.pipeline" not in text
    assert "classify_error" not in text  # logic moved to the core


def test_convert_worker_uses_core():
    src = pathlib.Path(__file__).resolve().parent.parent / "workers" / "convert_worker.py"
    text = src.read_text(encoding="utf-8")
    assert "core.convert" in text
