# History Tab Redesign - Design

Status: approved
Date: 2026-10-18
Applies to: `core/download.py`, `core/history.py`, `ui/history_tab.py`,
`sites/cookies.py`, `tests/`

## Problem

The History tab is unusable for all three of its purposes. Two data bugs and a
layout that ignores its own space.

### Data bugs

1. **The recorded title is the raw title, not the file that was saved.** The tab
   shows `Facebook` for every Facebook row, because Facebook returns that generic
   title when a cookie file is sent. The file on disk is
   `26K views - 201 reactions Why Breakups...mp4`. The tab therefore shows a name
   that matches nothing on disk, and every row looks identical.
2. **The platform is shown as the internal key**, `facebook`, instead of the
   display name. `sites/cookies.py` already holds `PLATFORM_NAMES` for this.

### Layout

1. Title is squeezed into the narrowest column while Date and Status have room to
   spare; nothing is sized to its content.
2. A large dead area below the table.
3. No hierarchy: no icon, chip, or colour anywhere. The Queue tab already uses
   `ui/platform_icons.icon_for_url` and state colours, so the two tabs disagree.
4. The action row is split arbitrarily, and the most destructive action
   (`Clear history`) looks like a default button.
5. Status is a bare word with no visual treatment.

## Goal

One tab that serves all three purposes: **find a file to play**, **read a complete
record**, and **manage disk space**.

## Non-goals

- No thumbnails or cover art. yt-dlp supplies no image, and fetching one per row
  is a network cost and a caching problem for no real gain.
- No in-app player: Play still hands the file to the OS (unchanged).
- No new dependency.
- No change to what a history entry stores beyond the title (see A1). The status
  stays derived, never stored.

## A. Data fixes

1. **Record the name the file actually got.** In `core/download.py`, after the
   final rename, set `manifest.title` to the final base name, so the result and
   the history entry name the artifact on disk. `better_base_name` already
   computed that name; use its result rather than the raw `info["title"]`.
2. **Display the platform properly.** Add a display helper (or use the existing
   `PLATFORM_NAMES`) so the table and the filter show `Facebook`. Keep the raw key
   for matching and filtering, so stored entries keep working.
3. Entries already on disk keep their stored title. Only new downloads get the
   corrected name. No migration.

## B. Layout - a split view

- **Summary bar (top).** `12 downloads · 3.4 GB · 2 not found`, plus the action
  buttons on the right. Serves the audit and disk goals at a glance.
- **Table (middle).** Fills the remaining height.
- **Detail pane (bottom).** Shows the selected row: title, URL, path, format,
  resolution, duration, size, source, status, and the probed container and codecs.
  **Details stops being a modal**, and the dead space is used.
- The detail pane updates on selection and clears when nothing is selected.

## C. Row design

- **Platform icon** from `ui/platform_icons.icon_for_url`, matching the Queue tab.
- **Title**: widest column, ellipsised, full text in the detail pane.
- **Format**: a small chip (`MP4` / `MP3`).
- **Size**: right-aligned so the column reads as numbers.
- **Date**: relative inside the last week (`2 days ago`), absolute beyond it.
- **Status**: a colour chip. `OK` green, `Not found` amber, `Deleted by you` grey.
- Row height and padding increased; header stays sticky.

## D. Actions

- **Primary:** `Play`, `Open folder`. Enabled only for `OK` rows.
- **Destructive, visually separated and danger-styled:** `Delete file`,
  `Remove from history`. `Clear history` moves into an overflow menu.
- **Multi-select bulk delete** (the disk goal): selecting rows shows their
  **combined size** in the summary bar, and `Delete file` acts on the whole
  selection. Every destructive action still confirms first, and only paths the
  app recorded are ever touched.
- The right-click menu keeps the same set.

## E. Empty and filtered states

- **No history:** a real message explaining what will appear here, not a blank
  table.
- **Filters match nothing:** `No downloads match`, with a `Clear filters` action.

## F. Testing

Pure logic is tested, the tab is verified offscreen, as the rest of the UI is.

`tests/test_history.py`:
- the platform display helper maps `facebook` to `Facebook` and passes an unknown
  key through unchanged.
- `entry_from_result` uses the name it is given, so a corrected title is stored.

`tests/test_download_history.py`:
- a download whose title was rewritten records the **final base name**, not the
  raw title.

Offscreen verification (isolated `SOCIALCLIP_DATA` and a `petra-dot-test` settings
scope): seeded entries covering a real name, a generic name, a missing file and a
deleted file; assert the platform icon, the chip colours, right-aligned sizes, the
summary totals, multi-select bulk delete, and that the detail pane populates and
probes on demand.

## Risks

1. **Bulk delete is the most dangerous action in the app.** It confirms once for
   the whole selection and names the count and total size, and it only ever
   touches recorded paths. If that still feels too sharp, ship single-row delete
   first.
2. **The detail pane shrinks the table.** A large history shows fewer rows. Accept
   it, or make the pane collapsible if it proves annoying.
3. **Relative dates drift** and a row can say `2 days ago` after a refresh. That is
   fine for scanning; the detail pane shows the exact timestamp.
