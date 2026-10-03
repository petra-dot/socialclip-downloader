# Editor-Compatibility Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guarantee every file this app produces imports into CapCut, Premiere Pro, After Effects, and DaVinci Resolve: H.264 video and editor-safe audio, for downloads and for every converter format.

**Architecture:** One contract enforced in three places. `core/formats.py` encodes editor-safe codecs and tightened remux allow-lists; `core/convert.py`'s `plan_conversion` transcodes anything editor-hostile (including forced copies); `core/download.py`'s post-download probe re-encodes any non-conforming MP4. A single contract test walks every format and every plan outcome.

**Tech Stack:** Python 3.8+, ffmpeg/ffprobe, PyQt5 (labels only), pytest. No new dependencies.

**Spec:** `docs/specs/2026-10-03-editor-compat-output-design.md`

## Global Constraints

- **Editor-safe codecs are the only outputs.** Video: `h264`. Audio: `aac`, `mp3`, `pcm_s16le`. Nothing else may appear as a `vcodec`/`acodec` in the registry or in any plan outcome.
- `core/` stays Qt-free (guarded by `tests/test_core_isolation.py`); the result contract `schema_version` stays `"1.0"`.
- **Remux copies only `h264` video.** Every video format's `remux_v == ("h264",)`.
- **Forced copy of an editor-hostile codec is upgraded to a transcode**, with a message. Ruling recorded in the spec.
- The three-format legacy convert path (`output_type` in MP3/WAV/MP4) stays byte-identical; its tests are the guard.
- `gif` is exempt from the video-codec rule (it is an image format with no audio); it keeps its existing palette recipe.
- Conventional Commits on a branch. All existing tests stay green (200 at plan time).

---

### Task 1: Lock the contract into the format registry

**Files:**
- Modify: `core/formats.py`
- Test: `tests/test_formats_editor_safe.py` (new)

**Interfaces:**
- Produces: `core.formats.EDITOR_SAFE_V = ("h264",)`, `core.formats.EDITOR_SAFE_A = ("aac", "mp3", "pcm_s16le")`, and the retuned `FORMATS` table.

**The audio-container conflict, resolved:** `ogg`, `opus`, and `wma` are
containers that cannot carry an editor-safe audio codec (Ogg Vorbis/Opus and
WMA are the only codecs those containers accept, and all three are rejected by
at least one of the four editors). The contract wins over the container:
**these three formats are removed.** A user who wants a small audio file has
`mp3`, `m4a`, and `aac`, all editor-safe. This is a deliberate reduction, not
an oversight.

- [ ] **Step 1: Write the failing contract test**

```python
from core.formats import EDITOR_SAFE_A, EDITOR_SAFE_V, FORMATS, for_kind, keys


def test_every_video_format_writes_h264():
    for f in for_kind("video"):
        if f.key == "gif":
            continue
        assert f.vcodec == "h264", (f.key, f.vcodec)


def test_every_format_writes_editor_safe_audio():
    for f in FORMATS:
        if f.key == "gif":
            continue
        assert f.acodec in EDITOR_SAFE_A, (f.key, f.acodec)


def test_every_video_format_only_remuxes_h264():
    for f in for_kind("video"):
        if f.key == "gif":
            continue
        assert f.remux_v == ("h264",), (f.key, f.remux_v)


def test_every_remux_audio_codec_is_editor_safe():
    for f in FORMATS:
        for codec in f.remux_a:
            assert codec in EDITOR_SAFE_A, (f.key, codec)


def test_webm_is_served_with_safe_codecs():
    webm = [f for f in FORMATS if f.key == "webm"][0]
    assert webm.vcodec == "h264"
    assert webm.acodec == "aac"


def test_editor_hostile_containers_are_removed():
    for gone in ("ogg", "opus", "wma"):
        assert gone not in keys(), gone


def test_safe_set_is_what_we_claim():
    assert EDITOR_SAFE_V == ("h264",)
    assert set(EDITOR_SAFE_A) == {"aac", "mp3", "pcm_s16le"}
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_formats_editor_safe.py -v`
Expected: FAIL (`EDITOR_SAFE_V` does not exist; webm still vp9/opus; ogg/opus/wma present).

- [ ] **Step 3: Retune `core/formats.py`**

- Add `EDITOR_SAFE_V = ("h264",)` and `EDITOR_SAFE_A = ("aac", "mp3", "pcm_s16le")`.
- Replace the `FORMATS` list with **exactly this table** (nothing to infer):

| key | label | kind | container | vcodec | acodec | ext | remux_v | remux_a |
|-----|-------|------|-----------|--------|--------|-----|---------|---------|
| `mp4` | `MP4 (H.264 + AAC)` | video | `mp4` | `h264` | `aac` | `mp4` | `("h264",)` | `("aac","mp3")` |
| `mkv` | `MKV (H.264 + AAC)` | video | `matroska` | `h264` | `aac` | `mkv` | `("h264",)` | `("aac","mp3")` |
| `webm` | `WebM (H.264 + AAC, editor-friendly)` | video | `webm` | `h264` | `aac` | `webm` | `("h264",)` | `("aac","mp3")` |
| `mov` | `MOV (H.264 + AAC)` | video | `mov` | `h264` | `aac` | `mov` | `("h264",)` | `("aac","pcm_s16le")` |
| `avi` | `AVI (H.264 + MP3)` | video | `avi` | `h264` | `mp3` | `avi` | `("h264",)` | `("mp3","pcm_s16le")` |
| `gif` | `GIF (no audio)` | video | `gif` | `gif` | `none` | `gif` | `()` | `()` |
| `mp3` | `MP3 (audio)` | audio | `mp3` | `` | `mp3` | `mp3` | `()` | `("mp3",)` |
| `m4a` | `M4A (AAC audio)` | audio | `ipod` | `` | `aac` | `m4a` | `()` | `("aac",)` |
| `wav` | `WAV (PCM audio)` | audio | `wav` | `` | `pcm_s16le` | `wav` | `()` | `("pcm_s16le",)` |
| `aac` | `AAC (audio)` | audio | `adts` | `` | `aac` | `aac` | `()` | `("aac",)` |

- **Remove** `ogg`, `opus`, `wma`, and `flac` entirely (see the audio-container
  conflict above).

- [ ] **Step 4: Run the contract test**

Run: `python -m pytest tests/test_formats_editor_safe.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Update the existing registry test that asserts the old list**

`tests/test_formats.py::test_curated_fourteen_present` names the 14 formats.
Update it to the new set (mp4, mkv, webm, mov, avi, gif, mp3, m4a, wav, aac) and
any other assertion naming a removed format.

Run: `python -m pytest tests/test_formats.py -v` — Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/formats.py tests/test_formats_editor_safe.py tests/test_formats.py
git commit -m "fix(formats): every output format writes editor-safe codecs"
```

---

### Task 2: Enforce the contract in the conversion planner

**Files:**
- Modify: `core/convert.py`
- Test: `tests/test_plan_conversion_editor.py` (new)

**Interfaces:**
- Consumes: `core.formats.Format`, `FORMATS`, `EDITOR_SAFE_A`, `EDITOR_SAFE_V`.
- Produces: `plan_conversion` never returns an editor-hostile codec, even for `copy_streams=True`.

- [ ] **Step 1: Write the failing tests**

```python
from core.convert import plan_conversion
from core.formats import EDITOR_SAFE_A, EDITOR_SAFE_V, for_kind, get

VIDEO_KEYS = [f.key for f in for_kind("video") if f.key != "gif"]


def test_no_plan_ever_emits_a_hostile_video_codec():
    for key in VIDEO_KEYS:
        for src_v in ("h264", "hevc", "vp9", "av1"):
            plan = plan_conversion({"vcodec": src_v, "acodec": "aac"}, get(key))
            if plan.vcodec and plan.vcodec != "copy":
                assert plan.vcodec in EDITOR_SAFE_V, (key, src_v, plan)


def test_no_plan_ever_emits_a_hostile_audio_codec():
    for key in VIDEO_KEYS + [f.key for f in for_kind("audio")]:
        for src_a in ("aac", "opus", "vorbis", "wmav2", "flac"):
            plan = plan_conversion({"vcodec": "h264", "acodec": src_a}, get(key))
            if plan.acodec and plan.acodec != "copy":
                assert plan.acodec in EDITOR_SAFE_A, (key, src_a, plan)


def test_hostile_video_source_transcodes():
    plan = plan_conversion({"vcodec": "vp9", "acodec": "aac"}, get("mp4"))
    assert plan.mode == "transcode"
    assert plan.vcodec == "h264"


def test_forced_copy_of_hostile_video_is_upgraded():
    """copy_streams=True must not hand back a VP9 file an editor rejects."""
    plan = plan_conversion({"vcodec": "vp9", "acodec": "aac"}, get("mp4"), copy_streams=True)
    assert plan.vcodec != "copy", plan
    assert plan.vcodec == "h264"


def test_forced_copy_of_safe_codecs_still_copies():
    plan = plan_conversion({"vcodec": "h264", "acodec": "aac"}, get("mkv"), copy_streams=True)
    assert plan.mode == "remux"
    assert plan.vcodec == "copy"


def test_forced_copy_of_hostile_audio_is_upgraded():
    plan = plan_conversion({"vcodec": "h264", "acodec": "opus"}, get("mp4"), copy_streams=True)
    assert plan.acodec != "copy", plan
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_plan_conversion_editor.py -v`
Expected: FAIL — forced copy currently returns `copy` for hostile codecs.

- [ ] **Step 3: Implement the upgrade in `plan_conversion`**

In `core/convert.py`, when `copy_streams is True`:
- copy video only if `src vcodec == "h264"` (and the target is video); otherwise
  set `vcodec = target.vcodec`.
- copy audio only if `src acodec in EDITOR_SAFE_A`; otherwise
  `acodec = target.acodec`.
- if either stream cannot be safely copied, the plan's mode is `"transcode"`
  (not `"remux"`), so the message reflects a re-encode.

For the auto path, `v_ok`/`a_ok` are already the allow-list checks; keep them.

Example shape:

```python
    if copy_streams is True:
        v_copy = v == "h264" if target.kind == "video" else True
        a_copy = a in EDITOR_SAFE_A
        if v_copy and a_copy:
            return ConvertPlan("remux", "copy" if target.kind == "video" else "",
                               "copy", target.container)
        return ConvertPlan("transcode", target.vcodec, target.acodec, target.container)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_plan_conversion_editor.py tests/test_plan_conversion.py -v`
Expected: PASS. Update `tests/test_plan_conversion.py`'s existing forced-copy
assertions if they assert the old behaviour (it asserted forced copy always
remuxes; that rule is now conditional on safety).

- [ ] **Step 5: Commit**

```bash
git add core/convert.py tests/test_plan_conversion_editor.py tests/test_plan_conversion.py
git commit -m "fix(convert): never copy an editor-hostile codec, even when forced"
```

---

### Task 3: Enforce the contract after every download

**Files:**
- Modify: `core/download.py`
- Test: `tests/test_download_editor_contract.py` (new)

**Interfaces:**
- Consumes: `core.formats.EDITOR_SAFE_A`.
- Produces: `needs_universal_reencode(src_info)` returns True for a hostile video **or** audio codec.

The existing helper checks only the video codec. Extend it, and confirm the
re-encode uses an editor-safe audio codec (it calls `_ffmpeg_to_nle_mp4`, which
already writes libx264 + aac).

- [ ] **Step 1: Write the failing tests**

```python
from core.download import needs_universal_reencode


def test_hostile_video_triggers_reencode():
    assert needs_universal_reencode({"vcodec": "vp9", "acodec": "aac"}) is True
    assert needs_universal_reencode({"vcodec": "hevc", "acodec": "aac"}) is True
    assert needs_universal_reencode({"vcodec": "av1", "acodec": "opus"}) is True


def test_hostile_audio_triggers_reencode():
    assert needs_universal_reencode({"vcodec": "h264", "acodec": "opus"}) is True
    assert needs_universal_reencode({"vcodec": "h264", "acodec": "vorbis"}) is True


def test_safe_pair_is_left_alone():
    assert needs_universal_reencode({"vcodec": "h264", "acodec": "aac"}) is False
    assert needs_universal_reencode({"vcodec": "h264", "acodec": "mp3"}) is False


def test_unknown_is_reencoded():
    assert needs_universal_reencode({"vcodec": "", "acodec": ""}) is True
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_download_editor_contract.py -v`
Expected: FAIL on the hostile-audio cases (only video is checked today).

- [ ] **Step 3: Extend `needs_universal_reencode`**

```python
from core.formats import EDITOR_SAFE_A


def needs_universal_reencode(src_info: dict) -> bool:
    """True when a saved MP4 is not H.264 video + editor-safe audio."""
    info = src_info or {}
    vcodec = (info.get("vcodec") or "").lower()
    acodec = (info.get("acodec") or "").lower()
    if vcodec != "h264":
        return True
    # An absent audio codec is fine (silent video); a present hostile one is not.
    if acodec and acodec not in EDITOR_SAFE_A:
        return True
    return False
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_download_editor_contract.py tests/test_universal_reencode.py -v`
Expected: PASS. Reconcile `tests/test_universal_reencode.py` if it asserts the
old audio-agnostic behaviour.

- [ ] **Step 5: Commit**

```bash
git add core/download.py tests/test_download_editor_contract.py tests/test_universal_reencode.py
git commit -m "fix(download): re-encode hostile audio as well as video"
```

---

### Task 4: The single contract test

**Files:**
- Test: `tests/test_editor_contract.py` (new)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the all-paths contract test**

```python
"""One test that walks every format and every plan outcome and asserts no
editor-hostile codec can ever be produced."""

from core.convert import plan_conversion
from core.formats import EDITOR_SAFE_A, EDITOR_SAFE_V, FORMATS, for_kind

SOURCE_CODECS_V = ("h264", "hevc", "vp9", "av1", "")
SOURCE_CODECS_A = ("aac", "mp3", "opus", "vorbis", "wmav2", "flac", "")


def test_no_produced_codec_is_editor_hostile():
    bad = []
    for f in FORMATS:
        for sv in SOURCE_CODECS_V:
            for sa in SOURCE_CODECS_A:
                for copy in (None, True, False):
                    plan = plan_conversion(
                        {"vcodec": sv, "acodec": sa}, f, copy_streams=copy
                    )
                    if plan.vcodec and plan.vcodec != "copy":
                        if plan.vcodec not in EDITOR_SAFE_V:
                            bad.append((f.key, sv, sa, copy, "v", plan.vcodec))
                    if plan.acodec and plan.acodec != "copy":
                        if plan.acodec not in EDITOR_SAFE_A:
                            bad.append((f.key, sv, sa, copy, "a", plan.acodec))
    assert not bad, bad[:20]


def test_registry_itself_only_names_safe_codecs():
    for f in FORMATS:
        if f.key == "gif":
            continue
        assert f.vcodec in EDITOR_SAFE_V or f.vcodec == "", f.key
        assert f.acodec in EDITOR_SAFE_A, f.key
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/test_editor_contract.py -v`
Expected: PASS once Tasks 1-3 are done. If it fails, the failure names the exact
`(format, source, copy, stream, codec)` tuple to fix.

- [ ] **Step 3: Commit**

```bash
git add tests/test_editor_contract.py
git commit -m "test: one contract test for editor-safe output across all paths"
```

---

### Task 5: UI labels and docs

**Files:**
- Modify: `ui/convert_tab.py`, `README.md`, `CHANGELOG.md`

- [ ] **Step 1: GUI**

The Convert tab combo is built from the registry, so removed formats disappear
automatically and the new labels show. Verify headlessly:

```bash
python -c "
import os; os.environ['QT_QPA_PLATFORM']='offscreen'
from PyQt5 import QtWidgets
app = QtWidgets.QApplication([])
from ui.convert_tab import ConvertTab
t = ConvertTab()
keys = [t.conv_output_combo.itemData(i) for i in range(t.conv_output_combo.count())]
print('formats:', keys)
assert 'ogg' not in keys and 'opus' not in keys and 'wma' not in keys
assert 'webm' in keys
print('OK')
"
```

- [ ] **Step 2: README**

Replace the convert format list with the new set and state the guarantee:
every output is H.264 + AAC/MP3/PCM so it imports into CapCut, Premiere Pro,
After Effects, and DaVinci Resolve.

- [ ] **Step 3: CHANGELOG**

Add to the unreleased/v0.9 section: editor-safe output contract; `ogg`, `opus`,
`wma`, `flac` removed (containers/codecs the four editors reject); `webm`
now written as H.264/AAC; downloads re-encode non-conforming sources.

- [ ] **Step 4: Verify and commit**

Run: `python -m pytest -q` and `python -m flake8 . --count --select=E9,F63,F7,F82 --statistics`

```bash
git add ui/convert_tab.py README.md CHANGELOG.md
git commit -m "docs: editor-safe output contract, updated format list"
```

---

## Self-Review

**Spec coverage:** safe-codec registry -> Task 1; planner enforcement incl.
forced-copy upgrade -> Task 2; post-download enforcement incl. audio -> Task 3;
the single contract test the spec demands -> Task 4; labels + docs -> Task 5.

**Type consistency:** `EDITOR_SAFE_V`/`EDITOR_SAFE_A` are defined in Task 1 and
consumed in Tasks 2, 3, 4. `needs_universal_reencode` keeps its name and gains
the audio check in Task 3 (Task 4 does not depend on it directly).

**Deliberate reductions called out:** `ogg`, `opus`, and `wma` are removed
because their containers cannot carry an editor-safe codec; `flac` is removed
because After Effects does not accept it. These are product decisions recorded
here, not oversights. The remaining audio outputs are `mp3`, `m4a`, `wav`, `aac`.

**Deferred:** a future "streaming/archive" mode that intentionally keeps VP9/Opus
for users who want the original codecs. Out of scope for the guarantee.
