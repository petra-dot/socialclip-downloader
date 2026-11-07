"""Register the native-messaging host with each installed browser.

Chromium browsers read the host name from an HKCU registry key whose default
value is the manifest path; Firefox uses the same shape under its own key.
No administrator rights are involved.
"""

import json
import os
import sys

from core.native import HOST_NAME
from core.paths import data_dir

CHROMIUM_REGISTRY_PATHS = (
    r"Software\Google\Chrome\NativeMessagingHosts",
    r"Software\Microsoft\Edge\NativeMessagingHosts",
)
FIREFOX_REGISTRY_PATH = r"Software\Mozilla\NativeMessagingHosts"
FIREFOX_ADDON_ID = "socialclip@petra-dot"
DESCRIPTION = "SocialClip Downloader native host"


def host_manifest(executable: str, extension_id: str,
                  firefox: bool = False) -> dict:
    manifest = {
        "name": HOST_NAME,
        "description": DESCRIPTION,
        "path": executable,
        "type": "stdio",
    }
    if firefox:
        manifest["allowed_extensions"] = [extension_id]
    else:
        manifest["allowed_origins"] = ["chrome-extension://%s/" % extension_id]
    return manifest


def manifest_path(firefox: bool = False, data: str = None) -> str:
    """Chromium and Firefox read separate files, so they cannot overwrite."""
    suffix = ".firefox.json" if firefox else ".json"
    return os.path.join(data or data_dir(), HOST_NAME + suffix)


def wrapper_script(entry: str, data: str = None):
    """A launcher that carries --native-host for a source checkout.

    A manifest pointing straight at python.exe cannot pass the flag.
    """
    directory = data or data_dir()
    if sys.platform.startswith("win"):
        path = os.path.join(directory, "native-host.cmd")
        content = '@"%s" "%s" --native-host %%*\r\n' % (sys.executable, entry)
    else:
        path = os.path.join(directory, "native-host.sh")
        content = '#!/bin/sh\nexec "%s" "%s" --native-host "$@"\n' % (
            sys.executable,
            entry,
        )
    return path, content


def _write_json(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")


def _register(key_path: str, path: str) -> bool:
    import winreg

    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE
    ) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, path)
    return True


def install(executable: str, extension_id: str, frozen: bool = True,
            data: str = None) -> list:
    """Write both manifests and register them. Returns the keys written."""
    directory = data or data_dir()
    os.makedirs(directory, exist_ok=True)
    host_exe = executable
    if not frozen:
        path, content = wrapper_script(executable, directory)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
        if not sys.platform.startswith("win"):
            os.chmod(path, 0o755)
        host_exe = path

    chromium = manifest_path(False, directory)
    firefox = manifest_path(True, directory)
    _write_json(chromium, host_manifest(host_exe, extension_id))
    _write_json(firefox, host_manifest(host_exe, FIREFOX_ADDON_ID, firefox=True))

    if not sys.platform.startswith("win"):
        print("Wrote %s and %s. Register them with your browser manually."
              % (chromium, firefox))
        return []

    written = []
    for base in CHROMIUM_REGISTRY_PATHS:
        _register(base + "\\" + HOST_NAME, chromium)
        written.append(base + "\\" + HOST_NAME)
    _register(FIREFOX_REGISTRY_PATH + "\\" + HOST_NAME, firefox)
    written.append(FIREFOX_REGISTRY_PATH + "\\" + HOST_NAME)
    return written
