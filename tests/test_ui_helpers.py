from utils.ui_helpers import looks_like_url, reveal_command


def test_looks_like_url_accepts():
    for text in ("https://youtu.be/abc", "http://x.com/1", "youtu.be/abc", "www.facebook.com/reel/1"):
        assert looks_like_url(text), text


def test_looks_like_url_rejects():
    for text in ("", "   ", "hello world", "just text", "ftp:"):
        assert not looks_like_url(text), text


def test_reveal_command_windows_selects_file():
    assert reveal_command("C:/a/b.mp4", "win32") == ["explorer", "/select,C:\\a\\b.mp4"]


def test_reveal_command_macos_reveals():
    assert reveal_command("/a/b.mp4", "darwin") == ["open", "-R", "/a/b.mp4"]


def test_reveal_command_linux_opens_dir():
    assert reveal_command("/a/b.mp4", "linux") == ["xdg-open", "/a"]
