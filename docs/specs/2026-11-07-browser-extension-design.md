# Browser extension support (link fetch, add to queue, download now)

## Intent

Downloads currently start from inside the app: copy a URL, switch to the app,
paste, press Fetch, then Download. The most common path is the reverse: you are
already looking at the video in the browser and the app is somewhere behind it.

This adds a thin browser extension so the browser can hand a link to the app:
right-click to add to the Queue or to download it now, and a page scan that
collects the supported links already on the page.

## Goals

- Context menu entries on a link, a page, or a media element:
  **Add to SocialClip Queue** and **Download now**.
- Download now opens a small popup to pick output format and resolution, then
  the app opens on the Queue tab with that job already running, so progress and
  errors are visible where they always are.
- Link fetch: the popup scans the current page's anchors, keeps only hosts the
  app supports, shows the list, and bulk-adds the ticked ones.
- Works with the app closed. The browser starts the app when needed.
- Chrome, Edge and Firefox.
- No new Python dependency.

## Non-goals

- No download-manager takeover. The extension never intercepts the browser's
  own downloads.
- No reading of browser profiles or cookies from the extension.
- No store publishing. This ships as a developer-mode load plus a one-time
  registration that the app performs itself.
- No progress UI inside the browser. Progress stays in the app.
- No support for pages that need a logged-in session the app cannot reach. Those
  still need the existing cookies flow.

## Anti-goals

- A second, hand-maintained copy of the supported-site list in JavaScript.
- An open TCP port on the user's machine.
- Two app instances writing `queue.json`, or downloading the same URL twice.

## Constraints

- Native messaging: the host is an executable browser-spawned process. It reads
  one length-prefixed JSON message on stdin and writes one on stdout. Stdout is
  protocol only, so the GUI can never appear on that path. The shipped build is
  windowed, where Python hands the process `None` for both streams, so the host
  must read and write the raw OS handles rather than `sys.stdin`/`sys.stdout`.
- The extension ID must be stable for `allowed_origins` to work. Registration
  therefore takes the Chromium extension id as an argument rather than guessing
  it, and Firefox gets a fixed add-on id (`socialclip@petra-dot`) in its
  manifest. A pinned `key` in the Chromium manifest is not needed for a
  developer-mode load from a fixed folder.
- Host registration is per browser, all under HKCU on Windows: Chrome, Edge and
  Firefox each get a registry key under their own
  `NativeMessagingHosts\com.petra_dot.socialclip` path pointing at the manifest.
  No admin rights needed for any of them.
- Firefox MV3 uses an event page (`background.scripts`), Chromium uses a
  service worker. Two manifests, one shared payload.
- A permanent Firefox install requires AMO signing (unlisted is enough);
  Chromium wants a store listing or developer mode.
- `core/` stays Qt-free, so the queue-options builder must move out of
  `ui/batch_tab.py` before the host can use it.
- PyInstaller onefile: expect roughly a second of host startup per action.

## Approaches

**Loopback HTTP listener (rejected).** The app serves `127.0.0.1:<port>` with a
token and the extension POSTs URLs. Instant and simple on both sides, but it
opens a port, needs a token the user has to carry into the extension, and fails
outright whenever the app is not already running.

**Custom URL scheme (rejected).** Handling `socialclip://add?url=` needs a
registry entry and no extension at all. But the request needs a context menu,
which only an extension provides, so the scheme would be extra machinery on top
of the extension rather than a replacement for the transport.

**Native messaging (chosen).** The browser launches the installed exe in a
headless mode, that process replies and exits, and nothing listens on a port.
It also answers the "app is closed" case without a daemon, which the other two
cannot.

## How it works

1. **Registration.** A new `--install-native-host` flag (also reachable from the
   app's File menu) writes the host manifest to the data directory and registers
   Chrome, Edge and Firefox under their own HKCU
   `NativeMessagingHosts\com.petra_dot.socialclip` keys. The manifest names the
   current executable, or a wrapper that runs the entry point with the flag when
   running from a source checkout.

2. **Host mode.** `--native-host` reads one message, answers, exits:
   - `ping` returns the app version, so the extension can say "app not installed"
     or "app outdated" instead of failing silently.
   - `sites` returns the platform host patterns from `sites/cookies.py` plus the
     protocol version, so the page scanner filters with the app's real list
     instead of a hand-copied one. That list covers the seven named platforms,
     so a link on any other yt-dlp-supported site is not offered by the scanner.
   - `formats` returns the download path's real choices: `MP4`/`MP3` and the
     values in `utils/file_utils.RESOLUTIONS`. `core/formats.py` is the
     converter's registry and is deliberately not used here, because the Queue
     cannot produce those containers.
   - `check` takes URLs and reports which are already in the queue and which are
     already in history, so the extension can warn before anything is added.
   - `add` takes URLs plus output, resolution and a start flag, enqueues them,
     and returns how many were added. It does not filter: consent already came
     from the popup.
   - Replies stay well under the browser's 1 MB cap: the scanner sends at most
     200 links and reports the rest as not shown.

3. **Single instance.** The host first tries to talk to a running app over a
   `QLocalServer` named per user. If the app is up, it hands over the job so the
   running app owns the file and the job starts immediately. If not, the host
   writes `queue.json` itself and, when the request asked to start, spawns the
   GUI with the new `--run-queue` flag, which starts pending jobs on launch. The
   same guard makes a second normal launch raise the existing window instead of
   opening a rival one, which also fixes today's duplicate-writer hazard.

   Direct writes use a strict load that refuses to continue on a corrupt or
   unknown-version file and returns an error to the extension. Today's
   `QueueStore.load()` swallows that case and leaves an empty list, which the
   next save would write over the user's queue. Known limit: an older app build
   already running has no local server, so it is still a second writer; the
   version reply is what lets the extension warn instead of guessing.

4. **Extension.** Context menu with the two entries, a popup with the format
   picker and the scanned-link list, and a background script that owns all host
   calls. The popup caches the last `formats` and `sites` reply in extension
   storage so it paints immediately and refreshes in the background.

   A context-menu add that turns out to be a duplicate does not add silently: it
   opens the popup instead, which names the reason ("already in the queue",
   "already in your history") and offers Add anyway or Cancel. In the scanned
   list, known rows are marked but stay tickable, and the summary line counts
   them.

## Decisions taken in this conversation

- Download now picks the format in the popup, then opens the app and shows it
  running rather than downloading invisibly.
- Transport is native messaging.
- Chrome, Edge and Firefox from the start.
- Link fetch collects anchors on the page whose host the app supports, with a
  tick list before adding.
- A URL that is already in the queue or already in history is never skipped
  silently. It is flagged, and you decide whether to add it anyway.

## Calls I made, for you to check

- **Single-instance guard is in scope.** Without it, "open the app" per click
  produces a second window that overwrites the first one's `queue.json`. It is
  small Qt work and fixes a latent bug, so it is a prerequisite, not a nice-to-
  have.
- **`build_job_options` moves from `ui/batch_tab.py` to `core/`** and the tab
  imports it, so the headless host can build the same option dict without Qt
  widgets.
- **Format and site lists are served by the host, not hardcoded in JS.** One
  source of truth; a stale cache is refreshed on every popup open. Formats are
  the download path's two types and resolutions, not the converter registry.
- **Subtitles default to off** on extension jobs. The Queue tab's subtitle
  choice is never persisted, so there is no stored value to inherit and
  inventing one would be a guess.
- **Cookies come from the persisted settings** (`batch/cookies`,
  `cookies/browser`). This differs from a job queued by hand in the same session,
  where the tab's live path is used. Accept the difference instead of adding a
  second settings store.
- **Source checkouts get a wrapper launcher.** A manifest pointing at
  `python.exe` cannot pass `--native-host`, so registration writes a small
  `.cmd`/`.sh` wrapper in the data directory that runs the entry point with the
  flag, and the manifest points at the wrapper. A frozen build points straight
  at the exe.
- **The extension requires protocol version 1**, reported by `ping`, so an older
  install says "update the app" rather than failing obscurely.
- **Extension ID is passed at install time.** `--install-native-host --extension-id <id>`
  names the Chromium origin, and Firefox gets the fixed `socialclip@petra-dot`
  add-on id, so no manifest `key` generation is needed.

## What is left to the builder

- Exact popup layout and wording, and the error copy for host-not-registered,
  app-too-old and message-rejected.
- Packaging: whether the extension directory ships in the repo only, or also as
  a zip attached to the release. Settle at build time.

## Verification

- Pure logic gets tests: manifest generation for each browser, host-message
  parsing and replies, the `check` duplicate lookup against a queue and a
  history fixture, host-pattern filtering against `sites/cookies.py`, and the
  strict queue load refusing a corrupt file.
- The offscreen UI script gains a check that `--run-queue` starts pending jobs.
- Real check: load the unpacked extension, right-click a link, confirm the job
  lands in the Queue and the app comes forward.
