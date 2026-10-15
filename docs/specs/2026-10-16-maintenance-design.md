# Maintenance and Self-Repair - Design

Status: proposed
Date: 2026-10-16
Applies to: `core/paths.py` (new), `core/maintenance.py` (new),
`workers/maintenance_worker.py` (new), `utils/ytdlp.py`, `utils/ffmpeg.py`,
`core/doctor.py`, `ui/dialogs.py`, `ui/main_window.py`, `cli.py`,
`socialclip_downloader.py`, `sites/cookies.py`, `tests/test_paths.py` (new),
`tests/test_maintenance.py` (new)

## Problem

A PyInstaller build bundles a pinned yt-dlp and ffmpeg, and cannot update
either. yt-dlp's extractors rot in weeks: a site changes, and the download
starts failing. YouTube additionally needs a JavaScript runtime that is not
bundled at all, so a machine without deno or node gets HTTP 403 on every
YouTube download. Today the only cure for any of this is a new app release, so
a build can be unusable days after it was installed.

The app also keeps its state next to the executable (`app_dir()`): cookies,
`queue.json`, `presets.json`, `archive.txt`. That directory is read-only in
real installs - a macOS app run from a quarantined download, a Linux binary in
`/usr/local/bin`, anything under `Program Files` - so the queue and cookies can
silently fail to save.

## Goal

The app keeps itself working without a new release. It knows the state of each
component it depends on (the app, yt-dlp, ffmpeg, the JavaScript runtime), and
when one is missing, stale, or broken it downloads a verified replacement into
a per-user data directory and uses it. A **Health** view shows every component
and lets the user repair by hand. Nothing blocks startup, and nothing replaces a
working component before its replacement is verified.

## Non-goals

- Code signing. An unsigned build still trips SmartScreen; free OSS signing
  (SignPath) is a later option.
- Shipping the binaries in the release. They are fetched on first need, which
  keeps the download small; the app bundle stays as it is.
- Updating the app itself. `core/updater.py` already does that; this feature
  sits beside it.
- Delta or patch updates. Whole assets are downloaded.
- Repairing or replacing a system-wide install. The app manages only its own
  per-user copies, and never deletes anything it did not put there.
- A new runtime dependency. Everything uses `urllib`, `zipfile`, and the
  standard library.

## Decisions taken

1. **A per-user data directory holds all writable state** - cookies, `queue.json`,
   `presets.json`, `archive.txt`, and the managed binaries.
   `%LOCALAPPDATA%\SocialClip Downloader` (Windows),
   `~/Library/Application Support/SocialClip Downloader` (macOS),
   `$XDG_DATA_HOME/socialclip` or `~/.local/share/socialclip` (Linux).
   `SOCIALCLIP_DATA` overrides it, for tests and advanced use.
2. **A one-time copy migration** moves any legacy app-dir files into the data
   dir on first run. Files are copied, never moved or deleted, and never
   overwritten.
3. **Check at most once a day, in the background.** Repair runs when a component
   is missing, stale (yt-dlp older than 90 days), or broken. A manual check
   ignores the cache.
4. **Repair is automatic everywhere, including source runs**, but a source run
   never clobbers a pip-installed yt-dlp: the managed copy is used only when the
   installed one is missing, stale, or broken. `pip` and the app do not fight.
5. **A managed copy wins over the bundled one or `PATH`** when present. It is
   newer by construction, and that is the point of managing it.
6. **Every download is HTTPS, host allow-listed, and SHA-256 verified** before
   the file is unpacked or used.
7. **Atomic swap with rollback.** Unpack to a temp directory, verify, then
   swap. yt-dlp keeps a `.prev` copy; a copy that fails to import is rolled
   back and marked broken.
8. **Sources:** yt-dlp's own GitHub release **source tarball** (`yt-dlp.tar.gz`,
   which carries the `yt_dlp` package) plus its `SHA2-256SUMS`; BtbN
   `ffmpeg-builds` latest (win64 / linux64) plus its `checksums.sha256`;
   `denoland/deno` latest per-platform zip plus its checksum. All are
   GitHub-hosted, so one host allow-list covers them. The yt-dlp release
   publishes **no wheel** (wheels live on PyPI), so the tarball is the source.
9. **The Health view is the existing Doctor dialog, extended** - one row per
   component with its version and state, plus **Repair**, **Repair all**, and
   **Open data folder**.
10. **Startup repair never blocks the UI and never removes a working component**
    before its replacement is verified.
11. **`SOCIALCLIP_QUEUE` is kept, folded into `SOCIALCLIP_DATA`.** When set, it
    still overrides the queue file's directory, so existing scripts and tests
    keep working; otherwise the queue lives in `data_dir()` like the rest.
    `SOCIALCLIP_DATA` moves the whole data directory and wins over it.
12. **Managed locations are fixed:** yt-dlp unpacks to `data_dir/yt-dlp/yt_dlp/`,
    ffmpeg and ffprobe to `data_dir/bin/`, deno to `data_dir/bin/deno`
    (`deno.exe` on Windows). `data_dir/yt-dlp.prev/` holds the rollback copy.

## Architecture

### `core/paths.py` (new, Qt-free)

```python
DATA_ENV = "SOCIALCLIP_DATA"

def data_dir() -> str                    # per-user dir, created on demand
def legacy_dir() -> str                  # app_dir(), where state lived before
def managed_dir(kind: str) -> str        # "yt-dlp" | "bin"
def migrate_legacy_files() -> list       # names copied, for the log
def data_dir_writable() -> bool
```

- `data_dir()` returns `os.environ["SOCIALCLIP_DATA"]` when set, else the
  platform default, and creates it (`os.makedirs(..., exist_ok=True)`). On
  failure it falls back to `legacy_dir()` so the app still runs.
- `migrate_legacy_files()` copies `queue.json`, `presets.json`, `archive.txt`,
  and every `*_cookies.txt` from `legacy_dir()` to `data_dir()` when the target
  is absent. It returns the names copied. It never overwrites and never deletes.

### `core/maintenance.py` (new, Qt-free)

```python
STATES = ("ok", "missing", "stale", "broken", "unknown")

@dataclass Component:
    key: str          # "app" | "yt-dlp" | "ffmpeg" | "js-runtime" | "data-dir"
    label: str
    state: str
    version: str
    detail: str
    action: str       # "none" | "install" | "update"

check_all(data_dir=None) -> list          # every Component, no network
plan_repairs(components) -> list          # component keys needing a repair
install_ytdlp(dest, opener=None) -> str   # version installed
install_ffmpeg(dest, opener=None) -> str
install_deno(dest, opener=None) -> str
latest_ytdlp(opener=None) -> tuple        # (version, wheel_url, sums_url)
```

- `check_all` reads local state only: `__version__`, the managed/installed
  yt-dlp version and its age, `ffmpeg -version` presence, and
  `utils.ytdlp.find_js_runtime()`. No network, so it is fast and testable.
- `plan_repairs` is pure: `missing`/`broken` -> `install`, `stale` -> `update`,
  `ok`/`unknown` -> nothing. `app` and `data-dir` are never repaired here.
- Each `install_*` fetches, verifies the SHA-256, unpacks to a temp directory,
  and swaps it in. An injected `opener` makes the network fakeable in tests.

### `utils/ytdlp.py` (extend)

```python
def load() -> str            # "managed" | "system"; inserts managed on sys.path
def managed_ytdlp_dir() -> str
def find_js_runtime()        # now also checks data_dir/bin/deno first
```

`load()` runs before anything imports `yt_dlp`. If `managed_dir("yt-dlp")`
contains a package it is inserted at the front of `sys.path`; otherwise the
bundled or installed `yt_dlp` is used. It is idempotent.

### `utils/ffmpeg.py` (extend)

`ffmpeg_path()` / `ffprobe_path()` order becomes: managed `bin/` ->
`SOCIALCLIP_FFMPEG` / `FFMPEG_LOCATION` -> bundled -> `PATH`.

### `workers/maintenance_worker.py` (new)

Mirrors `workers/expand_worker.py`:
- `MaintenanceCheckWorker` -> `done_signal(list[Component])`, `error_signal(str)`
- `MaintenanceRepairWorker(keys)` -> `progress_signal(str key, str detail)`,
  `done_signal(list[Component])`, `error_signal(str)`

### `ui/dialogs.py`

`DoctorDialog` gains a components table: label, version, state, detail, and a
**Repair** button per repairable row, plus **Repair all** and **Open data
folder**. The existing ffmpeg / cookies / network / runtime / yt-dlp lines
become the rows.

### `ui/main_window.py`

- Startup: `MaintenanceCheckWorker`; when `plan_repairs` is non-empty,
  `MaintenanceRepairWorker` runs and logs one line. Cache the check in
  `QSettings` under `maintenance/last_check` (ISO time), skipped when under 24h.
- **Help -> Check components** forces a check; the dialog offers Repair.

### Entry points

```python
# socialclip_downloader.main(), before any Qt or core.download import
from core.paths import migrate_legacy_files
from utils.ytdlp import load
migrate_legacy_files()
load()
```

`cli.py` does the same at the top of `main()`. A `repair` subcommand runs
`plan_repairs` + the repair workers synchronously for scripting.

## Data flow

```
main()
  core.paths.migrate_legacy_files()   # copy legacy state into data_dir
  utils.ytdlp.load()                  # managed yt-dlp on sys.path, if present
  ... Qt ...
  MaintenanceCheckWorker              # local state only
    -> no repairs? done
    -> repairs?   MaintenanceRepairWorker
        -> install_*: fetch -> verify -> unpack temp -> swap -> re-check
```

`core/download.py` and `utils/ydl_opts.py` keep `from yt_dlp import YoutubeDL`;
they are imported after `load()` in both entry points. A test asserts the
managed copy takes precedence.

## Platform behaviour

| Component | Windows | macOS | Linux |
|---|---|---|---|
| yt-dlp | source tarball + `SHA2-256SUMS`, auto | same | same |
| ffmpeg | BtbN win64 | **no verified source: refuse and point at Homebrew** | BtbN linux64 |
| deno | `deno-x86_64-pc-windows-msvc.zip` | `...-apple-darwin.zip` | `...-unknown-linux-gnu.zip` |
| app | `core/updater.py` (self-install) | notify | notify |

A JavaScript runtime already on `PATH` is used first; a runtime the app
installed is the fallback for a machine that has none, so the app never
overrides a working system install.

## Security

- HTTPS only. The host must be `github.com`, `api.github.com`,
  `objects.githubusercontent.com`, or `release-assets.githubusercontent.com`
  (GitHub redirects release assets to the last of these), checked on the
  initial URL **and on every redirect hop**.
- Every asset's SHA-256 is verified against the publisher's checksum file before
  it is unpacked or used. A mismatch deletes the download and reports the
  reason.
- Nothing is installed over a working component until its replacement is
  verified.
- The app only manages files inside `data_dir()`; it never deletes a file it did
  not create.
- Downloaded executables (ffmpeg, deno) are `chmod +x`'d on POSIX.

## Testing

`tests/test_paths.py`:
- `data_dir()` honours `SOCIALCLIP_DATA`, else the platform default
  (monkeypatched env and platform).
- `migrate_legacy_files()` copies when the target is absent, never overwrites,
  never deletes the original, and returns the copied names.

`tests/test_maintenance.py`:
- `check_all` with fake files and versions -> the expected state per component.
- `plan_repairs`: missing/broken -> install, stale -> update, ok/unknown ->
  nothing, app and data-dir never.
- version parsing and the 90-day staleness boundary.
- `install_ytdlp` with a fake `opener` serving a small wheel and a matching sums
  file: unpacked, verified, swapped. A wrong digest is refused and nothing is
  swapped.
- `utils.ytdlp.load()` precedence, in a subprocess, so `sys.path` is real.

No tests for the real network, the `QThread`s, or the Qt view; those are
verified by hand, matching the repo's treatment of network and Qt code.

## Risks

1. **We import downloaded Python.** A managed yt-dlp is third-party code the app
   executes. The SHA-256 check against the canonical `yt-dlp/yt-dlp` release is
   the trust anchor, exactly as the app updater trusts GitHub's digest. The
   allow-list stops a redirect to another host.
2. **A new yt-dlp can regress.** The `.prev` copy plus Repair is the escape
   hatch; a copy that fails to import is rolled back automatically.
3. **BtbN builds are GPLv3**, unlike the LGPL ffmpeg the release bundles today.
   The app downloads them at the user's request and does not redistribute them,
   so this is a note, not a licence change - but it is worth stating.
4. **macOS has no verified automatic ffmpeg source.** BtbN publishes no macOS
   build, and the app will not install an unverified one, so `install_ffmpeg`
   refuses on macOS with a message pointing at `brew install ffmpeg` or
   `SOCIALCLIP_FFMPEG`. yt-dlp and deno still repair automatically there.
5. **First repair can be large** (~3 MB yt-dlp, ~40 MB deno, ~80 MB ffmpeg) and
   only happens when a component is missing or stale.
6. **Migration could surprise a user with a queue.** It copies and keeps the
   originals, and logs what it did, so nothing is lost either way.
7. **macOS quarantines a downloaded binary.** `chmod +x` is applied; if
   Gatekeeper still blocks it, Health shows the failure and the user can clear
   the attribute by hand.
8. **Corporate proxies may block GitHub.** Health shows the reason; the manual
   **Browse** cookie path and `SOCIALCLIP_FFMPEG` still work.
