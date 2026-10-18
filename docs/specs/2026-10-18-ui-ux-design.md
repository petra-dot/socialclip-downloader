# UI/UX Refresh - Design

Status: draft - awaiting review
Date: 2026-10-18
Applies to: `ui/style.py`, `ui/main_window.py`, `ui/single_tab.py`,
`ui/batch_tab.py`, `ui/convert_tab.py`, `ui/history_tab.py`, `ui/dialogs.py`,
`ui/update_indicator.py`, `utils/system_theme.py` (new), `tests/`

## Problem

The app works and the engine is genuinely good, but the interface is unstyled
default Qt and reads as bland. There is no color system, no accent, and the
theming is inconsistent. A 2026-10-15 critique scored it 21/40, but most of that
critique is now stale: the code shipped a lot of UX work since (v0.10.1 through
v0.12.2). What is actually still open:

1. **No visual system.** `ui/style.py` holds only per-theme state colors and a
   palette. Every widget uses default Qt chrome; nothing carries an accent; no
   spacing, radius, or type scale exists. This is the "bland".
2. **Theme inconsistency.** Dark forces the Fusion style while Default/Light use
   the native style, so widget shapes change when the theme changes.
3. **Vocabulary drift.** The same concept is "Format:" (Download), "Output:"
   (Queue), and "Convert to:" (Convert); format labels differ between
   `utils/file_utils.OUTPUT_FORMATS` and the `core/formats.py` registry.
4. **The Download result is a thin line**, not a panel: no codecs, resolution,
   size, or a clear "editor-ready" moment, and the primary action has no visual
   priority.
5. **The Queue has no multi-select or bulk action.** The options block under the
   table reads as if it applies to the rows; Start only *logs* a stale-options
   warning instead of asking.
6. **Convert is a single column** that does not match Download, its button says
   "Convert Selected File" with no selection list, and the log owns the space.
7. **The activity log occupies 120 px by default** on Download and Convert.
8. **Accessibility is partial**: `setBuddy` is used in some places only, result
   and progress changes are not announced, and dark disabled text is ~4.2:1.

Already fixed and therefore **out of scope**: the Resolution combo is disabled
when inert (`single_tab._sync_resolution_state`); the Download button becomes
Cancel while running; the result line is styled by state; the log is capped; the
Queue header says "Video"; queue rows show their baked options in Detail.

## Goal

Make the app look deliberate and native, with one accent, consistent vocabulary,
and a result that shows the editor-safe promise. Fix the gaps above without
changing what any feature does.

## Decisions (locked during the design pass)

- **Base:** native / OS-consistent. System font, native controls, native
  density.
- **Accent:** one signature accent, teal `#0d7d75`, used for the primary action,
  the active tab, and the editor-ready result. It is deliberately clear of every
  state color.
- **Theming:** Fusion for all three modes, with hand-tuned Light and Dark
  palettes that look like the OS; Default follows the OS light/dark setting.
- **Download:** form on the left, a persistent result panel on the right.
- **Queue:** baked options shown in the Detail cell; multi-select with a bulk
  bar.
- **Convert:** two-pane, matching Download.
- **History:** structure unchanged; adopt the tokens only.

## Non-goals

- No new download features, no changes to `core/` logic, no new dependencies.
- No thumbnails in Queue/History (unchanged decision).
- No file deletion from the Queue; file deletion stays in the History tab.
- No drag-and-drop, no translations, no in-app player.

## A. Token layer (`ui/style.py`)

Add a semantic, theme-aware token layer; widgets read tokens, never literal hex.

- **Surfaces:** `window`, `base`, `panel` (a second neutral for panels and
  toolbars), `border`, `divider`.
- **Text:** `text`, `text_secondary`, `text_muted`.
- **Accent:** `accent`, `accent_hover`, `accent_pressed`, `accent_subtle`
  (a tint for the selected row and the editor-ready card).
- **State:** `ok`, `error`, `busy`, `warn`, `muted`, each with a `*_tint` for
  chips.
- **Accessors:** `token(name)` returns the current theme's value;
  `state_color(kind)` becomes a thin alias of `token(kind)` so existing callers
  (`dialogs`, `batch_tab`, `history_tab`) keep working unchanged.
- **Scales:** `SPACING` (`xs` 4, `sm` 6, `md` 8, `lg` 12, `xl` 16, `xxl` 24) with
  `space(name)`; `RADIUS` (`control` 4, `panel` 6, `chip` 8).
- **Type:** keep `make_heading`; add `make_title` (+2), `make_caption`
  (small/muted), and `mono_font()` (used only for codecs, paths, and the log —
  real data, not decoration).
- **Chips:** one `make_chip(text, tone)` factory returning a QWidget whose child
  QLabel is exposed as `.label`; tones `ok`, `error`, `warn`, `busy`, `muted`,
  `neutral`. It replaces `history_tab._chip` and the inline chip styling in
  `dialogs.show_doctor`, so Queue, History, and Health share one chip.
- **Buttons:** `primary_button_style()` (accent fill) and keep
  `danger_text_style()` (error text, muted when disabled).
- **Motion:** 150-200 ms, state changes only. No load choreography.

## B. Theming (`ui/style.py`, `utils/system_theme.py`)

- `apply_theme(app, mode)` always sets the Fusion style, then applies a palette
  built from the token dict. Light and Dark palettes are hand-tuned to read like
  the OS. `THEMES` and `THEME_LABELS` stay `("system", "light", "dark")` /
  Default, Light, Dark.
- Default resolves through `utils.system_theme.detect()`: `"dark"` or `"light"`,
  never raising. Windows reads `HKCU\...\Themes\Personalize\AppsUseLightTheme`
  (via `winreg`, imported inside the function); macOS runs
  `defaults read -g AppleInterfaceStyle`; Linux runs
  `gsettings get org.gnome.desktop.interface color-scheme`; anything else is
  `"light"`. The subprocess runner is injectable for tests.
- Fix the dark disabled-text contrast to at least 4.5:1.
- The active tab gets a 2 px accent underline and accent text, applied from the
  theme so it recolors on a theme change.

## C. Shell (`ui/main_window.py`)

- Remove the standalone header row; move the update button into the tab bar with
  `self.tabs.setCornerWidget(self.update_button, QtCore.Qt.TopRightCorner)`.
- Content margins and spacing come from the `SPACING` scale.
- `_refresh_theme_colors` additionally refreshes the Download and Convert result
  panels (they hold literal colors) alongside the existing Queue/History calls.

## D. Download tab (`ui/single_tab.py`)

Two panes: the form on the left, a persistent result panel on the right.

- **Form:** URL + Fetch; one **Output** row (format combo labelled from the
  registry - `MP4 (H.264 + AAC)` / `MP3 (audio)` - plus a resolution combo); the
  save folder; the existing **Advanced** disclosure (filename options,
  subtitles, clip, cookies); **Download** as the only primary action, becoming
  **Cancel** while running (already the case).
- **Resolution without a lie:** the combo lists `Best (no re-encode)` plus
  `RESOLUTIONS`. Choosing `Best` means no re-encode; choosing a number means
  convert. This replaces the separate "Convert to chosen resolution" checkbox
  and the disable-when-inert guard, and keeps the same capability. Presets keep
  storing `convert` + `resolution`; the UI derives one from the other.
- **Result panel** (right, `panel` token): empty state ("Downloads appear here"),
  running state (percent, speed, ETA, downloaded/total), success state (filename,
  codecs "H.264 + AAC", resolution, size, duration, an "editor-ready for CapCut /
  Premiere / Resolve" line, Play, Open folder), and error state (the classified
  message plus a recovery hint). The panel is filled from a new
  `DownloadWorker.result_signal(object)` carrying the `DownloadResult` the worker
  already builds; no new probing.
- **Activity:** the log collapses to zero height by default and expands only when
  "Activity" is toggled.

## E. Queue tab (`ui/batch_tab.py`)

- Rows stay `Video | Status | Detail`. Status becomes a `make_chip` chip (Done
  `ok`, Failed `error`, Running `busy`, Pending `muted`, Cancelled/Skipped
  `muted`).
- The Detail cell carries the truth: baked options for pending
  (`job_options_summary` + "queued"), live progress for running, filename for
  done, the classified error for failed.
- **Multi-select:** `ExtendedSelection`; selecting rows shows a bulk bar above
  the table reading "N selected" with **Retry**, **Remove**, and
  **Clear finished**. The bar shows a count, not a combined size: the queue
  model stores no file sizes (that stays in History, which does). The bar acts
  on queue entries only; deleting files stays in History. The right-click menu is
  unchanged.
- **Options block:** relabelled "Options for new items", and **Start** asks
  "N pending items use different options. Apply the current options and start?"
  when pending jobs differ, instead of only logging it.
- Header stays "Video".

## F. Convert tab (`ui/convert_tab.py`)

- Two panes matching Download: form left (File + Select, Output, Resolution,
  Streams, **Convert** primary), result panel right (output filename, target
  format, size, editor-ready, Play, Open folder).
- `Convert` is disabled until the file field names an existing file.
- The log collapses to zero height by default behind "Activity".
- Keep `_update_conv_controls` (resolution disabled for audio, GIF, and
  copy-streams) and the existing worker.

## G. History tab (`ui/history_tab.py`)

Structure unchanged. Adopt the tokens and `make_chip`; the active tab gets the
accent underline and the selected row uses `accent_subtle`. No behavior change.

## H. Dialogs (`ui/dialogs.py`)

Tokens, shared `make_chip`, and `primary_button_style` on the primary button of
each dialog (Welcome, Health, Cookies, Edit job, Manage presets, Expand,
Update ready). Health keeps its `state_chip` text/tone mapping but renders
through `make_chip`.

## I. Accessibility

- Bind the remaining labels with `setBuddy`.
- Give the result and progress labels accessible names and post an accessibility
  event when their text changes, so a screen reader hears the outcome.
- Keyboard path for cancel is the focused Download button (already works); verify
  it in the smoke pass.
- Dark disabled text at or above 4.5:1; the result panel is reachable by Tab.

## J. Vocabulary unification

- One label for the concept: **Output** on Download, Queue, and Convert.
- One format vocabulary. The Download tab and the Queue support only two output
  formats (`output_type` MP4/MP3), so their combo shows the registry's labels for
  those two, `MP4 (H.264 + AAC)` and `MP3 (audio)`, not the registry's full list.
  The Convert tab keeps offering the full registry. The Queue's option summary
  and the History detail pane use the same labels, so "MP4" always reads the same
  way. `OUTPUT_FORMATS` still drives the legacy `output_type` path; only the
  displayed text changes.

## K. Testing and verification

Pure logic gets pytest tests; the Qt layer is verified offscreen, as the rest of
the UI is (the suite stays free of GUI tests per the repo convention).

- `tests/test_system_theme.py` (new): `detect()` returns dark/light for each
  platform using an injected runner, and falls back to light on error.
- `tests/test_style_tokens.py` (new): every token key exists in both themes;
  `state_color` aliases `token`; the text, placeholder, and disabled pairs meet
  4.5:1 (a pure contrast helper).
- `tests/test_ui_wiring.py` (extend): chips come from `make_chip`; `THEMES` and
  `THEME_LABELS` are unchanged.
- `tests/verify_ui_offscreen.py` (new, runnable, not collected by pytest):
  constructs each tab offscreen under `QT_QPA_PLATFORM=offscreen` and asserts the
  invariants - resolution combo shows `Best` for audio, the Download button
  becomes Cancel while a worker runs, the Queue bulk bar appears on multi-select
  with the combined size, Convert is disabled with no file, chips render, and the
  result panel shows each of its four states. Screenshots are captured light and
  dark for the vision pass.
- Manual: run the Windows build; open all four tabs in light and dark; download
  one video and one MP3; convert one file.
- Re-run the Impeccable `critique` and `audit` passes after implementation; the
  2026-10-15 critique is superseded (see below).

## Risks

1. **Qt5 stylesheet on Fusion is brittle.** Keep styling palette-first and QSS
   minimal (tab underline, chips, primary/danger buttons). Verify each theme on
   Windows before shipping.
2. **Removing the convert checkbox** changes a familiar control. The `Best`
   option preserves the capability and presets keep their fields; the spec keeps
   the mapping explicit.
3. **`setCornerWidget`** can mis-size the update button; check the tab bar on
   Windows.
4. **Two-pane at the 820 px minimum width** leaves roughly 480 px for the form;
   verify the Output row and the Advanced disclosure still fit.
5. **OS theme detection on Linux is unreliable**; it falls back to light, and
   Light/Dark remain explicit overrides.
6. **Do not regress the shipped History redesign** or the 619 existing tests;
   `state_color`, `THEMES`, `THEME_LABELS`, `apply_theme`'s Fusion string,
   `danger_text_style`, and `make_heading` must keep working.

## Supersedes

`.impeccable/critique/2026-10-15T20-40-39Z__ui.md` is stale: most of its P1s
(resolution lie, missing cancel, unstyled result, log size, queue header) shipped
after it was written. It is kept for the record but no longer describes the app.
