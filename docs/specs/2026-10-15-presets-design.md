# Download Presets - Design

Status: proposed
Date: 2026-10-15
Applies to: `core/presets.py` (new), `ui/single_tab.py`, `ui/batch_tab.py`,
`cli.py`, `tests/test_presets.py` (new)

## Problem

Every download re-sets the same choices by hand: output format, resolution,
the convert toggle, the filename options, the save folder, and the cookies
file. The single tab persists only the folder and cookies, so format and
resolution reset on every launch. The queue tab persists the same two and
resets the rest. A video editor downloading a batch of clips repeats the setup
on every run, and there is no way to keep a known-good setup to reuse.

## Goal

Save the whole download setup as a named preset, apply it in one click from the
Download tab and the Queue tab, and use it from the CLI, with editor-first
built-ins that match the app's contract.

## Non-goals

- Presets for the Convert tab (a separate, later feature).
- Auto-applying a preset by platform or URL.
- A preset marketplace or sharing format.
- Changing the download result contract (`schema_version` `"1.0"`).

## Decisions taken

1. **A preset holds the whole download setup:** output format, resolution, the
   convert toggle, the two filename options, the save folder, and the cookies
   file.
2. **Storage: a `presets.json` file next to the app** (the `queue.json`
   directory), plus the last-used preset name in `QSettings`.
3. **Both tabs and the CLI.** A selector on the Download and Queue tabs, and
   `download --preset NAME`.
4. **Editor-first built-ins plus your own.** Built-ins live in code and are not
   editable; the file holds only user presets.

## Architecture

### `core/presets.py` (new, Qt-free)

```python
@dataclass
class Preset:
    name: str
    output: str          # "MP4" or "MP3"
    resolution: str      # "1080", "720", ...
    convert: bool
    add_channel: bool
    add_timestamp: bool
    save_dir: str
    cookies: str
    builtin: bool = False

BUILTIN_PRESETS: List[Preset]

class PresetStore:
    def __init__(self, path): ...
    def load(self): ...
    def save(self): ...
    def all(self) -> List[Preset]      # built-ins first, then user presets
    def user(self) -> List[Preset]
    def get(self, name) -> Optional[Preset]
    def add(self, preset): ...         # user preset; replaces same-name user preset
    def remove(self, name) -> bool     # user presets only
    def rename(self, old, new) -> bool # user presets only
```

- `to_dict` / `from_dict` on `Preset`, and a versioned file shape, so a future
  field is additive.
- `all()` returns `BUILTIN_PRESETS` followed by the user presets, so built-ins
  always appear and cannot be shadowed.
- `remove`/`rename` refuse a built-in name, and `add` refuses a name that
  matches a built-in, so built-ins cannot be shadowed.

### Built-ins (in code)

| Name | Format | Resolution | Convert | Filename |
|---|---|---|---|---|
| Editor-safe 1080p | MP4 | 1080 | yes | - |
| Editor-safe 720p | MP4 | 720 | yes | - |
| Audio only (MP3) | MP3 | - | no | - |
| Original quality | MP4 | (source) | no | - |
| Archive master | MP4 | (source) | no | +channel +timestamp |

"Original quality" and "Archive master" leave convert off (keep the source
resolution); the editor-safe codec guarantee still applies to every download.
"Audio only (MP3)" ignores the resolution.

### Storage

`presets.json` in the app directory (`default_cookie_dir()`, the same place as
`queue.json`), version-stamped:

```json
{"version": 1, "presets": [
  {"name": "My setup", "output": "MP4", "resolution": "1080", "convert": true,
   "add_channel": false, "add_timestamp": false, "save_dir": "D:/clips",
   "cookies": ""}
]}
```

The file holds only user presets; the built-ins live in code, so a release can
add one without touching the file. The last-used preset name is stored in
`QSettings` under `preset/last`.

### `ui/single_tab.py`

A **Preset:** row at the top of the Output section: a combo listing the
built-ins and the user presets, plus a **Custom** entry, and two buttons,
**Save as preset...** and **Manage**.

- Selecting a preset applies format, resolution, the convert toggle, both
  filename checkboxes, the save folder, and the cookies file.
- Editing any of those controls flips the combo to **Custom**.
- **Save as preset...** prompts for a name, captures the current settings,
  stores them, and selects the new preset.
- **Manage** opens a small dialog to rename or delete the selected user preset;
  built-ins are excluded.
- On launch, the combo re-selects `preset/last` if that preset still exists.

### `ui/batch_tab.py`

The same **Preset:** selector, applying format, resolution, save folder, and
cookies. Management stays on the Download tab. The Queue has no filename
checkboxes, so a preset's channel/timestamp options are not applied there, and
the tooltip says so.

### `cli.py`

`download --preset NAME` loads the preset and uses its format, resolution,
convert, cookies, and folder. Precedence is **explicit flag > preset > default**.
An unknown name exits `2` with a message.

For that precedence to hold, `--format` and `--resolution` default to `None`
(today they default to `"mp4"` and `1080`, which would silently beat a preset);
the effective value is `flag or preset or "mp4"/1080`. `--output` and
`--cookies` already default to `None`.

## Testing

`tests/test_presets.py`:
- `Preset` serialization round-trip; a version guard on load.
- `BUILTIN_PRESETS` present and well-formed (five entries, expected names).
- `PresetStore` add / remove / rename / get against a `tmp_path` file; `get` on
  an unknown name returns `None`; remove/rename refuse a built-in.
- One CLI test: `download --preset nope` exits `2`, hermetic (dependency checks
  monkeypatched, like the clip test).

No tests for the Qt widgets or the apply-into-controls path; verified by hand,
matching the repo convention.

## Risks

1. `presets.json` in the app directory fails to write in a read-only install
   (for example Program Files). The same limitation `queue.json` already has;
   the store degrades to in-memory when the file is unwritable.
2. A preset's save folder may not exist on this machine. Applying it sets the
   field; the download creates the folder, as it does today.
3. A built-in cannot be edited, so a user who wants a variation must save their
   own from the controls; this is intentional and keeps releases able to add
   built-ins.
4. The Queue ignores a preset's filename options; documented in the UI.
