from utils.system_theme import detect


def test_windows_light_and_dark_from_the_registry():
    assert detect(runner=lambda cmd: "1", platform="win32") == "light"
    assert detect(runner=lambda cmd: "0", platform="win32") == "dark"


def test_macos_uses_apple_interface_style():
    assert detect(runner=lambda cmd: "Dark", platform="darwin") == "dark"
    assert detect(runner=lambda cmd: "", platform="darwin") == "light"


def test_linux_reads_the_gnome_color_scheme():
    assert detect(runner=lambda cmd: "'prefer-dark'", platform="linux") == "dark"
    assert detect(runner=lambda cmd: "'default'", platform="linux") == "light"


def test_a_failing_runner_falls_back_to_light():
    def boom(cmd):
        raise OSError("no shell")

    assert detect(runner=boom, platform="linux") == "light"
    assert detect(runner=lambda cmd: "garbage", platform="win32") == "light"
