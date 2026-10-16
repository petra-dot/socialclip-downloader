# Next Session - 2026-10-17

Status: planned
Written: 2026-10-16, after the v0.10.0 release.

Two items, in this order. Item 1 is small and self-contained; item 2 is a
design task and should start with the brainstorming skill.

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

## Item 1 - Fix the cookie resolution bug

**Reported by the user, still open.** The Cookies dialog (`File -> Cookies`)
lists the cookie files it found, but the **Cookies file** field on the Download
and Queue tabs does not show the detection, so the user has to set it by hand.

Three real defects, diagnosed:

1. **The Queue tab never auto-detects.** `ui/batch_tab.py` has no
   `get_cookie_path` call at all. Its field starts from the shared
   `cookies_file_ref` or `settings("batch/cookies")`.
2. **The download core never resolves cookies itself.** `core/download.py`
   does not call `get_cookie_path`; only `cli.py` does
   (`cookies or get_cookie_path(url)`). So in the GUI a per-platform cookie file
   is used **only if the field already holds the path**. A Queue job with an
   empty field gets no cookies even though `youtube_cookies.txt` sits in the
   data directory.
3. **The shared path is one global string.** Queue a YouTube URL, then a Douyin
   URL: the second reuses YouTube's file, because the auto-set only fires when
   the path is empty.

**Intended fix (root cause):** resolve cookies **per-URL inside
`core.download.download_one`**, the way `cli.py` does, so the field becomes an
*override* rather than the only source. Then both tabs get correct cookies, the
mixed-platform case is fixed, and the UI can show what was resolved.

Also worth doing while there:
- Show the resolved file in both tabs when the field is empty (e.g. as
  placeholder/hint text), so the detection is visible instead of manual.
- A pure helper for "which cookie file applies to this URL, given an optional
  override" so it can be unit-tested (the repo's tests cover pure logic only).

**Tests:** the repo's suite is pure-logic only. Add tests for the override-vs-
detected precedence helper. `tests/test_cookies.py` and
`tests/test_core_download.py` are the natural homes.

**Do not** re-add keyword lists to workers; route error copy through
`sites.errors.classify_error` per `AGENTS.md`.

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
