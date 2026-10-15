"""Named download presets: editor built-ins plus user presets in a JSON file.

Pure model and store; no Qt. The UI and the CLI apply a preset to their controls.
"""

import json
import os
from dataclasses import asdict, dataclass
from typing import List, Optional

STORE_VERSION = 1


@dataclass
class Preset:
    name: str
    output: str = "MP4"
    resolution: str = "1080"
    convert: bool = True
    add_channel: bool = False
    add_timestamp: bool = False
    save_dir: str = ""
    cookies: str = ""
    builtin: bool = False


BUILTIN_PRESETS = [
    Preset(name="Editor-safe 1080p", output="MP4", resolution="1080",
           convert=True, builtin=True),
    Preset(name="Editor-safe 720p", output="MP4", resolution="720",
           convert=True, builtin=True),
    Preset(name="Audio only (MP3)", output="MP3", resolution="1080",
           convert=False, builtin=True),
    Preset(name="Original quality", output="MP4", resolution="1080",
           convert=False, builtin=True),
    Preset(name="Archive master", output="MP4", resolution="1080",
           convert=False, add_channel=True, add_timestamp=True, builtin=True),
]

_BUILTIN_NAMES = {p.name for p in BUILTIN_PRESETS}


def default_presets_path() -> str:
    from sites.cookies import default_cookie_dir
    return os.path.join(default_cookie_dir(), "presets.json")


def preset_to_dict(preset: Preset) -> dict:
    data = asdict(preset)
    data.pop("builtin", None)
    return data


def preset_from_dict(data) -> Optional[Preset]:
    data = data or {}
    name = data.get("name") or ""
    if not name:
        return None
    return Preset(
        name=name,
        output=data.get("output") or "MP4",
        resolution=data.get("resolution") or "1080",
        convert=bool(data.get("convert", True)),
        add_channel=bool(data.get("add_channel", False)),
        add_timestamp=bool(data.get("add_timestamp", False)),
        save_dir=data.get("save_dir") or "",
        cookies=data.get("cookies") or "",
        builtin=False,
    )


class PresetStore:
    def __init__(self, path: str):
        self.path = path
        self.presets: List[Preset] = []

    def load(self) -> None:
        self.presets = []
        if not self.path:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict) or data.get("version") != STORE_VERSION:
            return
        for raw in data.get("presets") or []:
            preset = preset_from_dict(raw)
            if preset and preset.name not in _BUILTIN_NAMES:
                self.presets.append(preset)

    def save(self) -> None:
        if not self.path:
            return
        data = {
            "version": STORE_VERSION,
            "presets": [preset_to_dict(p) for p in self.presets],
        }
        tmp = "%s.%d.tmp" % (self.path, os.getpid())
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def user(self) -> List[Preset]:
        return list(self.presets)

    def all(self) -> List[Preset]:
        return list(BUILTIN_PRESETS) + list(self.presets)

    def get(self, name: str) -> Optional[Preset]:
        for preset in self.all():
            if preset.name == name:
                return preset
        return None

    def add(self, preset: Preset) -> bool:
        if preset.name in _BUILTIN_NAMES:
            return False
        for index, existing in enumerate(self.presets):
            if existing.name == preset.name:
                self.presets[index] = preset
                return True
        self.presets.append(preset)
        return True

    def remove(self, name: str) -> bool:
        for index, preset in enumerate(self.presets):
            if preset.name == name:
                del self.presets[index]
                return True
        return False

    def rename(self, old: str, new: str) -> bool:
        if not new or new in _BUILTIN_NAMES:
            return False
        for preset in self.presets:
            if preset.name == old:
                preset.name = new
                return True
        return False
