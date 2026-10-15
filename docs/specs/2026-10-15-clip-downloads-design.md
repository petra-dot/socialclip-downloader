# Clip Downloads - Design

Status: proposed
Date: 2026-10-15
Applies to: `core/clip.py` (new), `core/download.py`,
`workers/download_worker.py`, `ui/single_tab.py`, `cli.py`,
`tests/test_clip.py` (new)

## Problem

Editors rarely want the whole video. A quote, one b-roll beat, or a single
chorus is what reaches the timeline; the rest is dead weight. Today the only
way to get a segment is to download the whole video and trim it in the editor,
which burns bandwidth on a long video and a step on every clip.

## Goal

Download only a requested time range, from the Download tab and the CLI, with a
cut that is lossless by default and frame-accurate on request, and that keeps
the editor-safe output guarantee.

## Non-goals

- Per-queue-item clips. A clip is a one-off for one video; the Queue stays bulk.
- Multiple ranges in one download (one start/end per download).
- A timeline or scrubbing UI.
- Clipping an already-downloaded file. That is the Convert tab's territory and a
  later feature.
- Changing the download result contract (`schema_version` `"1.0"`).

## Decisions taken

1. **Section download with a full-cut fallback.** The primary path asks yt-dlp
   for only the section; if that fails, download the full file and cut with
   ffmpeg.
2. **Stream-copy by default, exact cut on request.** Stream-copy is instant and
   lossless but snaps to keyframes; an "Exact cut" toggle re-encodes the clip
   for frame accuracy.
3. **Download tab and CLI only.** Not per-queue-item.
4. **Range entry is a mode toggle** between Start + End and Start + Duration,
   with lenient time parsing.

## Architecture

### `core/clip.py` (new, Qt-free, pure)

```python
@dataclass
class ClipSpec:
    start: float
    end: Optional[float]
    exact: bool

parse_time(text) -> Optional[float]
resolve_range(start_text, end_text, duration_text, mode) -> (Optional[ClipSpec], Optional[str])
clip_ffmpeg_args(spec) -> list[str]
```

- `parse_time` accepts `<seconds>` (`90`), `<mm>:<ss>` (`1:30`), and
  `<hh>:<mm>:<ss>` (`00:01:30`); trims whitespace; returns `None` for empty,
  junk, or a negative value.
- `resolve_range` is where the mode toggle lives. Mode `"end"` uses
  `end_text`; mode `"duration"` sets `end = start + duration`. An empty start
  returns `(None, None)` (no clip requested). Bad input (unparseable time, or
  `end <= start`) returns `(None, "<message>")`. A `None` end means clip to the
  end of the video.
- `clip_ffmpeg_args` returns the ffmpeg cut arguments: stream-copy
  (`-ss`, `-to`, `-c copy`, `-avoid_negative_ts make_zero`) or the exact-cut
  re-encode reusing the editor-safe `libx264`/`aac` flags.

### `core/download.py`

`download_one(url, outtmpl, output_type, convert, target_resolution, ...,
clip=None)`.

1. **Primary.** With a clip, pass yt-dlp `download_ranges` (the API form of
   `--download-sections`) so only the section is fetched. `exact=True` maps to
   yt-dlp's `force_keyframes_at_cuts`; `exact=False` leaves it off, which
   yt-dlp stream-copies at keyframes.
2. **Fallback.** If the section download raises, download the full file and cut
   it with ffmpeg via `clip_ffmpeg_args`.

Either path then runs the existing editor-safe guarantee
(`needs_universal_reencode`), so a clip is still H.264/AAC. The clipped file is
named `<base>_clip_<start>-<end>.<ext>` with whole-second times (`_clip_90-120`;
an open end is `_clip_90-end`), and the manifest points at it.

### `workers/download_worker.py`

`DownloadWorker(..., clip=None)` forwards it to `download_one`.

### `ui/single_tab.py`

A **Clip** checkbox under the download options. When ticked it reveals a mode
toggle (**Start + End** or **Start + Duration**), the **Start** field, the
**End**/**Duration** field (label follows the mode), an **Exact cut
(re-encode)** checkbox, and a hint: "Times like 90, 1:30, or 00:01:30. Leave
End empty to clip to the end."

`resolve_range` runs before the download starts; an error is shown through the
existing inline hint and blocks the start.

### `cli.py`

`download` gains `--start`, `--end`, `--duration`, and `--exact-cut`. Invalid
input exits `2` with a message, matching the CLI's existing usage-error
behavior.

### Queue

Unchanged, by decision: the Queue keeps passing `clip=None`.

## Testing

`tests/test_clip.py`:
- `parse_time`: `90`, `1:30`, `00:01:30`, empty, junk, negative, out-of-range.
- `resolve_range`: end mode, duration mode, empty start (no clip), end before
  start (error), open-ended end.
- `clip_ffmpeg_args`: stream-copy args versus exact args.

No tests for the yt-dlp section download or the real ffmpeg cut; those are
verified by hand, matching how the repo treats network and ffmpeg code.

## Risks

1. yt-dlp's section download is unreliable on some sites. The full-cut fallback
   covers it, at the cost of a full download for that run.
2. Stream-copy cuts snap to keyframes, so a clip may start up to a couple of
   seconds early. The Exact cut toggle fixes it and the hint says so.
3. A very long video with the fallback downloads fully; the primary path avoids
   that when it works.
4. Clipping an audio output cuts the audio; the cut applies before the MP3
   extraction, so the two compose.
