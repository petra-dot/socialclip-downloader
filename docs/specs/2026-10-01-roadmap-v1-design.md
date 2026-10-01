# Roadmap to v1.0

Status: proposed
Date: 2026-10-01
Starting point: v0.6.1

## Problem

SocialClip Downloader is currently "a yt-dlp GUI". That is not a product
position, because `yt-dlp` already handles extraction, format selection,
merging, and audio extraction. Anything this tool does not add on top of
that is something a user (or an AI agent) can already do themselves.

Two gaps in the ecosystem define the opportunity:

1. `yt-dlp` is CLI-only and unfriendly to non-technical users. Existing GUI
   wrappers are GUI-only and therefore invisible to agents.
2. No tool in this space exposes a *stable, parseable contract* to an agent.
   An agent driving raw `yt-dlp` must parse human-prose stderr, guess where
   the file landed, and hand-roll the ffmpeg post-processing recipe.

## Positioning

One core, two front-ends.

- A headless core owns the parts users and agents get wrong: the ffmpeg
  merge recipe, resolution policy, MP3 extraction, cookie/auth handling,
  cookie-file discovery, and the error taxonomy.
- The PyQt5 GUI stays the human front-end.
- A new `socialclip` CLI is the agent front-end, emitting structured JSON.

The primary differentiator (what we lead with):

- **Structured output** — `--json` results with the final path, height,
  size, platform, and a machine-readable error category.
- **Deterministic orchestration** — the post-processing decision is a fixed,
  tested table, not a per-call improvisation.
- **Per-site auth/error diagnosis** — `yt-dlp` extracts; this tool explains
  "Douyin needs cookies" and names the platform.

## Non-goals

- A cloud service, accounts, or telemetry.
- Replacing yt-dlp. We are a layer over it, and we track its releases.
- An MCP server before v1.0. The CLI is the shared core; MCP wraps it later.
- Bundling a browser. Cookie export stays a user action.

## Architecture

### The core

New package `core/` with **no PyQt imports**. It is importable and testable
without a display.

```
core/
  manifest.py     DownloadResult / Manifest dataclasses, JSON encode
  download.py     download_one(url, opts) -> DownloadResult
  convert.py      convert_file(path, opts) -> ConvertResult
  options.py      CoreOptions: output type, resolution, cookies, save dir
```

Existing logic moves into or is shared with `core/`:

- `workers/pipeline.py` `plan_postprocess` moves to `core/pipeline.py`.
  `workers/pipeline.py` becomes a re-export shim for one release, then is
  deleted. No behavior change.
- `sites/errors.py` `classify_error` becomes the single error vocabulary and
  gains the `network` and `not_found` categories.
- `utils/ffmpeg.py` stays the binary resolver.
- `utils/file_utils.py` keeps filename/path helpers.

The core does not import `utils.ydl_opts`'s postprocessor dict wholesale;
`_nle_ydl_opts` moves to `core/options.py` as the one place download options
are built, and `utils/ydl_opts.py` keeps only the thin subprocess wrappers.

### The CLI

`cli.py`, installed as the `socialclip` console script.

```
socialclip download URL [--json] [--output DIR] [--format mp4|mp3]
                        [--resolution 720|1080|1440|2160] [--cookies FILE]
socialclip convert FILE [--json] [--to mp4|mp3|wav] [--resolution N]
socialclip doctor [--json]
socialclip manifest-schema         # prints the JSON schema + its version
```

### The GUI

Workers (`download_worker`, `batch_worker`, `convert_worker`) become thin
adapter layers: they call the core, then emit Qt signals carrying the same
`DownloadResult` the CLI serializes. No logic duplication between surfaces.

## The agent contract

`--json` writes exactly one JSON object to stdout and nothing else. Human
progress text goes to stderr. This separation is the whole point: an agent
reads stdout, a human reads stderr.

```json
{
  "schema_version": "1.0",
  "status": "ok",
  "url": "https://www.facebook.com/reel/931231782795079",
  "platform": "facebook",
  "title": "Example Reel",
  "path": "D:/Downloads/Example Reel.mp4",
  "extension": "mp4",
  "height": 1080,
  "bytes": 48213004,
  "duration_seconds": 42,
  "error_category": null,
  "message": null
}
```

On failure `status` is `"error"`, `path` is `null`, and `error_category` is
one of: `"blocked"`, `"format"`, `"ffmpeg"`, `"network"`, `"not_found"`,
`"other"`.

Today `classify_error` (sites/errors.py) returns `blocked`, `format`,
`ffmpeg`, `other`. v0.7 must add `network` and `not_found` to that function,
with tests, so the CLI categories are real and not aspirational. This is
in-scope for v0.7, not deferred.

- `schema_version` is bumped on any breaking field change.
- `socialclip manifest-schema` prints the JSON Schema for the current
  version so an agent can validate or pin against it.

### Exit codes

- `0` success
- `1` download/extraction failure (see `error_category` in the JSON)
- `2` usage error (bad arguments)
- `3` missing dependency (ffmpeg not found, yt-dlp missing)

Exit codes let an agent branch without parsing JSON when it only needs
pass/fail.

## Releases

### v0.7 — Headless core + CLI

Ship the differentiator. Extract the core, prove the GUI still works on it,
ship `socialclip download|convert|doctor --json` and `manifest-schema`.
Add the `socialclip` console build to `release.yml` alongside the GUI build.

Honest caveat to carry: the core refactor touches both workers. The test
guard is that the existing GUI behavior is unchanged and the pure functions
keep their tests.

### v0.8 — Human onboarding + reliability

- First-run flow: no dead ends, a sensible default save location, a cheap
  way to paste a URL and go.
- `socialclip doctor`: reports ffmpeg presence/version, cookie files found,
  network reachability.
- Post-download "Open folder" action.
- Progress that reflects reality (no false 100%).

### v0.9 — Power features (still public-relevant)

- Download queue with pause/resume/cancel across items.
- Playlist/channel support with an explicit item cap (default off).
- Subtitles, thumbnail/cover embedding.
- Interactive format picker for users who want a specific stream.

### v1.0 — MCP server + distribution

- MCP server exposing the CLI as tools (`download_video`, `get_metadata`,
  `convert_media`), reusing the same core and contract.
- Package managers: Homebrew cask, winget, Scoop, AppImage/`.desktop`.
- Freeze the `schema_version: "1.0"` contract as stable.

## Testing strategy

- Pure functions (`plan_postprocess`, `classify_error`, `find_ffmpeg`,
  manifest building) under pytest. This is where the project's tests already
  live and where new core logic must land.
- The CLI is tested by invoking it as a subprocess against a local fixture
  file (no network) for `convert` and against a mocked downloader for
  `download`; assert on stdout JSON and exit code.
- The core is imported by tests directly; no Qt, no threads.
- GUI remains manually tested, as today. This is a known gap, not a
  regression.

## Risks

- **Core refactor regresses the GUI.** Mitigation: keep the GUI on the core
  only after the core's tests are green; ship v0.7 only when the three tabs
  are re-verified by hand.
- **yt-dlp output drifts.** Mitigation: `classify_error` already isolates the
  couple points; add a test per known drift.
- **Scope creep into an MCP server too early.** Mitigation: MCP is v1.0.
- **Cross-platform binaries remain unverified on macOS/Linux.** Open issue
  from v0.6.1; the roadmap does not claim to close it.

## Decisions taken

- CLI name is **`socialclip`**. It matches the repo and the window title.
  `scdl` is rejected for being non-obvious to a first-time user.
- The CLI ships as its **own console build**, not inside the windowed GUI
  binary. A `--windowed` PyInstaller onefile on Windows has no console and
  cannot emit stdout, so a windowed GUI binary cannot serve as the agent
  interface. `release.yml` gains a second, console build per OS.

## Open questions

- None blocking. Decisions above close the two that would have blocked v0.7.
