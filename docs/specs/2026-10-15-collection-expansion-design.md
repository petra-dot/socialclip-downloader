# Collection Expansion (Playlists, Channels, Profiles) - Design

Status: proposed
Date: 2026-10-15
Applies to: `sites/collections.py` (new), `core/collections.py` (new),
`workers/expand_worker.py` (new), `ui/batch_tab.py`, `ui/single_tab.py`,
`ui/main_window.py`, `ui/dialogs.py`, `core/queue.py`, `cli.py`

## Problem

A collection URL is a URL that points at many videos: a YouTube playlist, a
channel, or a social profile. Today the app treats every URL as one video.

- `utils/ydl_opts.py:79` hardcodes `"noplaylist": True`, so pasting a playlist
  or channel link downloads a single video and says nothing. The user thinks
  the app is broken.
- Users paste these links expecting the whole collection to be queued.
- Listing a collection is easy on YouTube through yt-dlp, and unreliable
  elsewhere (Instagram, TikTok, X, Facebook). The app must be honest about
  which is which instead of pretending they are equal.

## Goal

Pasting a collection URL lists its videos, shows how many were found, and
enqueues them after the user confirms. It works from the Queue tab and from the
single Download tab, which hands the URL to the Queue. Listing is best-effort
per platform, with a clear message when a platform cannot list.

## Non-goals

- Owning per-platform crawlers (Instagram/TikTok/X private APIs). yt-dlp is the
  only listing engine; a second engine is a maintenance liability.
- Downloading a collection without going through the queue.
- Expanding a channel's Shorts or Live tabs (Videos only, yt-dlp's default).
- Changing the download result contract (`schema_version` `"1.0"`).

## Decisions taken

1. **Scope: all platforms, best-effort.** YouTube is reliable; the rest are
   attempted and may fail. Failures are reported honestly, not hidden.
2. **UX: preview and confirm.** Nothing enters the queue until the user
   confirms the expansion.
3. **Location: single tab hands off to the Queue.** All expansion happens in the
   Queue tab; the single tab routes collection URLs to it.
4. **Scale: soft cap, adjustable.** The fetch is capped at 200 entries by
   default. The confirm dialog can ask for more, which re-fetches with the
   higher limit before adding.
5. **Duplicates: skipped.** URLs already in the queue are not added again.
6. **Handoff triggers on Fetch/Download click**, not on paste. Auto-switching
   tabs mid-typing would be jarring.
7. **Channel = Videos tab only.** Shorts and Live are out of scope.
8. **No special row badge** for expanded jobs; the title is enough.
9. **CLI is opt-in**: `socialclip queue add --expand <url>`. Without the flag a
   collection URL is added as a single job, as today.

## Architecture

### `sites/collections.py` (new, Qt-free, platform knowledge)

Mirrors `sites/cookies.py` and `sites/errors.py`: pure patterns, no network.

```python
classify_url(url) -> "video" | "collection" | "unknown"
collection_note(platform) -> str
```

- `classify_url` checks single-video patterns first, then collection patterns.
  Single-video patterns: `watch?v=`, `/p/`, `/reel/`, `/status/`, `/video/`,
  `/watch?v=`. Collection patterns per platform: YouTube `playlist?list=`,
  `/@handle`, `/channel/`, `/c/`, `/user/`, `/videos`; Instagram `/username/`;
  TikTok `/@username`; X `/username`; Facebook page/`/videos` roots; Bilibili
  `space.bilibili.com/<mid>`, `/space/`; Douyin `user/<id>`.
- YouTube nuance: `watch?v=X&list=Y` classifies as **video**, because the user
  opened a video, not a playlist.
- `collection_note(platform)` returns honest text, empty for YouTube, for
  example Instagram: "Profile listing is best-effort and often returns nothing.
  Paste individual post links instead."

### `core/collections.py` (new, Qt-free, does the network)

```python
DEFAULT_LIMIT = 200

@dataclass
class CollectionEntry:
    url: str
    title: str
    id: str

@dataclass
class ExpandResult:
    platform: str
    entries: list[CollectionEntry]
    total: int | None
    truncated: bool
    error: str | None
    category: str | None

def expand_collection(url, cookies_file=None, limit=DEFAULT_LIMIT) -> ExpandResult
def entries_from_info(info, limit) -> (entries, total, truncated)   # pure
def new_entries(entries, existing_urls) -> (kept, skipped)          # pure
```

- `expand_collection` uses yt-dlp with:
  `extract_flat="in_playlist"`, `skip_download=True`, `noplaylist=False`,
  `playlistend=limit`, `ignoreerrors=True` (one dead entry must not kill the
  list), `quiet=True`, `no_color=True`, `age_limit=99`, and `cookiefile` when a
  cookie file resolves. `playlistend` bounds the fetch, so a huge channel is
  finite work.
- `entries_from_info` normalizes each entry: prefer `webpage_url`, else `url`;
  when YouTube returns a bare id, form
  `https://www.youtube.com/watch?v=<id>`. `total` comes from `playlist_count`
  or `n_entries`; `truncated = total is not None and total > len(entries)`.
  Missing titles fall back to the id. Pure, so it gets tests.
- `new_entries` filters out URLs already present, preserving order, returning
  the count skipped. Pure.
- Failures route through `sites.errors.classify_error` for the category and
  `sites.collections.collection_note` for the message.

### `workers/expand_worker.py` (new)

A `QThread` that runs `expand_collection` and emits
`done_signal(ExpandResult)` / `error_signal(str)`. Mirrors
`workers/convert_worker.py`.

### `ui/batch_tab.py`

- `_add_jobs` splits parsed lines with `classify_url`. Singles are added
  immediately (current behavior). Collections run the expansion path one at a
  time.
- `expand_collection_url(url)` is the entry point shared by the paste flow and
  the single-tab handoff.
- During expansion: Add/Paste disabled, console logs the platform and result.
- On success: show `ExpandConfirmDialog`; on confirm, `queue.add(url, options,
  title=...)` per kept entry, save, refresh, log.
- On failure: console shows the `classify_error` category plus the
  `collection_note`.
- Table column 0 shows `job.title or job.url`, full URL as the cell tooltip.

### `ui/dialogs.py`

`ExpandConfirmDialog(result, existing_urls)`:
- "YouTube channel: 1,284 videos found."
- "Add first N" spinbox. Max is `total` when known, else the fetched count.
  Default is `min(200, max)`. Preview of the first ~20 titles, then "...and N
  more".
- "N already in the queue, skipped."
- Add / Cancel. Returns the chosen N.

When the chosen N exceeds `len(result.entries)` (the user asked for more than
the capped fetch returned), the caller re-runs
`expand_collection(url, limit=N)` once and adds from that result. This is the
only re-fetch path, and it is why the dialog's max can exceed what was fetched.

### `ui/single_tab.py` + `ui/main_window.py`

- `SingleTab.collection_requested = QtCore.pyqtSignal(str)`.
- First line of `on_fetch_metadata` (and `on_download` as a guard): if
  `classify_url(url) == "collection"`, log "This is a playlist or channel;
  opening the Queue.", emit, return.
- `MainWindow` connects the signal to a router that switches to the Queue tab
  and calls `batch_tab.expand_collection_url(url)`. The tabs stay decoupled;
  the signal is the only link.

### `core/queue.py`

- `QueueJob` gains `title: str = ""`. The default keeps `queue.json` backward
  compatible: `_coerce_jobs` builds `QueueJob(**raw)`, so a store written
  before this change still loads.
- `Queue.add(url, options=None, title="")`. `add_many` unchanged.

### `cli.py`

- `queue add --expand` lists the URL and enqueues every entry (same
  `expand_collection`), skipping already-queued URLs. Without `--expand`, a
  collection URL is added as a single job, unchanged.

## Platform expectations

| Platform | Listing quality | Note shown on failure |
|----------|-----------------|-----------------------|
| YouTube | reliable | (none) |
| Bilibili | usually works | may need cookies |
| TikTok | partial, rate-limited | best-effort, try cookies |
| Instagram | usually fails | paste post links instead |
| Twitter/X | partial, needs cookies | best-effort, try cookies |
| Facebook | rarely works | paste video links instead |
| Douyin | usually fails | best-effort, try cookies |

## Error handling

- Extraction failure: `classify_error` category + `collection_note`.
- Zero entries with no error: "Found no videos. The profile may be private or
  the listing may be unsupported for this site."
- Cookie-required sites reuse the existing cookie resolution
  (`sites.cookies.get_cookie_path`).
- A partially listed collection is used as-is; `truncated` is reported.

## Testing

- `tests/test_collections.py` (new):
  - `classify_url` table-driven across every platform, including
    `watch?v=X&list=Y` as video and junk as unknown.
  - `entries_from_info`: bare-id normalization, missing fields, empty entries,
    generator entries, truncation math.
  - `new_entries`: order preserved, skipped counted.
- `tests/test_queue.py` (extended): `title` default; store round-trip proving
  an old `queue.json` without `title` loads and a new one persists it.
- No tests for the network call or the Qt widgets, matching repo convention.

## Risks

1. Non-YouTube listing will fail or come back partial often. Accepted; the
   `collection_note` sets expectations.
2. A huge channel is slow even capped, because yt-dlp paginates internally to
   reach the cap. `playlistend` bounds it.
3. Some channels need cookies; the existing cookie path covers it.
4. Flat entries on some extractors have no real title; column 0 falls back to
   the URL.
5. A pasted playlist URL still downloads as a single video if the user ignores
   the handoff (for example, from the CLI without `--expand`). That is
   intentional and unchanged.
