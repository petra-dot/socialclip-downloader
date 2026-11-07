"""Start with the system, per user, without administrator rights.

Windows uses the Run key, macOS a LaunchAgent, Linux an autostart entry. All
three point at the same command the user is running now.
"""

import os
import sys

APP_DIR_NAME = "SocialClip Downloader"
MAC_LABEL = "com.petra-dot.socialclip"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "SocialClipDownloader"


def _windows_command(parts) -> str:
    return " ".join('"%s"' % part for part in parts)


def _mac_plist_path() -> str:
    return os.path.join(
        os.path.expanduser("~"), "Library", "LaunchAgents", MAC_LABEL + ".plist"
    )


def _linux_desktop_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )
    return os.path.join(base, "autostart", "socialclip.desktop")


def _mac_plist(parts) -> str:
    args = "".join("<string>%s</string>" % part for part in parts)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        "  <key>Label</key><string>%s</string>\n"
        "  <key>ProgramArguments</key><array>%s</array>\n"
        "  <key>RunAtLoad</key><true/>\n"
        "</dict></plist>\n" % (MAC_LABEL, args)
    )


def _linux_desktop(parts) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=SocialClip Downloader\n"
        "Exec=%s\n"
        "X-GNOME-Autostart-enabled=true\n" % _windows_command(parts)
    )


def is_enabled() -> bool:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, VALUE_NAME)
            return True
        except OSError:
            return False
    if sys.platform == "darwin":
        return os.path.isfile(_mac_plist_path())
    return os.path.isfile(_linux_desktop_path())


def enable(parts) -> None:
    if sys.platform == "win32":
        import winreg

        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ,
                              _windows_command(parts))
        return
    if sys.platform == "darwin":
        path, content = _mac_plist_path(), _mac_plist(parts)
    else:
        path, content = _linux_desktop_path(), _linux_desktop(parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def disable() -> None:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except OSError:
            pass
        return
    path = _mac_plist_path() if sys.platform == "darwin" else _linux_desktop_path()
    try:
        os.remove(path)
    except OSError:
        pass
