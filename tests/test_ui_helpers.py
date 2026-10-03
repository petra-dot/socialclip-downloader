import os

from utils.ui_helpers import looks_like_url, reveal_command


def test_looks_like_url_accepts():
    for text in ("https://youtu.be/abc", "http://x.com/1", "youtu.be/abc", "www.facebook.com/reel/1"):
        assert looks_like_url(text), text


def test_looks_like_url_rejects():
    for text in ("", "   ", "hello world", "just text", "ftp:"):
        assert not looks_like_url(text), text


def test_reveal_command_windows_selects_file():
    # A non-existent path is treated as a file to select.
    assert reveal_command("C:/a/b.mp4", "win32") == ["explorer", '/select,"C:\\a\\b.mp4"']


def test_reveal_command_windows_quotes_spaced_paths():
    """explorer parses its own argument line; an unquoted spaced path makes it
    silently open the default folder (Documents) instead of selecting."""
    cmd = reveal_command("C:/Users/Me/My Videos/clip one.mp4", "win32")
    assert cmd[0] == "explorer"
    assert cmd[1].startswith("/select,")
    assert '"' in cmd[1], cmd


def test_reveal_command_windows_opens_a_directory():
    d = os.path.dirname(os.path.abspath(__file__))
    cmd = reveal_command(d, "win32")
    assert cmd[0] == "explorer"
    assert not cmd[1].startswith("/select,"), cmd
    assert '"' in cmd[1]


def test_reveal_command_macos_reveals():
    assert reveal_command("/a/b.mp4", "darwin") == ["open", "-R", "/a/b.mp4"]


def test_reveal_command_linux_opens_file_parent():
    assert reveal_command("/a/b.mp4", "linux") == ["xdg-open", "/a"]


def test_reveal_command_linux_opens_a_directory_directly():
    d = os.path.dirname(os.path.abspath(__file__))
    cmd = reveal_command(d, "linux")
    assert cmd == ["xdg-open", d]


def test_reveal_in_folder_opens_parent_when_file_missing(tmp_path, monkeypatch):
    """A missing file must open its containing folder, not a default folder."""
    ran = []
    monkeypatch.setattr(
        "utils.ui_helpers.subprocess.run", lambda cmd, **k: ran.append(cmd)
    )
    from utils.ui_helpers import reveal_in_folder

    missing = tmp_path / "gone.mp4"
    reveal_in_folder(str(missing))
    assert ran, "expected a reveal command to run"
    joined = " ".join(ran[0])
    assert str(tmp_path) in joined, (ran, str(tmp_path))
