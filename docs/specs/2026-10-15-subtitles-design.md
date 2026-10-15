# Subtitle Downloads - Design

Status: proposed
Date: 2026-10-15
Applies to: `core/subtitles.py` (new), `core/download.py`,
`workers/download_worker.py`, `ui/single_tab.py`, `ui/batch_tab.py`, `cli.py`,
`tests/test_subtitles.py` (new)

## Problem

Editors cut to captions. Today the app downloads video and audio only, so a
caption has to be fetched by hand or retyped. `core/download.download_one`
already declares `subtitles=False` and `embed_thumbnail=False`, but nothing
reads them and `_nle_ydl_opts` sets no subtitle options; the feature was never
built.

## Goal

Fetch a video's subtitles and either save them as sidecar `.srt` files next to
the video, embed them as tracks, or both, selectable per download, from the
Download tab, the Queue, and the CLI.

## Non-goals

- Burning subtitles into the picture (a hard-sub render is a Convert-tab job,
  not this feature).
- Transcribing a video that has no subtitles at all (that is speech-to-text,
  out of scope).
- A subtitle editor or timing fixups.
- Changing the download result contract (`schema_version` `"1.0"`).

## Decisions taken

1. **Delivery is a per-download choice: Off, Sidecar, Embed, or Both.**
2. **All available languages.** No language field; every track the video offers
   is fetched.
3. **Manual and auto-generated tracks are both kept**, as distinct files.
4. **Available on the Download tab, the Queue, and the CLI.**

## Architecture

### `core/subtitles.py` (new, Qt-free)

```python
@dataclass
class SubtitleTrack:
    lang: str
    kind: str        # "manual" | "auto"
    url: str
    ext: str

DELIVERIES = ("off", "sidecar", "embed", "both")

subtitle_tracks(info) -> List[SubtitleTrack]      # pure
write_subtitle(track, base_path, opener=None) -> Optional[str]
embed_subtitles(video_path, subtitles) -> bool    # subtitles: list of (lang, path)
```

- `subtitle_tracks` reads `info["subtitles"]` (manual) and
  `info["automatic_captions"]` (auto). Each maps a language to a list of format
  dicts (`ext`, `url`). It prefers `srt`, then `vtt`; a language offering
  neither is skipped (a `json3` or `srv` source would need its own parser). Pure,
  so it carries the tests.
- `write_subtitle` fetches the track URL and writes
  `<base>.<lang>.srt` for a manual track and `<base>.<lang>.auto.srt` for an
  auto one. A WebVTT source is converted to SRT with ffmpeg; an SRT source is
  written as-is. The distinct names are the point: no collision, both tracks
  kept, which is why this is not delegated to yt-dlp (yt-dlp writes a manual and
  an auto track for the same language to one filename).
- `embed_subtitles(video_path, subtitles)` muxes the sidecars into the video in
  one ffmpeg call (`-c copy -c:s mov_text`), replacing the file. `subtitles` is a
  list of `(lang, path)` pairs, so each stream is tagged with its language.

### `core/download.py`

`download_one`'s dead `subtitles=False` parameter becomes `subtitles="off"`,
taking a value from `DELIVERIES`. After the existing editor-safe step, when
`subtitles != "off"`:

1. `tracks = subtitle_tracks(info)`; write every track as a sidecar.
2. If the delivery is `embed` or `both`, `embed_subtitles(final_path, sidecars)`.
3. Delivery `embed` removes the sidecars after muxing; `sidecar` and `both`
   keep them.

The sidecar base is the final video's base name, so a clip's subtitles carry
the clip's name.

### Delivery

| Value | Sidecars kept | Embedded track |
|---|---|---|
| off | no | no |
| sidecar | yes | no |
| embed | no (removed after mux) | yes |
| both | yes | yes |

### `ui/single_tab.py` and `ui/batch_tab.py`

A **Subtitles:** combo (**Off** / **Sidecar (.srt)** / **Embed** / **Both**),
default Off, on both tabs. The Download tab passes it to `DownloadWorker`; the
Queue's `build_job_options` gains a `subtitles` field so every queued job
carries it. Off leaves the download byte-identical to today.

### `cli.py`

`download --subtitles {off,sidecar,embed,both}`, default `off`.

## Testing

`tests/test_subtitles.py`:
- `subtitle_tracks` on a fake `info` with a manual and an auto track for one
  language, a manual-only language, and an auto-only language: all three become
  tracks, the manual and auto ones carry distinct `kind`, and an `srt` format is
  preferred over `vtt`.
- A language whose only format has no `url` is skipped.

No tests for the fetch, the WebVTT-to-SRT conversion, or the embed mux; those
are network and ffmpeg, verified by hand, matching the repo convention.

## Risks

1. **Many files.** "All available" on a popular video can mean a dozen or more
   `.srt` files. That is what "all available" asks for, and Off is the default.
2. **Subtitle URLs expire.** yt-dlp's subtitle URLs are signed and short-lived,
   so they are fetched in the same run as the download, not cached.
3. **The embed mux replaces the video file**, so a failed mux must not lose the
   original. The mux writes to a temp name and replaces only on success, as the
   existing convert steps do.
4. **A video with no subtitle tracks** yields nothing and is not an error; the
   download still succeeds.
5. **WebVTT to SRT via ffmpeg** is the conversion path; if ffmpeg is missing the
   download already fails earlier, so this adds no new dependency.
