
from core.autostart import _linux_desktop, _mac_plist, _windows_command


def test_windows_command_quotes_every_part():
    assert _windows_command(["C:/Program Files/x.exe", "--hidden"]) == (
        '"C:/Program Files/x.exe" "--hidden"'
    )


def test_mac_plist_names_the_program_and_runs_at_load():
    text = _mac_plist(["/Applications/SocialClip"])
    assert "<string>/Applications/SocialClip</string>" in text
    assert "RunAtLoad" in text


def test_linux_desktop_has_the_exec_line():
    text = _linux_desktop(["/usr/bin/socialclip"])
    assert 'Exec="/usr/bin/socialclip"' in text
