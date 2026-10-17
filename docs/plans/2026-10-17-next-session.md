# Next Session - 2026-10-17

Status: items 1 and 3 DONE; item 2 (UI design) still to do
Written: 2026-10-16, after the v0.10.0 release. Updated: items 1 and 3 fixed.

**Remaining work is item 2 only: redesign the Doctor / Health interface.**
Start it with the brainstorming skill.

## Done in this pass

- **Item 1 - cookie resolution: FIXED** (`ef6a2da`).
  Root cause: the download core never resolved cookies per-URL (only the CLI
  did), the Queue tab never auto-detected at all, and the shared path was one
  global string, so a mixed-platform queue reused the first URL's file.
  Fix: `sites.cookies.resolve_cookie_file(url, override)` (override wins, else
  the platform's own file) called at the top of `core.download.download_one`,
  so both tabs are fixed in one place; the tabs now show the detection as
  placeholder text instead of a sticky fill. Verified live: a YouTube URL
  resolves `www.youtube.com_cookies.txt` and a Douyin URL
  `www.douyin.com_cookies.txt` with no manual step.
- **Item 3 - queue downloads named after the site: FIXED** (`69430e8`).
  Root cause (counter-intuitive, proven live): **Facebook returns the generic
  title `Facebook` when a cookie file is sent**, and the real title only
  without cookies. `%(title)s` was therefore literally `Facebook`, and the app
  accepted it. The Download tab had the same bug - it looked fine only because
  the user tested YouTube URLs there.
  Fix: `utils.file_utils.is_generic_title` plus
  `core.download.better_base_name`, applied in the shared download core so both
  tabs benefit. Order: the real title (re-fetched without cookies when the site
  degraded it) -> `uploader_id` -> `id`. Verified live: the same URL now yields
  `13K views ... Can Touching Your Partner Reduce Stress ... #psychologyfacts`.
- Baseline now: `python -m pytest -q` -> **536 passing**; lint gate -> **0**.

## Context to resume from

- Branch `main`, clean, level with `origin/main` (`2711653`).
- **v0.10.0 is released** (tag + GitHub Release, all 3 platforms built).
  `__version__` is `0.10.0` in `core/version.py`.
- Baseline: `python -m pytest -q` -> **521 passing**;
  `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`
  -> **0**.
- Writable state lives in the **per-user data directory** (`core/paths.py`),
  not next to the app. On this machine:
  `%LOCALAPPDATA%\SocialClip Downloader`. `SOCIALCLIP_DATA` overrides it.
- **CI gotcha:** `python-package.yml` has a "Check version matches the latest
  tag" step that runs on every push to `main` and requires `__version__` to
  equal the **latest existing tag**. So a version bump cannot be pushed to
  `main` before its tag exists. Order: tag and `main` together, or tag first.
- **Offscreen smoke gotcha:** constructing `MainWindow()` under
  `QT_QPA_PLATFORM=offscreen` with a bare `QApplication([])` segfaults inside
  `show_welcome` (no org/app name, so `first_run_done` never persists and the
  first-run dialog opens). Set `setOrganizationName("petra-dot")`,
  `setApplicationName("SocialClip Downloader")`, and
  `QSettings().setValue("first_run_done", True)` first.

---

## Item 1 - Fix the cookie resolution bug  [DONE - `ef6a2da`, `69430e8` was item 3]

**Resolved.** See "Done in this pass" above for the root cause and the fix.
Kept here for the record of what the three defects were:

1. **The Queue tab never auto-detected.** `ui/batch_tab.py` had no
   `get_cookie_path` call at all.
2. **The download core never resolved cookies itself.** Only `cli.py` did, so a
   per-platform cookie file was used only if the UI field already held the path.
3. **The shared path was one global string**, so a YouTube job followed by a
   Douyin job reused YouTube's file.

---

## Item 2 - Redesign the Doctor / Health interface

**User feedback: "the doctor interface text everything looks very ugly there.
that need a good UI design."**

Current state: `ui/dialogs.py:show_doctor()` builds a monospaced text blob with
`doctor_lines(report, components)` and drops it in a read-only `QTextEdit`,
with a button row underneath. It is plain text pretending to be an interface.

`doctor_lines` is **pure and unit-tested** (`tests/test_ui_wiring.py`), so keep
it (or keep an equivalent pure builder) rather than deleting the tested logic.

Design goals to explore (not yet decided):
- A proper component list/table: name, version, state, and an action per row,
  instead of a wall of text.
- Real status affordances: colour or an icon per state
  (`ok` / `missing` / `stale` / `broken` / `unknown`), using the theme's state
  colours (the app already has per-theme state colours from the UI-polish work).
- The cookies / network / ffmpeg detail as a secondary, collapsible section
  rather than the primary content.
- **Move the probe off the GUI thread.** Today `show_doctor` runs
  `run_checks()` (which does a `socket.create_connection` with a 3 s timeout)
  and `check_all()` (which spawns `ffmpeg -version`) **synchronously**, so
  opening Health can freeze the window for ~3 s. A parked minor already flags
  this; the redesign is the right time to fix it, reusing
  `workers/maintenance_worker.MaintenanceCheckWorker`.

Process: this is creative work, so **start with the brainstorming skill**
(explore intent, then a design), then a spec in `docs/specs/`, then a plan in
`docs/plans/`. The `impeccable` skill is a good fit for the design pass; an
earlier critique of `ui/` scored 21/40 with a snapshot at
`.impeccable/critique/2026-10-15T20-40-39Z__ui.md`.

Constraints that still bind: `core/` stays Qt-free; `doctor_lines`-style
formatting stays pure and testable; the offscreen smoke gotcha above applies to
any GUI verification.

---

## Parked minors from the v0.10.0 work (triage when convenient)

Non-blocking, from the per-task reviews. Full list with reasoning was in
`.superpowers/sdd/2026-10-16-maintenance/progress.md` (untracked scratch; may
have been deleted). The notable ones:

- `install_ytdlp`'s `_swap` does two non-atomic renames: if the second fails,
  `dest` is left absent and the old copy sits at `.prev`. The window is tiny and
  the working copy is never deleted.
- The bad-digest test proves `dest` was not created, not that a *pre-existing*
  working copy survives.
- `data_dir_writable()` can leave a `.write-test` file behind if `os.remove`
  fails; `data_dir()`'s `OSError` fallback and `data_dir_writable()` are
  untested.
- `check_all`'s "never raises" contract is untested; the stale-ytdlp test spawns
  the host's `ffmpeg -version`.
- `utils/ffmpeg._managed_bin_dir` and `utils/ytdlp._managed_bin` are the same
  helper twice.
- `install_ffmpeg` swaps `ffmpeg` and `ffprobe` individually (both come from one
  archive, so a crash between them leaves a mixed but valid pair).
- **macOS has no verified automatic ffmpeg source** (BtbN publishes no macOS
  build), so `install_ffmpeg` refuses there and points at Homebrew. yt-dlp and
  deno still repair automatically. This is by design and documented.
- `release.yml` bundles `ffmpeg` only, so `ffprobe` falls back to `PATH` in a
  frozen build; the maintenance installer supplies both.
- `_managed_runtime` has no executability check, so on POSIX a stray
  non-executable file named `deno` is returned as the runtime.
