import os

from core.archive import clear_archive, default_archive_path
from sites.cookies import app_dir


def test_default_archive_path_is_beside_the_queue_file():
    path = default_archive_path()
    assert path.endswith("archive.txt")
    assert os.path.dirname(path) == app_dir()


def test_clear_archive_removes_the_file(tmp_path):
    target = tmp_path / "archive.txt"
    target.write_text("youtube abc\n")
    assert clear_archive(str(target)) is True
    assert not target.exists()


def test_clear_archive_missing_file_returns_false(tmp_path):
    assert clear_archive(str(tmp_path / "nope.txt")) is False


def test_clear_archive_never_raises_on_a_directory(tmp_path):
    # A directory where the file should be must not raise.
    assert clear_archive(str(tmp_path)) is False
