import os

from utils.ui_helpers import looks_like_url, reveal_command


def test_looks_like_url_accepts():
    for text in ("https://youtu.be/abc", "http://x.com/1", "youtu.be/abc", "www.facebook.com/reel/1"):
        assert looks_like_url(text), text


def test_looks_like_url_rejects():
    for text in ("", "   ", "hello world", "just text", "ftp:"):
        assert not looks_like_url(text), text


def test_reveal_command_windows_selects_file():
    assert reveal_command("C:/a/b.mp4", "win32") == ["explorer", '/select,"C:\\a\\b.mp4"']


def test_reveal_command_windows_handles_spaces():
    """explorer parses its own argument line, so a spaced path must be quoted
    or it silently opens the default folder (Documents) instead of selecting."""
    cmd = reveal_command("C:/Users/Me/My Videos/clip one.mp4", "win32")
    assert cmd[0] == "explorer"
    assert cmd[1].startswith("/select,")
    assert '"' in cmd[1], cmd


def test_reveal_command_macos_reveals():
    assert reveal_command("/a/b.mp4", "darwin") == ["open", "-R", "/a/b.mp4"]


def test_reveal_command_linux_opens_dir():
    assert reveal_command("/a/b.mp4", "linux") == ["xdg-open", "/a"]


def test_reveal_in_folder_falls_back_to_parent_when_file_missing(tmp_path, monkeypatch):
    """A missing file must not open a random default folder; open its parent."""
    ran = []
    monkeypatch.setattr(
        "utils.ui_helpers.subprocess.run", lambda cmd, **k: ran.append(cmd)
    )
    missing = tmp_path / "gone.mp4"
    from utils.ui_helpers import reveal_in_folder

    reveal_in_folder(str(missing))
    assert ran, "expected a reveal command to run"
    joined = " ".join(ran[0])
    assert str(tmp_path) in joined or str(tmp_path).replace(os.sep, "/") in joined
