# Editing-Compatible Output Contract — Design

Status: proposed
Date: 2026-10-03
Applies to: download pipeline and the converter (`core/download.py`,
`core/convert.py`, `core/formats.py`)

## Problem

Users edit what they download. The four mainstream editors — **CapCut,
Adobe Premiere Pro, Adobe After Effects, and DaVinci Resolve** — accept a
narrow set of codecs relably and reject or struggle with others:

| Codec | CapCut | Premiere/AE | DaVinci | Verdict |
|-------|--------|-------------|---------|---------|
| **H.264 video** | yes | yes | yes | safe |
| HEVC/H.265 video | partial | recent only | yes (Studio for some) | unsafe |
| VP9 / AV1 video | no | partial | partial | unsafe |
| ProRes / DNxHR | partial | yes | yes (Studio) | pro-only |
| **AAC audio** | yes | yes | yes | safe |
| MP3 audio | yes | yes | yes | safe |
| PCM audio | yes | yes | yes | safe |
| Opus / Vorbis audio | no | partial | **no** (Opus) | unsafe |
| WMA audio | no | partial | no | unsafe |

Two failures follow:

1. **Downloads** can hand back a file whose codec an editor rejects. A file
   this app downloaded was probed and found to be VP9-in-MP4 — rejected by
   WhatsApp/Facebook and by Premiere/CapCut. The app's own default output must
   never be like that.
2. **The converter lets the user ask for a container whose natural codec is
   editor-hostile** (`webm` = VP9/Opus, `ogg` = Vorbis, `opus`, `wma`), and
   `remux` can copy an editor-hostile source codec into `mkv`/`mov` unchanged.

The user experience this produces is the worst kind: an edit session that
cannot import the clip, with no clue why.

## Goal

**Every video/audio file this app produces must import into CapCut, Premiere
Pro, After Effects, and DaVinci Resolve without a codec error, and must play on
WhatsApp, Facebook, and Instagram.**

Where a container's "native" codec is editor-hostile, we output an
editor-safe codec in that container instead (containers are forgiving; the
codec is what matters).

## Non-goals

- Matching every niche codec an editor *might* accept.
- Pro-only interchange formats (ProRes/DNxHD) as user-facing outputs.
- Changing the existing result contract (`schema_version` `"1.0"`).

## Decisions taken

- **Editor-safe is the contract.** Output is H.264 video and AAC/MP3/PCM audio,
  always, for every format that carries that stream type.
- **Formats keep their identity; codecs change** where that is possible. The
  WebM muxer only accepts VP8/VP9/AV1 video and Vorbis/Opus audio, all
  editor-hostile, so an editor-safe WebM cannot be produced and `webm` is
  removed rather than mislabeled. Where the standards conflict, the editor
  contract wins.
- **Remux is only allowed when the source codec is already editor-safe.** A
  VP9/HEVC/AV1 source is transcoded to H.264 rather than copied.
- **One shared rule table**, not scattered `if`s.

## Architecture

### `core/formats.py` — add an editor-safety axis

```python
# Codecs an editor reliably accepts.
EDITOR_SAFE_V = ("h264",)
EDITOR_SAFE_A = ("aac", "mp3", "pcm_s16le")

@dataclass(frozen=True)
class Format:
    key: str
    label: str
    kind: str
    container: str
    vcodec: str          # the codec we always write (editor-safe)
    acodec: str          # the codec we always write (editor-safe)
    extension: str
    remux_v: tuple       # source vcodecs safe to copy into this container
    remux_a: tuple       # source acodecs safe to copy into this container
```

No `editor_safe` flag is added: after this change every format is editor-safe
by construction (its `vcodec`/`acodec` come from the safe sets), so a flag
that is always `True` would be dead weight. The contract is enforced by the
invariant tests instead.

Rules encoded in the table:

- **Every video format's `vcodec` is `h264`** and `acodec` is `aac`
  (the container may differ; the codec does not).
- **`remux_v` is `("h264",)` for every video format.** Copying HEVC/VP9/AV1
  into any container can produce a file an editor rejects, so remux is only
  offered when the source is already H.264.
- **`remux_a` may include opus/vorbis/flac only if the target's `acodec` is
  overridden** — simpler: `remux_a` is limited to editor-safe audio
  (`aac`, `mp3`, `pcm_s16le`). Editor-hostile audio is transcoded.
- `editor_safe` is not added; every format is editor-safe by construction.

### `core/convert.py`

- `plan_conversion`: remux only when `source_vcodec in target.remux_v` AND
  `source_acodec in target.remux_a`; otherwise transcode to the format's
  editor-safe codec pair. This already exists; the change is the tightened
  allow-lists.
- **Forced copy (`copy_streams=True`) is upgraded to a transcode when the
  source codec is editor-hostile.** Ruling: a user asking to "copy streams"
  wants speed, but not at the cost of a file their editor rejects. The result
  message states the upgrade ("Re-encoded for editor compatibility"). An
  explicit copy of an already-safe codec still copies.
- The vcodec written is always `h264` for a video target and the acodec is
  always editor-safe.

### `core/download.py`

The existing post-download guarantee (probe the saved file; re-encode if the
video codec is not H.264) becomes the **single enforcement point** for the
download path and is extended to also check the audio codec:

- if `vcodec != "h264"` **or** `acodec not in EDITOR_SAFE_A`: re-encode to
  H.264 + AAC.
- This runs for every MAINSTREAM platform (YouTube, TikTok, Instagram,
  Facebook, Twitter/X, Bilibili, Douyin, and anything else yt-dlp returns),
  because it is applied to whatever the site delivered rather than assumed
  from the site name.

### UI and CLI

- The Convert tab labels each format and shows its output codecs; no format
  is marked "not for editing" because all are editor-safe after this change.
- Formats whose *name* implies a codec are labeled with the codec actually
  written (for example `AVI (H.264 + MP3)`), so users know the codec before
  they choose the container.

## The universal guarantee (what "mainstream" means here)

The download guarantee is **codec-based, not site-based**: whatever yt-dlp
extracts, the post-download probe decides. That covers every site uniformly,
so a new platform cannot reintroduce the bug. This is deliberately chosen over
per-site logic, which would rot as sites change.

## Error handling

- A forced remux that would copy an editor-hostile codec is upgraded to a
  transcode and the result message says so ("Re-encoded for editor
  compatibility").
- A re-encode that fails returns `error_result("ffmpeg", ...)` and removes the
  partial output (already implemented).
- A source with no audio stream re-encodes video only; the missing audio is
  not an error.

## Testing

- **Registry invariants** (pytest): every video format's `vcodec == "h264"`;
  every format's `acodec` is editor-safe; every `remux_v` is `("h264",)`;
  every `remux_a` is editor-safe.
- **`plan_conversion`**: a VP9/HEVC/AV1/Opus source transcribes to H.264/AAC
  for every video target; a forced copy of an editor-hostile codec is upgraded.
- **`download_one`**: a VP9-in-MP4 download is re-encoded to H.264/AAC; an
  Opus-audio MP4 is re-encoded; an already-H.264/AAC file is left untouched.
- **A "no editor-hostile output" test** that walks every `Format` and every
  `plan_conversion` outcome and asserts no produced codec is outside the
  editor-safe set. This is the contract test.
- Existing tests stay green; the three-format legacy path is untouched.

## Risks

- **Cost**: editor-safe output means VP9/AV1/Opus sources are always
  re-encoded, which takes time and loses a little quality. Accepted: a file an
  editor can open is the point.
- **`webm` is removed, not emulated.** WebM's muxer accepts only editor-hostile
  codecs, so there is no editor-safe WebM to offer. A user who wants real VP9
  can be served later via an explicit "streaming" option if demand appears.
- **HEVC sources now always transcode.** Correct for compatibility; slower.
