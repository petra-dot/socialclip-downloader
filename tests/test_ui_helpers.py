import os

from utils.ui_helpers import looks_like_url, reveal_command, reveal_shell_string


def test_looks_like_url_accepts():
    for text in ("https://youtu.be/abc", "http://x.com/1", "youtu.be/abc", "www.facebook.com/reel/1"):
        assert looks_like_url(text), text


def test_looks_like_url_rejects():
    for text in ("", "   ", "hello world", "just text", "ftp:"):
        assert not looks_like_url(text), text


def test_reveal_command_windows_selects_file():
    # A non-existent path is treated as a file to select.
    assert reveal_command("C:/a/b.mp4", "win32") == ["explorer", '/select,"C:\\a\\b.mp4"']


def test_reveal_shell_string_windows_quotes_the_whole_command():
    """explorer.exe parses one raw command line; passing a pre-quoted argv
    element misreads it and opens Documents. The whole command must be one
    string (verified working on the user's machine)."""
    s = reveal_shell_string("C:/a/b.mp4", "win32")
    assert s == 'explorer /select,"C:\\a\\b.mp4"'


def test_reveal_shell_string_windows_spaced_path():
    s = reveal_shell_string("C:/My Videos/clip one.mp4", "win32")
    assert s is not None
    assert s.startswith("explorer /select,")
    assert '"' in s


def test_reveal_shell_string_none_on_other_platforms():
    assert reveal_shell_string("/a/b.mp4", "darwin") is None
    assert reveal_shell_string("/a/b.mp4", "linux") is None


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
    # cmd is a shell string on Windows, a list elsewhere; both must name the dir.
    arg = ran[0] if isinstance(ran[0], str) else " ".join(ran[0])
    assert str(tmp_path) in arg, (ran, str(tmp_path))
