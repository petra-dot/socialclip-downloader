# Cookies manager: browser cookies plus file override

Date: 2026-10-16
Status: approved

## Why

The most common download failures (login-required, age-gated, bot-check) are
cookie problems. Today cookies are a manual file path per platform: the user
exports a Netscape file, names it correctly, and drops it next to the app. A
browser-backed source removes that whole step.

## Decisions

1. **One global browser choice**, e.g. "Use cookies from: No cookies / Chrome /
   Firefox / Edge / Brave". A per-platform cookie file still overrides it.
2. **A Cookies dialog** (File -> Cookies) holds the browser combo, a per-platform
   status list, and an "Open cookie folder" button. One place, applies to all
   tabs and the CLI.
3. **CLI too:** `download --cookies-from-browser BROWSER` and
   `queue add --cookies-from-browser BROWSER`.
4. **Precedence:** a platform cookie file wins; the browser is the fallback.

## Security guarantees (binding)

- **Nothing is imported.** The app never reads a browser profile itself and never
  writes a cookie file. It passes a browser name to yt-dlp's `cookiesfrombrowser`,
  and yt-dlp reads the browser's cookie database at download time. Any temp copy
  yt-dlp makes lives outside this repo and is yt-dlp's own transient file.
- **No personal data enters the repo, now or later.** `.gitignore` already ignores
  `cookies.txt`, `*.cookies.txt`, `*cookies.txt`; CI's `gitleaks.yml` scans for
  Netscape cookie exports; AGENTS.md forbids committing cookies.
- **Tests never touch a real browser.** Every test fakes yt-dlp
  (`monkeypatch.setattr("yt_dlp.YoutubeDL", ...)`) and asserts only the options
  dict (the `cookiesfrombrowser` tuple). No test opens Edge, Brave, or any real
  profile. This is a binding rule for the plan, not a preference.
- **The dialog does not read a browser.** "Open cookie folder" opens the app
  directory only.

## Non-goals

- No per-platform browser matrix (one global browser).
- No cookie import/export or a snapshot file.
- No reading, parsing, or displaying cookie contents.
- No browser auto-detection or "is the browser installed" probing.

## Architecture

### `sites/cookies.py` (pure)

- `BROWSERS = ("chrome", "chromium", "firefox", "edge", "brave", "opera",
  "vivaldi", "safari", "whale")` - the names offered by the combo and accepted by
  the CLI flag. (yt-dlp supports more; this is the offered set.)
- `cookie_status() -> list` - one `(platform, display_name, file_path)` per entry
  in `PLATFORM_NAMES`, `file_path` from the existing `cookie_file_for`. Powers the
  dialog's status list. Pure, no browser access.

### `utils/ydl_opts.py`

`_nle_ydl_opts(outtmpl, progress_hooks=None, cookies_file=None,
archive_file=None, cookies_from_browser=None)`. Precedence:

```python
    if cookies_file and os.path.isfile(cookies_file):
        opts["cookiefile"] = cookies_file
    elif cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser, None, None, None)
```

### `core/download.py`

`download_one(..., cookies_from_browser=None)`; pass it to both `_nle_ydl_opts`
calls (the section path and the clip fallback), beside `cookies_file`.

### `ui/dialogs.py`

`CookiesDialog(parent=None)`:

- A "Use cookies from:" `QComboBox` with "No cookies" (data `""`) then each
  `BROWSERS` entry (display name capitalised).
- A read-only per-platform status list from `cookie_status()`: "YouTube: none" or
  "YouTube: <path>".
- An "Open cookie folder" button calling `reveal_in_folder(app_dir())`.
- `chosen_browser() -> str` returns the combo's data.

### `ui/main_window.py`

A File -> "Cookies..." action opening `CookiesDialog`; on accept, store the choice
in `QSettings` key `cookies/browser`. A small helper `current_browser()` reads it
(default `""`).

### Tabs, workers, CLI

The browser is baked into a job's options at add time, exactly like
`cookies_file`:

- `ui/batch_tab.py`: `build_job_options(save_dir, output_text, resolution,
  cookies_path, subtitles="off", cookies_from_browser="")` adds the key;
  `_job_options` passes the global `cookies/browser` setting.
- `ui/single_tab.py`: passes `cookies_from_browser` to `DownloadWorker`.
- `workers/download_worker.py`: `DownloadWorker(..., cookies_from_browser="")`
  forwards to `download_one`.
- `workers/queue_worker.py`: `_download` reads `opts.get("cookies_from_browser")`.
- `cli.py`: `download --cookies-from-browser`; `queue add
  --cookies-from-browser`; `_queue_executor` reads the job option.

## Data flow

```
Cookies dialog ──▶ QSettings[cookies/browser] ──▶ build_job_options / DownloadWorker
                                                          │
                                          download_one(cookies_from_browser=)
                                                          │
                                          _nle_ydl_opts: file wins, else browser
                                                          │
                                          yt-dlp reads the browser DB (outside the repo)
```

## Error handling

A browser yt-dlp cannot read (Chrome running, profile locked, not installed)
raises inside `download_one` and is classified by `sites.errors.classify_error`
like any other failure. The dialog never probes a browser, so it cannot fail.

## Testing

- `_nle_ydl_opts`: file present -> `cookiefile` set, `cookiesfrombrowser` absent;
  no file + browser -> `cookiesfrombrowser == (browser, None, None, None)`; neither
  -> neither key.
- `cookie_status()`: one row per platform; a platform with a file reports its path.
- CLI: `download --cookies-from-browser chrome` reaches `download_one` with
  `cookies_from_browser="chrome"`; `queue add --cookies-from-browser` stores it in
  the job options.
- `CookiesDialog` constructs offscreen; `chosen_browser()` reflects the combo.
- **No test may read a real browser profile** (see Security guarantees).

## Known limitations

- yt-dlp reading Chrome's or Edge's cookie database can fail while the browser is
  running (yt-dlp copies the DB, but not always successfully). Surfaces as a normal
  classified error.
- The browser choice is global, not per platform.
- Cookies age with the browser session; a stale login fails as it would in the
  browser.
