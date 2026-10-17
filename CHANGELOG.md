# Changelog

## v0.12.1 - 2026-10-18

### Fixed
- **The History detail pane froze the window on the first click of a row.** The
  container and codec probe ran `ffprobe` on the UI thread, so the first click on
  each downloaded file stalled while the process started — worst in the frozen
  Windows build, whose bundle ships `ffmpeg` but no `ffprobe` and so falls back
  to `PATH`. The probe now runs on a worker thread: the pane paints at once, the
  codec rows read `…`, and they fill in when the probe answers. Results are
  cached per file, so every later click is instant.

## v0.12.0 - 2026-10-18

### Added
- **History detail pane.** The selected row's full record — title, URL, path,
  format, resolution, duration, size, source, status, and the file's real
  container and codecs, probed on demand — is shown in a pane below the table,
  replacing the **Details** dialog. It updates as you move the selection and
  clears when nothing is selected.
- **Summary bar.** The top of the tab now reads `12 downloads · 3.4 GB · 2 not
  found`, so the audit and disk-space picture is one glance, with the action
  buttons beside it.
- **Multi-select and bulk delete.** Select several rows and the summary shows
  their combined size; **Delete file** acts on the whole selection after a single
  confirmation that names the count and total size. Only recorded paths are ever
  touched.
- **Relative dates.** A row inside the last week reads `2 days ago`; older rows
  show the exact date, and the detail pane always shows the full timestamp.
- **Empty states.** No history shows what will appear here; a filter that
  matches nothing shows `No downloads match` with a **Clear filters** action.

### Changed
- **History rows carry the same visual language as the Queue.** Each row has the
  platform badge, the platform's display name (`Facebook`, not `facebook`), a
  format chip (`MP4` / `MP3`), a right-aligned size, and a colour status chip
  (`OK` green, `Not found` amber, `Deleted by you` grey), with taller rows.
- **Destructive actions are grouped and marked.** `Delete file` and `Remove from
  history` are separated from the primary actions and shown in the error colour;
  `Clear history` moved into a **More** overflow menu. The right-click menu keeps
  the same set.

### Fixed
- **The history named the site, not the file.** Every Facebook row read
  `Facebook`, because that is the title the site returns when cookies are sent;
  the file on disk is named after the real title. The recorded name is now the
  base name of the file that was actually saved, so the row matches the artifact.
  Entries already on disk keep their stored title; there is no migration.
- **The platform showed its internal key** (`facebook`) instead of its display
  name. The table and the platform filter now show the display name while the raw
  key is still used for matching and filtering, so stored entries keep working.

## v0.11.0 - 2026-10-18

### Added
- **Download History.** A fourth tab lists every completed download, from the
  Download tab, the Queue, and the CLI, recorded in `history.json` in the data
  directory. Sort by any column, search by title, filter by platform or format.
- **Play and Details.** Play hands the file to the operating system's default
  application; the app bundles no media player. Details shows what was recorded
  at download time and probes the file on demand for its real container and
  codecs.
- **Honest status.** The status is checked against the disk whenever the tab is
  opened, so a file you moved or deleted reads as **Not found**.
- **Delete or forget.** Delete file removes the file and keeps the entry marked
  **Deleted by you**; Remove from history drops the entry and leaves the file
  alone. Both confirm first, and only paths the app recorded are ever touched.

### Fixed
- **Two downloads with the same title could collide and one failed.** Facebook
  returns the generic title `Facebook` when a cookie file is sent, so two such
  videos downloaded at the same time shared one output path and the second died
  inside yt-dlp's converter with `[WinError 183] Cannot create a file when that
  file already exists`. The Queue and the CLI now put the video id in the output
  template (`%(title)s [%(id)s].%(ext)s`), so every path is unique per video, and
  the id is stripped back out for the name on disk. The Download tab already
  built a unique base and was not affected.

## v0.10.1 - 2026-10-18

### Fixed
- **Downloads were named after the site instead of the video.** Facebook returns
  the generic title `Facebook` when a cookie file is sent, and the real title
  only without cookies, so files landed as `Facebook.mp3`. A title that is
  empty or is just the site's own name is now treated as unusable: the real
  title is re-fetched without cookies, and failing that the uploader and video
  id are used. This affected the Download tab too, not only the Queue.
- **Cookies are now resolved per URL in the download core.** Previously only the
  CLI resolved a per-platform cookie file, so a GUI download used one only if
  the field already held the path, and the Queue never auto-detected at all. A
  YouTube job followed by a Douyin job also reused the first URL's file.
- **A manual cookie file is scoped to the platform its own filename names**, so
  a YouTube cookie file is never sent to Douyin or to an unrelated site. A file
  whose name says nothing about a platform is still applied to every download.
- **The browser cookie choice is lazy.** The first download attempt sends no
  browser cookies; only a failure that looks like an authentication demand
  retries **once** with them. Sending unnecessary cookies is harmful, not just
  noise: cookies to Facebook degraded the title (see above).
- **The cookie box now shows and follows the per-URL file**, updating when the
  URL changes. **Clear** now forgets the stored path as well as the visible
  text, **Browse** opens the folder the cookie files live in, and the Queue tab
  gained the **Clear** button the Download tab already had.
- **A static "is this URL supported?" check was removed.** It accepted a URL
  only when a site-specific extractor claimed it and excluded yt-dlp's generic
  extractor, which wrongly rejected real, downloadable links (for example a
  Facebook `share/v/` URL, which only the generic extractor claims before
  following a redirect). Support cannot be decided without trying, so any
  URL-shaped input is accepted again and yt-dlp decides.
- **An unsupported link now reports a friendly message** ("That link is not a
  video yt-dlp can download from.") instead of the raw
  `ERROR: Unsupported URL: ...` text.

### Changed
- **The Health view is a status dashboard.** It was a wall of monospaced text
  that also froze the window for up to three seconds, because it ran the network
  probe and `ffmpeg -version` on the GUI thread. It now shows a tone-coloured
  headline, one row per component with a state chip, version, and a **Repair**
  button where one is needed, with the raw report behind a collapsed
  **Details** pane. A worker does the probing, so the dialog opens instantly.

## v0.10.0 - 2026-10-16

### Changed
- **Writable state moved out of the app directory** into the per-user data
  directory, so an install under `Program Files`, `/usr/local/bin`, or a
  quarantined macOS download can still save cookies and the queue. Any legacy
  files next to the app are copied into the data directory once on first run
  (copied, never moved; an existing file is never overwritten).
  `SOCIALCLIP_QUEUE` still overrides the queue file only.
- **The app version moved to `core/version.py`** (`socialclip_downloader`
  re-exports it), so the version is importable without pulling in Qt.

### Fixed
- **YouTube downloads failing with HTTP 403.** yt-dlp's Python API does not read
  your yt-dlp config file and defaults to deno as its only JavaScript runtime,
  so a machine with node but no deno extracted YouTube without a runtime and
  YouTube rejected the media URLs. The app now detects an installed runtime
  (deno, node, bun, quickjs) and passes it explicitly.
- The **Doctor** report now shows the JavaScript runtime it found and the
  installed yt-dlp version with its age, flagging it when it is over 90 days
  old (doctor schema `1.2`). A stale yt-dlp is also noted once in the activity
  log at startup.
- **MP3 audio with a stream copy always failed.** The conversion plan read a
  global audio codec instead of the target format's, so it built `-c:a copy
  -f mp3` for an MP3 target and ffmpeg refused it; the plan now consults the
  target's own remux allow-list.
- **A GUI-saved "Audio (MP3)" preset made the CLI download video.** The GUI
  stored the human label and the CLI compared it to `mp3`; both sides now map
  through one helper.
- **The queue silently dropped jobs it could not read.** An unknown option key,
  or a job from an older schema, was discarded on load; unknown keys are now
  ignored while the job is kept.
- **Thumbnail decoding ran on the worker thread.** `QPixmap` may only be built
  on the GUI thread; the worker now decodes to a `QImage` and the slot turns it
  into the pixmap.
- **A failed ffmpeg run left its partial output behind.** The half-written file
  could be mistaken for a good download; it is now removed on failure, matching
  the converter.
- **`--convert` could not be turned off for a preset.** The CLI gains
  `--no-convert`, so an explicit flag beats the preset, which beats the default.
- **A preset rename allowed a duplicate name, and a clip time like `1:90` was
  accepted.** Renaming onto an existing name is rejected, and a non-leading time
  component over 59 is now invalid.
- The CLI archive follows `SOCIALCLIP_QUEUE` so it moves with the queue, the
  updater refuses a non-HTTPS asset URL, and the Queue's option, retry, and edit
  actions refuse to run while the queue is running.

### Added
- **Maintenance and self-repair.** The app now checks its components (yt-dlp,
  ffmpeg, and the JavaScript runtime YouTube needs) at most once a day and
  repairs a missing, stale, or broken one from a verified download, so a frozen
  build keeps working without a new release. New `core/maintenance.py` holds the
  component model, the local checks, and the SHA-256-verified installers for
  yt-dlp, ffmpeg, and deno; `workers/maintenance_worker.py` runs the checks and
  repairs off the UI thread. A new **Health** view (**Help -> Health**) lists
  every component with its version and state and offers **Repair** and **Open
  data folder**, and the CLI gains `socialclip repair` (with `--dry-run`).
  macOS has no verified automatic ffmpeg source, so `repair` refuses to install
  ffmpeg there and points at Homebrew; yt-dlp and deno still repair
  automatically.
- **Per-user data directory.** New `core/paths.py` resolves one writable
  location for cookies, `queue.json`, `presets.json`, `archive.txt`, and the
  managed components (`%LOCALAPPDATA%\SocialClip Downloader`,
  `~/Library/Application Support/SocialClip Downloader`, or
  `~/.local/share/socialclip`), with **File -> Open data folder** to reveal it.
  `SOCIALCLIP_DATA` moves the whole directory.
- **A bundled JavaScript runtime.** The release builds now ship deno, so
  YouTube works on a machine with no runtime of its own. `find_js_runtime`
  looks on `PATH`, then in the managed data directory, then in the bundle.
- **Browser cookie source:** open **File -> Cookies** and pick one installed
  browser (Chrome, Firefox, Edge, Brave, and others); the app passes it to
  yt-dlp as `cookiesfrombrowser`, and the one choice applies to every download.
  A per-platform cookie file still wins over it. The CLI gains
  `download --cookies-from-browser` and `queue add --cookies-from-browser`
- **Skip already-downloaded videos:** the Queue can skip a video it has already
  saved. Tick **Skip already downloaded** on the Queue tab, or pass
  `queue run --archive`, and each finished video is recorded in `archive.txt`
  beside `queue.json` (yt-dlp's `download_archive`). A skipped job ends in a new
  terminal `skipped` state. **Clear archive** (or `queue archive --clear`)
  resets it. Off by default, and the single Download tab is unaffected. New
  `core/archive.py` holds the archive path and clear helpers
- **Parallel queue downloads:** the Queue runs up to 3 downloads at once by
  default, adjustable 1-8 with **Downloads at once** (or `queue run --jobs N`).
  Each running row shows its own percent, a running row can be cancelled on its
  own, and **Cancel all** stops the batch. `core/queue.py` stays thread-free
  with new pure `claim_next()`/`apply_result()` primitives; the pool lives in
  `workers/queue_worker.py` and `cli.py`
- **In-app updater**: the app checks GitHub Releases at most once a day
  (`Help -> Check for updates` forces it) and shows a top-right indicator when a
  newer release exists. On Windows it downloads the new build, verifies its
  SHA-256 digest, and self-installs with a restart via `--apply-update`;
  macOS/Linux and source runs open the release page
- **Collection expansion:** paste a playlist, channel, or profile URL and the
  Queue offers to add its videos: preview the list, confirm, then enqueue them.
  Duplicates already in the queue are skipped and the batch is capped. Listing
  is reliable on YouTube and best-effort elsewhere
- `socialclip queue add --expand`: expand a collection URL into its videos
  before enqueuing; the single-video path is unchanged without the flag
- New modules: `sites/collections.py` (URL classification),
  `core/collections.py` (pure listing and dedupe helpers),
  `workers/expand_worker.py` (Qt expansion thread)
- **Clip downloads:** save only a time range from a video. In the Download tab,
  tick **Clip** to reveal a **Start** plus either an **End** or a **Duration**;
  the default cut is lossless (stream copy) with an **Exact cut** option that
  re-encodes at the precise frame. The CLI gains `--start`/`--end`/`--duration`/
  `--exact-cut` on `download`. Times accept `90`, `1:30`, or `00:01:30`. The
  primary path asks yt-dlp for the section directly and falls back to a full
  download cut with ffmpeg. New `core/clip.py` holds the pure parsing and
  ffmpeg-argument helpers
- **Download presets:** save the whole download setup (output format,
  resolution, convert toggle, filename options, save folder, cookies) under a
  name and recall it from the Download and Queue tabs. Editor-first built-ins
  (**Editor-safe 1080p**, **Editor-safe 720p**, **Audio only (MP3)**,
  **Original quality**, **Archive master**) live in code; your own presets are
  stored in `presets.json` in the app directory, next to `queue.json`. The CLI
  gains `download --preset NAME` (explicit flags win over the preset). New
  `core/presets.py` holds the pure model and store, and a new
  `ui.dialogs.manage_presets` dialog renames and deletes user presets
- **Subtitle downloads:** choose **Off**, **Sidecar**, **Embed**, or **Both** on
  the Download and Queue tabs. Sidecars are written next to the video as
  `<base>.<lang>.srt`; every language the source offers is fetched, and a
  human-made track and an auto-generated track for the same language are kept as
  separate files (`<base>.<lang>.srt` vs `<base>.<lang>.auto.srt`). **Embed**
  muxes the tracks into the video, and a failed embed still keeps the sidecars.
  The CLI gains `download --subtitles off|sidecar|embed|both` (default `off`).
  New `core/subtitles.py` selects the tracks and writes or embeds them
- **Queue retry and per-job editing:** re-queue failed jobs from the Queue tab
  (**Retry failed**, or right-click a row and choose **Retry**) or the CLI
  `queue retry`. Right-click a pending job and choose **Edit options...** to
  replace its format, resolution, folder, subtitles, and cookie file before it
  runs. Retry touches failed jobs only; edit applies to pending jobs only
- **Download stats:** the progress display now shows speed, an ETA, and
  downloaded/total size alongside the percentage, on the Download tab (a label
  under the bar) and in each queue row's Detail cell. New `core/progress.py`
  holds the `Progress` payload and the formatters that render it

## v0.9.2 - 2026-10-11
### Added
- Menu bar: **File** (Paste URL, Open download folder, Quit), **View** (Theme),
  and **Help** (Doctor, About), with shortcuts `Ctrl+V`, `Ctrl+O`, `Ctrl+Q`, and
  `Ctrl+1/2/3` to switch tabs
- **Theme** selection (Default / Light / Dark), remembered between runs
- Remove a queue row: right-click it, or highlight it and press `Delete` (the
  context menu was mouse-only)
- The Queue tab shows guidance when empty instead of a blank table
- Platform badge beside each queued URL
- **Open folder** on the Convert tab reveals the converted file
- `Enter` in the URL field fetches, the desktop convention

### Changed
- Interactive inputs and the queue table carry accessible names; section
  headings scale with the system font instead of a fixed pixel size
- Recoverable mistakes (empty URL, no file, nothing to start) show an inline
  hint instead of a modal dialog
- Activity logs grow with the window instead of a fixed height

### Fixed
- **Dark theme was unreadable on Windows.** The palette was applied under the
  native style, which ignores most of a custom `QPalette`, leaving light text
  on light backgrounds; dark now applies under the Fusion style
- **Thumbnail preview never loaded.** The pixmap was built from
  `QtWidgets.QPixmap`, which does not exist; the exception was swallowed and
  the label read "Failed to load"
- **Cookie lookup and `queue.json` used the launch directory** (`os.getcwd()`),
  so auto-detection broke when the app was started from elsewhere; both now
  resolve against the app directory, with the working directory as a fallback
- The first-run welcome froze the window for seconds: it ran a network probe
  and an `ffmpeg -version` subprocess on the UI thread; it now checks only
  whether ffmpeg exists
- gitleaks flagged its own cookie test fixture; the rule is scoped to `tests/`

## v0.9.1 - 2026-10-03
### Fixed
- **Open folder** opened Documents instead of the download directory.
  `explorer.exe` parses a single raw command line rather than argv, so a
  pre-quoted `/select,` argument was misread; the reveal command is now passed
  as one string on Windows. A missing file opens its containing folder, and the
  Linux path no longer opens one level too high.
- **Downloads rejected by WhatsApp and Facebook.** A file this app downloaded
  was found to be VP9-in-MP4, which those platforms (and most editors) reject.
  Every download is now re-encoded to H.264/AAC when its video *or* audio codec
  is not universally supported. This also runs on the batch/queue path.
- Instagram Reels failed with "Requested format is not available": the format
  selector demanded H.264, but Reels often serve only VP9/AV1. The selector
  accepts any available stream again and the guarantee is applied after
  download instead.

### Changed
- **Editor-safe output contract.** Every file the app produces is H.264 video
  with AAC/MP3/PCM audio, so it imports into CapCut, Premiere Pro, After
  Effects, and DaVinci Resolve. Remux only copies codecs that are already safe;
  a forced copy of an unsupported codec is re-encoded and says so.
- Removed `webm`, `ogg`, `opus`, `wma`, and `flac` (their containers cannot hold
  an editor-safe codec). Remaining formats: `mp4`, `mkv`, `mov`, `avi`, `gif`,
  `mp3`, `m4a`, `wav`, `aac`.

## v0.9.0 - 2026-10-01
### Added
- **Queue** — persistent download queue (`core/queue.py`): `Queue`/`QueueStore`
  hold jobs as plain data (no threads), saved to `queue.json` in the app config
  directory. Set `SOCIALCLIP_QUEUE` to override the path. The GUI Queue tab and
  the CLI share the same file
- `socialclip queue add|list|run|clear` commands, each with `--json` output;
  `run` processes pending jobs one at a time and saves after each
- Queue tab (`ui/batch_tab.py:QueueTab`), replacing the old Batch tab: a URL
  table with per-item status plus **Add URLs**, **Paste**, **Pause**/**Resume**,
  **Cancel** (the current item and per-row), and **Clear finished**
- `workers/queue_worker.py` drives the queue on a `QThread`, one job at a time,
  reporting through Qt signals
- Mid-download abort: `core.download.download_one` takes a `cancel` callable
  checked in the yt-dlp progress hook and a new `cancelled` error category,
  distinct from the six in `sites/errors.py` and a terminal queue state; the
  partial file it created is cleaned up
- **Conversion formats** — curated 9-format registry (`core/formats.py`):
  video `mp4`, `mkv`, `mov`, `avi`, `gif`; audio `mp3`, `m4a`, `wav`, `aac`.
  Each format declares its container, codec pair, extension, and remux
  allow-lists
- Auto remux-vs-transcode (`core.convert.plan_conversion`): remux (fast,
  lossless) when the source streams are already in the target's
  `remux_v`/`remux_a` allow-lists, otherwise transcode to the format's codec
  pair. Legality is defined by the allow-lists, never by ad-hoc guessing
- `core/probe.py`: one `ffprobe` call returning
  `{vcodec, acodec, height, container}`; never raises, and empty codecs force a
  transcode plan
- "Copy streams" control in the Convert tab (Auto / Copy / Re-encode)
- `socialclip convert FILE --to <format> [--copy|--no-copy]`; an unknown key
  exits `2` and lists the valid formats
- Flat minimal app icon, wired at runtime (`assets/icon.ico`)

### Changed
- The Batch tab is now the Queue tab; the per-URL progress model is replaced by
  a persistent, resumable queue
- `socialclip convert --to` now names a registered format key instead of a
  fixed `output_type`; omitting `--to` keeps the previous `output_type`
  behaviour (`--to wav`, for example, produces the same audio through the
  format path rather than the legacy WAV path)
- `convert --resolution` was removed (it was inert once the format path took
  over video); resolution now applies to video format targets in the GUI
- **Editor-safe output contract** — every download and every converter target
  writes H.264 video with AAC, MP3, or PCM audio. Non-conforming download
  sources (video or audio) are re-encoded, and a forced stream copy of a
  hostile codec is upgraded to a transcode, so the saved file opens in CapCut,
  Premiere Pro, After Effects, and DaVinci Resolve

### Fixed
- Queue job snapshots are emitted to the GUI instead of the live `QueueJob`
  object, so a slot can no longer read state mutated on the worker thread
- The queue is written through a per-process tmp file, so concurrent GUI and CLI
  saves cannot clobber each other's partial file
- Partial files are cleaned up after any failed download, not only cancellation
- The window icon is imported from `QtGui`, so it renders correctly at runtime

### Removed
- `workers/batch_worker.py` (superseded by `workers/queue_worker.py`)
- `ogg`, `opus`, `wma`, and `flac` converter formats: those containers and
  codecs are rejected by the four target editors
- `webm`: the WebM muxer accepts only VP8/VP9/AV1 video and Vorbis/Opus audio,
  all editor-hostile, so an editor-safe WebM cannot be produced

## v0.8.0 - 2026-10-01
### Added
- Doctor health report (`core/doctor.py`) covering ffmpeg presence/version,
  per-platform cookie files, and network reachability. `socialclip doctor`
  renders it as text and `--json` as structured output; the report carries its
  own `schema_version` `"1.1"` (the download result contract stays `"1.0"`)
- First-run welcome dialog with the default save folder, ffmpeg status, and
  cookie guidance; a **Doctor** action in the Help menu opens the full report
  (`ui/dialogs.py`)
- Single tab: auto-fetch on a pasted URL, clipboard fill on focus/show, and an
  **Open folder** button that reveals the final artifact
- Batch tab: per-URL table showing each item's status, plus a bulk **Paste**
  action that appends URLs from the clipboard
- New pure helpers: `utils/ui_helpers.py` (`looks_like_url`,
  `reveal_in_folder`) and cookie lookup helpers in `sites/cookies.py`

### Deferred
- Batch tab per-item percentage progress (`running <pct>%`): v0.8 rows are
  state-only; the per-item percentage in the row is a follow-up

## v0.7.0 - 2026-10-01
### Added
- Headless `core/` package (Qt-free) shared by the GUI and the CLI:
  `core.download.download_one`, `core.convert.convert_file`, `core.manifest`
  (versioned JSON contract), `core.pipeline`
- `socialclip` command-line tool: `download`, `convert`, `doctor`,
  `manifest-schema`, with `--json` structured output and documented exit codes
  (0 ok, 1 failure, 2 usage, 3 missing dependency)
- Console binary per OS in the release workflow, alongside the GUI binary
- Error categories extended: `network`, `not_found`

### Fixed
- Platform detection matched substrings, so any URL containing `x.com`
  (e.g. `app.box.com`) was misdetected as Twitter; detection now parses the
  hostname and matches anchored patterns
- `socialclip download` re-encoded anything above 1080p by default; conversion
  is now opt-in via `--convert`, matching the GUI checkbox
- The ffmpeg-missing warning used `print()`, invisible in the `--windowed`
  build; it is now a dialog
- Batch downloads could not be stopped; a Cancel button is now wired to the
  worker
- `ffmpeg_location` is only passed to yt-dlp when the resolved path exists
- GUI download/convert lost their skip and success status messages after the
  core refactor

## v0.6.1 - 2026-10-01
### Added
- Per-OS release binaries (Windows/macOS/Linux) built by GitHub Actions
- HiDPI scaling and settings persistence (save dir, cookies, convert options,
  window geometry)
- macOS/Linux launcher (`run.sh`)

### Fixed
- ffmpeg is now located via env override / PATH / common install dirs, and the
  resolved path is passed to yt-dlp (installations outside PATH now work)
- Cookie file lookup falls back to the app directory when the launch directory
  has none
- Shared `classify_error` used by all download paths (consistent messages)

## v0.6.0 - 2026-09-02
### Added
- Facebook support (videos, Reels, single and batch download)
- Facebook cookie auto-detection and platform-aware error messages

### Fixed
- Duration display crash when yt-dlp returns float duration
- ffmpeg-not-found errors now show clear install instructions instead of raw traceback

## v0.5.0 - 2026-07-23
### Changed
- Restored default Qt theme (removed dark QSS + Fusion style)
- Replaced sidebar + header with QTabWidget layout
- Removed queue system (dlqueue module)
- Simplified all tab layouts to flat design (no card wrappers)
- Consolidated entry point to single `socialclip_downloader.py`

### Added
- Platform cookie auto-detection for YouTube, Douyin, Instagram, Twitter/X, TikTok, Bilibili
- Platform-aware error messages (shows correct site name, not generic "YouTube")
- Cookie UI in batch tab (was missing entirely)
- Shared combo constants (`OUTPUT_FORMATS`, `RESOLUTIONS`, `CONV_OUTPUT_FORMATS`)

### Fixed
- `clean_title` now preserves non-ASCII characters (Chinese, etc.)
- False "success" messages after ffmpeg failure in all workers
- `ydl.prepare_filename()` called outside context manager in batch worker
- Stale worker signals firing after URL change (sequence guards)
- Multiple workers starting on rapid button clicks
- Auto-cookies overwriting manual cookie selection
- `editingFinished` clearing cached metadata on focus loss

## v0.3.0 - 2026-03-16
### Added
- Added `run.bat` to simplify launching the app.
- Added cookie authentication support (cookies.txt) in `DownloadWorker` and GUI.

### Fixed
- Improved error handling and code readability.
- Updated `.gitignore` to improve organization.

## v0.2.0 - 2025-12-24
### Added
- Initial GUI with yt-dlp backend.
- MP3 conversion support.
- Resolution targeting for downloads.

## v0.1.0 - 2025-09-20
- First working version
