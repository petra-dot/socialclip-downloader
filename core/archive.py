import os

from sites.cookies import app_dir


def default_archive_path() -> str:
    """The archive file: archive.txt beside queue.json and presets.json."""
    return os.path.join(app_dir(), "archive.txt")


def clear_archive(path: str) -> bool:
    """Delete the archive file. Returns whether a file was removed.

    Never raises: a missing file, a directory in its place, or a permission
    error all return False so the caller can report "nothing to clear".
    """
    try:
        os.remove(path)
        return True
    except OSError:
        return False
