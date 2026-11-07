
from ui.tray import should_hide_on_close


def test_hides_only_with_a_tray_and_no_quit_request():
    assert should_hide_on_close(True, False, True) is True
    assert should_hide_on_close(False, False, True) is False
    assert should_hide_on_close(True, True, True) is False
    assert should_hide_on_close(True, False, False) is False
