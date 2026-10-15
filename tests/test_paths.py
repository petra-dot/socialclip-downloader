import os
import sys

import pytest

from core import paths


def test_data_dir_honours_env(tmp_path, monkeypatch):
    target = tmp_path / "custom"
    monkeypatch.setenv("SOCIALCLIP_DATA", str(target))
    assert paths.data_dir() == str(target)
    assert os.path.isdir(str(target))


def test_data_dir_default_windows(tmp_path, monkeypatch):
    monkeypatch.delenv("SOCIALCLIP_DATA", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "win32")
    assert paths.default_data_dir() == os.path.join(
        str(tmp_path), paths.APP_DIR_NAME
    )


def test_data_dir_default_linux(tmp_path, monkeypatch):
    monkeypatch.delenv("SOCIALCLIP_DATA", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "linux")
    assert paths.default_data_dir() == os.path.join(str(tmp_path), "socialclip")


def test_managed_dir_kinds(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    assert paths.managed_dir("yt-dlp") == os.path.join(str(tmp_path), "yt-dlp")
    assert paths.managed_dir("bin") == os.path.join(str(tmp_path), "bin")


def test_migrate_copies_and_keeps_originals(tmp_path, monkeypatch):
    legacy = tmp_path / "app"
    data = tmp_path / "data"
    legacy.mkdir()
    (legacy / "queue.json").write_text("[]", encoding="utf-8")
    (legacy / "youtube_cookies.txt").write_text("# Netscape", encoding="utf-8")
    monkeypatch.setattr(paths, "legacy_dir", lambda: str(legacy))
    monkeypatch.setenv("SOCIALCLIP_DATA", str(data))

    copied = paths.migrate_legacy_files()

    assert sorted(copied) == ["queue.json", "youtube_cookies.txt"]
    assert (data / "queue.json").read_text(encoding="utf-8") == "[]"
    assert (legacy / "queue.json").is_file()  # original kept


def test_migrate_never_overwrites(tmp_path, monkeypatch):
    legacy = tmp_path / "app"
    data = tmp_path / "data"
    legacy.mkdir()
    data.mkdir()
    (legacy / "queue.json").write_text("legacy", encoding="utf-8")
    (data / "queue.json").write_text("current", encoding="utf-8")
    monkeypatch.setattr(paths, "legacy_dir", lambda: str(legacy))
    monkeypatch.setenv("SOCIALCLIP_DATA", str(data))

    copied = paths.migrate_legacy_files()

    assert copied == []
    assert (data / "queue.json").read_text(encoding="utf-8") == "current"


def test_migrate_skips_when_same_dir(tmp_path, monkeypatch):
    legacy = tmp_path / "app"
    legacy.mkdir()
    (legacy / "queue.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(paths, "legacy_dir", lambda: str(legacy))
    monkeypatch.setenv("SOCIALCLIP_DATA", str(legacy))
    assert paths.migrate_legacy_files() == []


def test_default_cookie_dir_is_the_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    from sites.cookies import default_cookie_dir
    assert default_cookie_dir() == str(tmp_path)


def test_queue_path_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
    override = tmp_path / "elsewhere" / "q.json"
    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(override))
    import cli
    assert cli._queue_path() == str(override)


def test_queue_path_defaults_into_data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("SOCIALCLIP_QUEUE", raising=False)
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
    import cli
    assert cli._queue_path() == str(tmp_path / "data" / "queue.json")


def test_presets_and_archive_follow_data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("SOCIALCLIP_QUEUE", raising=False)
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
    import cli
    assert cli._presets_path() == str(tmp_path / "data" / "presets.json")
    assert cli._archive_path() == str(tmp_path / "data" / "archive.txt")


def test_queue_path_honours_override(tmp_path, monkeypatch):
    override = tmp_path / "elsewhere" / "q.json"
    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(override))
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
    from core.paths import queue_path
    assert queue_path() == str(override)


def test_core_queue_path_defaults_into_data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("SOCIALCLIP_QUEUE", raising=False)
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
    from core.paths import queue_path
    assert queue_path() == str(tmp_path / "data" / "queue.json")


def test_archive_path_follows_the_queue(tmp_path, monkeypatch):
    monkeypatch.delenv("SOCIALCLIP_QUEUE", raising=False)
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
    from core.archive import default_archive_path
    assert default_archive_path() == str(tmp_path / "data" / "archive.txt")


def test_archive_path_follows_a_queue_override(tmp_path, monkeypatch):
    override = tmp_path / "elsewhere" / "q.json"
    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(override))
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
    from core.archive import default_archive_path
    assert default_archive_path() == str(tmp_path / "elsewhere" / "archive.txt")


def test_presets_path_honours_override(tmp_path, monkeypatch):
    override = tmp_path / "custom" / "p.json"
    monkeypatch.setenv("SOCIALCLIP_PRESETS", str(override))
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
    import cli
    assert cli._presets_path() == str(override)
