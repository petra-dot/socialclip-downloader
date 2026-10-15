# In-App Updater - Design

Status: proposed
Date: 2026-10-15
Applies to: `core/updater.py` (new), `workers/update_worker.py` (new),
`ui/update_indicator.py` (new), `ui/main_window.py`, `ui/dialogs.py`,
`socialclip_downloader.py`, `tests/test_updater.py` (new)

## Problem

Users run a PyInstaller onefile build and have no way to learn a newer release
exists, or to install it, without visiting GitHub by hand. yt-dlp sites change
often, so a stale build silently rots. The app knows its own `__version__`
(`socialclip_downloader.py:4`) and its releases are public on GitHub, so it can
check and update itself.

## Goal

The app checks GitHub for a newer release, shows an unobtrusive top-right
indicator when one exists, and on Windows downloads, verifies, and installs it
with a restart, the way a modern desktop app updates itself. Everywhere else it
notifies and opens the release page.

## Non-goals

- Code signing. The download is digest-verified, but an unsigned exe still
  triggers SmartScreen on first run. Free OSS signing (SignPath) is a later
  option, not this feature.
- Delta or patch updates. The whole OS asset is downloaded each time.
- Self-install on macOS or Linux. Those platforms notify only; the `.app`
  bundle and the range of Linux install methods make a reliable in-place swap
  more than this feature should take on.
- Automatic rollback if a new version misbehaves.
- A new runtime dependency. The updater uses `urllib` and the standard library.

## Decisions taken

1. **Windows self-updates; macOS and Linux notify and open the release page.**
2. **Check on startup, cached to at most once per 24h**, plus a manual
   **Help -> Check for updates** that ignores the cache.
3. **Verify the downloaded binary's SHA-256** against the digest GitHub's
   release API reports for the asset. On mismatch, delete and refuse.
4. **Source runs notify only.** A source tree is updated with git, so a
   non-frozen run never downloads; it opens the release page.
5. **Relaunch-with-flag is the install mechanism**, not renaming the running
   executable. The downloaded exe is spawned with `--apply-update`, waits for
   the old process to exit, copies itself over the target, and relaunches.
6. **A batch helper is the fallback** only when the copy cannot complete inside
   the timeout, so a failed clean swap still finishes.

## Architecture

### `core/updater.py` (new, Qt-free, stdlib only)

```python
GITHUB_OWNER = "petra-dot"
REPO = "socialclip-downloader"
LATEST_API = "https://api.github.com/repos/petra-dot/socialclip-downloader/releases/latest"

@dataclass ReleaseInfo: tag: str; version: str; page_url: str; assets: list
@dataclass AssetInfo:   name: str; download_url: str; digest: Optional[str]
@dataclass ApplyPlan:   target: str; source: str; wait_pid: int

parse_version(text) -> tuple                 # "v0.9.2" -> (0, 9, 2)
is_newer(latest, current) -> bool            # semver, tolerant of tags
release_from_json(data) -> ReleaseInfo       # pure, testable
select_asset(assets, platform) -> AssetInfo|None
download_asset(asset, dest, progress=None, cancel=None) -> str
verify_digest(path, expected_hex) -> bool
apply_update(target, wait_pid, timeout=30) -> int
write_batch_fallback(plan) -> str
cleanup_update_temp(temp_dir)
```

- `release_from_json` reads `tag_name`, `html_url`, and each asset's `name`,
  `browser_download_url`, `digest` (`sha256:<hex>` -> hex). Pure.
- `select_asset` maps `sys.platform` (`win32`/`darwin`/`linux`) to
  `socialclip-downloader-windows.exe` / `-macos` / `-linux`. The CLI assets
  (`socialclip-windows.exe`) are never selected.
- `download_asset` streams in chunks, reports `progress(bytes_done, total)`,
  and honors a `cancel` callable (the pattern of `core/download.py`). It refuses
  any URL whose host is not `github.com` or `objects.githubusercontent.com`.
- `verify_digest` hashes the file and compares; on mismatch it deletes the file
  and returns `False`.
- `apply_update` runs inside the newly downloaded exe: it copies
  `sys.executable` over `target` in a retry loop bounded by `timeout` (the
  target stays locked until the old process exits, so the retry *is* the wait),
  relaunches `target` detached, and returns. `wait_pid` is passed for the batch
  fallback, which uses it to wait before replacing. If the copy never succeeds,
  `apply_update` calls `write_batch_fallback` and spawns the `.bat`.
- `cleanup_update_temp` deletes leftover `socialclip-update-*.exe` in the temp
  directory on startup (a running exe cannot delete itself, so the next launch
  does it).

### `workers/update_worker.py` (new)

Mirrors `workers/expand_worker.py`:
- `UpdateCheckWorker` -> `done_signal(ReleaseInfo | None)`, `error_signal(str)`
- `UpdateDownloadWorker` -> `progress_signal(int)`, `done_signal(str path)`,
  `error_signal(str)`

### `ui/update_indicator.py` (new)

`UpdateButton(QtWidgets.QToolButton)`, one state at a time:

| State | Look | Click |
|---|---|---|
| hidden | not shown | - |
| available | download-arrow icon, tooltip "Update vX.Y.Z available" | start download |
| downloading | percent on the button | cancel |
| ready | check icon, tooltip "Update ready to install" | open the install dialog |
| error | muted icon, tooltip with the reason | retry |

The button holds no logic beyond rendering a state and emitting `clicked`.

### `ui/main_window.py`

- A thin header row between the menu bar and the tabs: `addStretch()` then the
  update button, so it sits top-right over the tab area.
- **Help -> Check for updates** (forces a check past the cache).
- Owns the state machine and the workers.

State: `idle -> checking -> (uptodate | available) -> downloading -> ready ->
install -> quit`, with `error` reachable from `checking` and `downloading`.
Cancel from `downloading` returns to `available`; Later from `ready` stays
`ready`. Cache in `QSettings`: `update/last_check` (ISO time) and
`update/latest_tag`. Startup check is skipped when `last_check` is under 24h old.

### `ui/dialogs.py`

`show_update_ready(parent, version)` -> bool: "vX.Y.Z downloaded and verified.
Install and restart now?" with **Install and restart** / **Later**.

On **Install and restart**, `MainWindow` spawns the downloaded exe detached with
the apply flag and quits:

```python
subprocess.Popen(
    [download_path, "--apply-update", "--target", sys.executable,
     "--wait-pid", str(os.getpid())],
    creationflags=DETACHED_PROCESS,   # Windows
    close_fds=True,
)
QtWidgets.QApplication.quit()
```

The downloaded exe then performs `apply_update`, so the file being replaced is
never the file doing the replacing.

### `socialclip_downloader.py`

An early branch in `main()`, before any Qt is constructed:

```python
if "--apply-update" in sys.argv:
    from core.updater import apply_update
    return apply_update(target=..., wait_pid=...)
```

## Platform behaviour

| Platform | Check | Indicator | Click |
|---|---|---|---|
| Windows, frozen | yes | shown when newer | download, verify, install, restart |
| macOS / Linux, frozen | yes | shown when newer | open the release page |
| Any, source run | yes | shown when newer | open the release page |

## Security

- HTTPS only; the asset host must be `github.com` or
  `objects.githubusercontent.com`, checked before the download.
- SHA-256 verified against the release API digest before any install.
- No install without an explicit click in the install dialog.
- `--apply-update` is an internal flag; it only copies an already-verified file
  over `--target`, so invoking it by hand affects only the caller's own files.

## Testing

`tests/test_updater.py`:
- `parse_version` / `is_newer`: equal, older, newer, `v` prefix, short tags,
  non-numeric.
- `release_from_json`: full payload, missing digest, missing assets, odd tags.
- `select_asset`: windows/macos/linux, and `None` when absent.
- `verify_digest`: temp file, match and mismatch (mismatch deletes).

No tests for the network, the `QThread`s, the Qt UI, or the real file swap;
those are verified by hand on Windows, matching the repo's treatment of network
and Qt code.

## Risks

1. **Unsigned builds trigger SmartScreen** on the new exe's first run. Known
   limit; free OSS signing later.
2. **The swap can fail** (permissions, antivirus). The batch fallback covers it,
   but a swap that fails both ways leaves the old exe in place and the update
   unapplied; the button stays `ready` so it can be retried.
3. **A malicious release** is only as trustworthy as the GitHub account and the
   digest GitHub computed. Digest verification protects against transit and CDN
   tampering, not a compromised release.
4. **The daily cache** delays a startup check by up to 24h; the manual menu item
   bypasses it.
5. **Local build names differ** (`build.bat` produces `SocialClip
   Downloader.exe`). The updater replaces whatever `sys.executable` is, so a
   locally built exe updates to the released name only after the swap; this is
   acceptable and worth a note in the report.
