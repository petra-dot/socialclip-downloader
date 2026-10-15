# Subtitle Downloads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch a video's subtitles and save them as sidecar `.srt` files, embed them as tracks, or both, selectable per download, from the Download tab, the Queue, and the CLI.

**Architecture:** A Qt-free `core/subtitles.py` selects tracks from the yt-dlp `info` dict (pure), fetches and writes each as a distinct sidecar (manual `<base>.<lang>.srt`, auto `<base>.<lang>.auto.srt`), and muxes sidecars into the video for the embed delivery. `core/download.download_one`'s dead `subtitles` parameter becomes a delivery value. The two tabs and the CLI pass it.

**Tech Stack:** Python 3.8+, PyQt5, yt-dlp info dicts, ffmpeg, pytest. No new dependencies.

**Spec:** `docs/specs/2026-10-15-subtitles-design.md`

## Global Constraints

- `core/` must not import PyQt5. Enforced by `tests/test_core_isolation.py`.
- No new runtime dependencies.
- Delivery values are exactly `off`, `sidecar`, `embed`, `both`; default `off`.
- Manual and auto tracks get distinct filenames (`<base>.<lang>.srt`, `<base>.<lang>.auto.srt`); never delegate naming to yt-dlp.
- Track formats are limited to `srt` and `vtt`; anything else is skipped.
- The embed mux writes to a temp name and replaces the video only on success.
- The download result contract stays `schema_version` `"1.0"`.
- All existing tests stay green (`python -m pytest -q`); flake8 `--select=E9,F63,F7,F82` prints `0`.
- Conventional Commits. Never push without asking.

## File Structure

- `core/subtitles.py` (new) — `SubtitleTrack`, `DELIVERIES`, `subtitle_tracks` (pure), `write_subtitle`, `embed_command` (pure), `embed_subtitles`.
- `core/download.py` (modify) — the `subtitles` delivery integration.
- `workers/download_worker.py`, `workers/queue_worker.py` (modify) — forward `subtitles`.
- `ui/single_tab.py`, `ui/batch_tab.py` (modify) — the Subtitles combo; `build_job_options` gains `subtitles`.
- `cli.py` (modify) — `--subtitles`, and the queue executor forwards it.
- `tests/test_subtitles.py` (new).
- `README.md`, `CHANGELOG.md`, `AGENTS.md` (modify).

---

### Task 1: Track selection

**Files:**
- Create: `core/subtitles.py`
- Test: `tests/test_subtitles.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `SubtitleTrack(lang, kind, url, ext)`; `DELIVERIES = ("off", "sidecar", "embed", "both")`; `subtitle_tracks(info) -> List[SubtitleTrack]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_subtitles.py`:

```python
from core.subtitles import DELIVERIES, SubtitleTrack, subtitle_tracks


def test_deliveries_values():
    assert DELIVERIES == ("off", "sidecar", "embed", "both")


def test_subtitle_tracks_prefers_srt_and_keeps_both_kinds():
    info = {
        "subtitles": {
            "en": [{"ext": "vtt", "url": "u-en-vtt"},
                   {"ext": "srt", "url": "u-en-srt"}],
        },
        "automatic_captions": {
            "en": [{"ext": "vtt", "url": "u-en-auto"}],
            "fr": [{"ext": "vtt", "url": "u-fr"}],
        },
    }
    tracks = subtitle_tracks(info)
    manual_en = [t for t in tracks if t.lang == "en" and t.kind == "manual"][0]
    assert manual_en.url == "u-en-srt"
    assert manual_en.ext == "srt"
    auto_en = [t for t in tracks if t.lang == "en" and t.kind == "auto"][0]
    assert auto_en.url == "u-en-auto"
    assert any(t.lang == "fr" and t.kind == "auto" for t in tracks)


def test_subtitle_tracks_skips_unusable_formats():
    info = {"subtitles": {"de": [{"ext": "json3", "url": "u"}],
                          "es": [{"ext": "vtt"}]}}
    assert subtitle_tracks(info) == []


def test_subtitle_tracks_empty_info():
    assert subtitle_tracks({}) == []
    assert subtitle_tracks(None) == []


def test_subtitle_track_is_a_dataclass():
    track = SubtitleTrack(lang="en", kind="manual", url="u", ext="srt")
    assert track.lang == "en" and track.kind == "manual"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_subtitles.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.subtitles'`

- [ ] **Step 3: Write minimal implementation**

Create `core/subtitles.py`:

```python
"""Fetch a video's subtitles as sidecar .srt files, or embed them.

Pure selection helpers plus network and ffmpeg work. No Qt.
"""

import os
import subprocess
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

from utils.ffmpeg import ffmpeg_path

DELIVERIES = ("off", "sidecar", "embed", "both")

# A track is usable only if it offers one of these; an srt is written as-is, a
# vtt is converted. json3/srv sources would need their own parser.
_FORMAT_ORDER = ("srt", "vtt")


@dataclass
class SubtitleTrack:
    lang: str
    kind: str        # "manual" | "auto"
    url: str
    ext: str


def _pick_format(formats):
    for wanted in _FORMAT_ORDER:
        for fmt in formats or []:
            if fmt.get("ext") == wanted and fmt.get("url"):
                return fmt["url"], wanted
    return None


def subtitle_tracks(info) -> List[SubtitleTrack]:
    """Manual and auto tracks from a yt-dlp info dict, srt preferred over vtt."""
    info = info or {}
    tracks: List[SubtitleTrack] = []
    for key, kind in (("subtitles", "manual"), ("automatic_captions", "auto")):
        for lang, formats in (info.get(key) or {}).items():
            picked = _pick_format(formats)
            if not picked:
                continue
            url, ext = picked
            tracks.append(SubtitleTrack(lang=lang, kind=kind, url=url, ext=ext))
    return tracks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_subtitles.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/subtitles.py tests/test_subtitles.py
git commit -m "feat(subtitles): select manual and auto tracks from the video info"
```

---

### Task 2: Fetch, write, and embed

**Files:**
- Modify: `core/subtitles.py`
- Test: `tests/test_subtitles.py` (extend)

**Interfaces:**
- Consumes: Task 1 (`SubtitleTrack`).
- Produces: `write_subtitle(track, base_path, opener=None) -> Optional[str]`; `embed_command(video_path, subtitles, out_path, ffmpeg="ffmpeg") -> list[str]`; `embed_subtitles(video_path, subtitles) -> bool` (`subtitles` is a list of `(lang, path)`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_subtitles.py`:

```python
from core.subtitles import embed_command, write_subtitle


def test_embed_command_maps_and_tags_languages():
    cmd = embed_command("v.mp4", [("en", "en.srt"), ("fr", "fr.srt")], "out.mp4")
    assert cmd[cmd.index("-c:s") + 1] == "mov_text"
    assert "language=en" in cmd and "language=fr" in cmd
    assert cmd.count("-map") == 3          # 0 plus the two sidecar streams
    assert cmd[-1] == "out.mp4"


def test_embed_command_single_track():
    cmd = embed_command("v.mp4", [("en", "en.srt")], "out.mp4")
    assert cmd.count("-map") == 2
    assert "language=en" in cmd


def test_write_subtitle_writes_manual_and_auto_names(tmp_path):
    class Response:
        def __init__(self, body):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self._body

    base = str(tmp_path / "Video")
    manual = SubtitleTrack("en", "manual", "u1", "srt")
    auto = SubtitleTrack("en", "auto", "u2", "srt")
    opener = lambda req, timeout=None: Response(b"1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    assert write_subtitle(manual, base, opener=opener).endswith("Video.en.srt")
    assert write_subtitle(auto, base, opener=opener).endswith("Video.en.auto.srt")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_subtitles.py -v`
Expected: FAIL with `ImportError: cannot import name 'embed_command'`

- [ ] **Step 3: Write minimal implementation**

Append to `core/subtitles.py`:

```python
def _dest_for(track: SubtitleTrack, base_path: str) -> str:
    suffix = ".auto" if track.kind == "auto" else ""
    return "%s.%s%s.srt" % (base_path, track.lang, suffix)


def write_subtitle(track, base_path, opener=None) -> Optional[str]:
    """Fetch a track and write its sidecar. Returns the path, or None."""
    dest = _dest_for(track, base_path)
    open_url = opener or urllib.request.urlopen
    try:
        request = urllib.request.Request(
            track.url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with open_url(request, timeout=30) as response:
            data = response.read()
    except Exception:  # noqa: BLE001 - a missing subtitle must not fail the download
        return None

    if track.ext == "srt":
        with open(dest, "wb") as fh:
            fh.write(data)
        return dest

    tmp = dest + ".vtt"
    with open(tmp, "wb") as fh:
        fh.write(data)
    try:
        result = subprocess.run(
            [ffmpeg_path(), "-y", "-i", tmp, dest],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return dest if result.returncode == 0 else None


def embed_command(video_path, subtitles, out_path, ffmpeg="ffmpeg") -> list:
    """ffmpeg args to mux (lang, path) sidecars into the video as mov_text."""
    cmd = [ffmpeg, "-y", "-i", video_path]
    for _lang, path in subtitles:
        cmd += ["-i", path]
    cmd += ["-map", "0"]
    for index in range(len(subtitles)):
        cmd += ["-map", str(index + 1)]
    cmd += ["-c", "copy", "-c:s", "mov_text"]
    for index, (lang, _path) in enumerate(subtitles):
        cmd += ["-metadata:s:s:%d" % index, "language=%s" % lang]
    cmd += [out_path]
    return cmd


def embed_subtitles(video_path, subtitles) -> bool:
    """Mux the sidecars into the video, replacing it only on success."""
    if not subtitles:
        return True
    base, ext = os.path.splitext(video_path)
    out = base + ".subs" + ext
    result = subprocess.run(
        embed_command(video_path, subtitles, out, ffmpeg=ffmpeg_path()),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        try:
            os.remove(out)
        except OSError:
            pass
        return False
    os.replace(out, video_path)
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_subtitles.py -v`
Expected: PASS

- [ ] **Step 5: Verify core isolation**

Run: `python -m pytest tests/test_core_isolation.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core/subtitles.py tests/test_subtitles.py
git commit -m "feat(subtitles): write sidecars and embed them into the video"
```

---

### Task 3: The download integration

**Files:**
- Modify: `core/download.py`

**Interfaces:**
- Consumes: `subtitle_tracks`, `write_subtitle`, `embed_subtitles` (Tasks 1-2).
- Produces: `download_one(..., subtitles="off")` where the value is a `DELIVERIES` member.

- [ ] **Step 1: Change the parameter and add the step**

In `core/download.py`, change the signature's `subtitles=False` to `subtitles="off"`:

```python
def download_one(url, outtmpl, output_type, convert, target_resolution,
                 cookies_file=None, progress=None, cancel=None,
                 subtitles="off", embed_thumbnail=False, format_id=None,
                 clip=None):
```

After the editor-safe block (the `reencoded` computation, before the `if reencoded:` message chain), add:

```python
        if subtitles and subtitles != "off" and os.path.isfile(final_path):
            from core.subtitles import (
                embed_subtitles, subtitle_tracks, write_subtitle,
            )

            base = os.path.splitext(final_path)[0]
            sidecars = []
            for track in subtitle_tracks(info):
                written = write_subtitle(track, base)
                if written:
                    sidecars.append((track.lang, written))
            if subtitles in ("embed", "both") and sidecars:
                embed_subtitles(final_path, sidecars)
            if subtitles == "embed":
                for _lang, path in sidecars:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
```

- [ ] **Step 2: Verify it compiles and lints**

Run: `python -m py_compile core/download.py` then `python -m flake8 core/download.py --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: `0`

- [ ] **Step 3: Verify the full suite and core isolation**

Run: `python -m pytest -q` then `python -m pytest tests/test_core_isolation.py -v`
Expected: all pass (the existing `download_one` tests pass `subtitles` implicitly as `"off"`)

- [ ] **Step 4: Commit**

```bash
git add core/download.py
git commit -m "feat(download): fetch, save, or embed subtitles per delivery"
```

---

### Task 4: Forward subtitles through the workers

**Files:**
- Modify: `workers/download_worker.py`, `workers/queue_worker.py`, `cli.py` (the queue executor)

**Interfaces:**
- Consumes: `download_one(..., subtitles=)` (Task 3).
- Produces: `DownloadWorker(..., subtitles="off")`; the queue executor reads `opts.get("subtitles", "off")`.

- [ ] **Step 1: Download worker**

In `workers/download_worker.py`, add `subtitles="off"` to `DownloadWorker.__init__`, store `self.subtitles = subtitles`, and pass `subtitles=self.subtitles` in the `download_one(...)` call in `run()`.

- [ ] **Step 2: Queue worker**

In `workers/queue_worker.py` `_executor`, add `subtitles=opts.get("subtitles", "off"),` to the `download_one(...)` call.

- [ ] **Step 3: CLI queue executor**

In `cli.py` `_queue_executor`, add `subtitles=opts.get("subtitles", "off"),` to its `download_one(...)` call.

- [ ] **Step 4: Verify it compiles and lints**

Run: `python -m py_compile workers/download_worker.py workers/queue_worker.py cli.py` then `python -m flake8 workers cli.py --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: `0`

- [ ] **Step 5: Run the suite**

Run: `python -m pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add workers/download_worker.py workers/queue_worker.py cli.py
git commit -m "feat(workers): forward the subtitle delivery"
```

---

### Task 5: The UI combos

**Files:**
- Modify: `ui/single_tab.py`, `ui/batch_tab.py`

**Interfaces:**
- Consumes: `DELIVERIES` (Task 1); `DownloadWorker(..., subtitles=)` (Task 4).
- Produces: `self.subtitle_combo` (Download) and `self.batch_subtitle_combo` (Queue); `build_job_options` gains a `subtitles` field.

- [ ] **Step 1: Download tab**

In `ui/single_tab.py`, in `init_ui`, add a Subtitles row (after the filename checkboxes, before the save-folder row):

```python
        sub_row = QtWidgets.QHBoxLayout()
        sub_row.addWidget(QtWidgets.QLabel("Subtitles:"))
        self.subtitle_combo = QtWidgets.QComboBox()
        self.subtitle_combo.setAccessibleName("Subtitle delivery")
        for value, label in (
            ("off", "Off"), ("sidecar", "Sidecar (.srt)"),
            ("embed", "Embed"), ("both", "Both"),
        ):
            self.subtitle_combo.addItem(label, value)
        sub_row.addWidget(self.subtitle_combo)
        sub_row.addStretch(1)
        main.addLayout(sub_row)
```

In `on_download`, pass it to the worker:

```python
        self.worker = DownloadWorker(
            url, final_outtmpl, convert, target_resolution, output_type,
            cookies_file=self._get_cookies_path(),
            subtitles=self.subtitle_combo.currentData(),
        )
```

- [ ] **Step 2: Queue tab**

In `ui/batch_tab.py`, extend `build_job_options`:

```python
def build_job_options(save_dir: str, output_text: str, resolution: str,
                      cookies_path: str, subtitles: str = "off") -> dict:
    output_type = "MP3" if "MP3" in output_text else "MP4"
    return {
        "outtmpl": os.path.join(save_dir, "%(title)s.%(ext)s"),
        "output_type": output_type,
        "convert": output_type == "MP4",
        "target_resolution": int(resolution),
        "cookies_file": cookies_path,
        "subtitles": subtitles,
    }
```

In `init_ui`, add a Subtitles row after the cookies row:

```python
        sub_row = QtWidgets.QHBoxLayout()
        sub_row.addWidget(QtWidgets.QLabel("Subtitles:"))
        self.batch_subtitle_combo = QtWidgets.QComboBox()
        self.batch_subtitle_combo.setAccessibleName("Queue subtitle delivery")
        for value, label in (
            ("off", "Off"), ("sidecar", "Sidecar (.srt)"),
            ("embed", "Embed"), ("both", "Both"),
        ):
            self.batch_subtitle_combo.addItem(label, value)
        sub_row.addWidget(self.batch_subtitle_combo)
        sub_row.addStretch(1)
        queue_layout.addLayout(sub_row)
```

In `_job_options`, pass the value:

```python
        return build_job_options(
            save_dir,
            self.batch_output_combo.currentText(),
            self.batch_resolution_combo.currentText(),
            self._batch_get_cookies_path(),
            self.batch_subtitle_combo.currentData(),
        )
```

- [ ] **Step 3: Verify it compiles and lints**

Run: `python -m py_compile ui/single_tab.py ui/batch_tab.py` then `python -m flake8 ui/single_tab.py ui/batch_tab.py --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: `0`

- [ ] **Step 4: Verify offscreen**

Run:

```bash
python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PyQt5 import QtWidgets, QtCore; app=QtWidgets.QApplication([]); app.setOrganizationName('petra-dot'); app.setApplicationName('SocialClip Downloader'); QtCore.QSettings().setValue('first_run_done', True); from ui.batch_tab import QueueTab, build_job_options; t=QueueTab({'path':''}); opts=build_job_options('/tmp','Video (MP4)','1080','','both'); print('combo', t.batch_subtitle_combo.count(), 'opts', opts['subtitles'])"
```

Expected: `combo 4 opts both`

- [ ] **Step 5: Commit**

```bash
git add ui/single_tab.py ui/batch_tab.py
git commit -m "feat(ui): subtitle delivery combo on both tabs"
```

---

### Task 6: CLI `--subtitles`

**Files:**
- Modify: `cli.py`
- Test: `tests/test_cli.py` (extend)

**Interfaces:**
- Consumes: `DELIVERIES` (Task 1); `download_one(..., subtitles=)` (Task 3).
- Produces: `download --subtitles {off,sidecar,embed,both}`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_download_rejects_unknown_subtitle_delivery(monkeypatch, capsys):
    import cli
    monkeypatch.setattr(cli, "_ytdlp_missing", lambda: False)
    monkeypatch.setattr(cli, "_ffmpeg_missing", lambda: False)
    rc = cli.main(["download", "https://youtu.be/x", "--subtitles", "burn"])
    assert rc == 2
    assert "invalid choice" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py::test_download_rejects_unknown_subtitle_delivery -v`
Expected: FAIL (unknown argument `--subtitles`)

- [ ] **Step 3: Write minimal implementation**

In `cli.py`, add to the `download` parser:

```python
    d.add_argument("--subtitles", choices=list(DELIVERIES), default="off")
```

Add the import near the top of `cli.py`:

```python
from core.subtitles import DELIVERIES
```

In `_cmd_download`, pass it to `download_one`:

```python
        subtitles=args.subtitles,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS (argparse rejects an out-of-choices value with exit 2 and an "invalid choice" message; an unknown-flag error would say "unrecognized arguments" instead, so the assertion discriminates)

- [ ] **Step 5: Verify the full suite and lint**

Run: `python -m pytest -q` then `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: all pass; `0`

- [ ] **Step 6: Commit**

```bash
git add cli.py tests/test_cli.py
git commit -m "feat(cli): --subtitles delivery flag"
```

---

### Task 7: Documentation

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `AGENTS.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing code-facing.

- [ ] **Step 1: README**

Add a short subtitle note under the download features: Off / Sidecar / Embed / Both, all available languages, manual and auto kept separately, plus the CLI `--subtitles`.

- [ ] **Step 2: CHANGELOG**

Under `## Unreleased`, add `### Added` for subtitle downloads.

- [ ] **Step 3: AGENTS.md**

Add `core/subtitles.py` to the layout list and one line: subtitles are fetched from the video `info` and written as sidecars (manual `<base>.<lang>.srt`, auto `<base>.<lang>.auto.srt`), never delegated to yt-dlp naming.

- [ ] **Step 4: Commit**

```bash
git add README.md CHANGELOG.md AGENTS.md
git commit -m "docs: subtitle downloads"
```

---

## Self-Review

- **Spec coverage:** track selection (Task 1), fetch/write/embed (Task 2), download integration with the delivery table (Task 3), worker + queue + CLI-executor forwarding (Task 4), both-tab combos and `build_job_options` (Task 5), CLI flag (Task 6), docs (Task 7). The distinct manual/auto naming is `_dest_for` (Task 2). The temp-then-replace embed is `embed_subtitles` (Task 2).
- **Placeholder scan:** no TBD/TODO; every code step carries real code.
- **Type consistency:** `SubtitleTrack(lang, kind, url, ext)` identical across Tasks 1, 2, 5; `subtitle_tracks(info)` and `write_subtitle(track, base_path, opener=)` match their call sites; `embed_subtitles(video_path, subtitles)` takes `(lang, path)` pairs everywhere; `DELIVERIES` is the single source for the combo and the CLI choices; `DownloadWorker(..., subtitles=)` matches Task 5's call.
- **Known nuance:** the Queue's `build_job_options` now carries `subtitles`; the CLI queue executor and `workers/queue_worker.py` both read it, so the GUI queue and the CLI queue agree. The `embed_thumbnail` dead parameter stays dead (out of scope).
