# Clip Downloads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Download only a requested time range from a video, from the Download tab and the CLI, lossless by default and frame-accurate on request, still editor-safe.

**Architecture:** A Qt-free `core/clip.py` holds the pure time parsing and ffmpeg cut arguments. `core/download.download_one` gains a `clip` parameter: it first asks yt-dlp for only the section, and if that fails, downloads the full file and cuts it with ffmpeg. The Download tab and the CLI build a `ClipSpec` and pass it down.

**Tech Stack:** Python 3.8+, PyQt5, yt-dlp (`download_ranges`), ffmpeg, pytest. No new dependencies.

**Spec:** `docs/specs/2026-10-15-clip-downloads-design.md`

## Global Constraints

- `core/` must not import PyQt5. Enforced by `tests/test_core_isolation.py`.
- No new runtime dependencies.
- The editor-safe guarantee still runs on the clipped result (`needs_unreencode` path in `download_one`).
- The clipped file is named `<base>_clip_<start>-<end>.<ext>` with whole seconds; an open end is `_clip_<start>-end`.
- The download result contract stays `schema_version` `"1.0"`.
- All existing tests stay green (`python -m pytest -q`); flake8 `--select=E9,F63,F7,F82` prints `0`.
- Conventional Commits. Never push without asking.

## File Structure

- `core/clip.py` (new) — `ClipSpec`, `parse_time`, `resolve_range`, `clip_ffmpeg_args`. Pure.
- `core/download.py` (modify) — `_clip_name`, `_cut_file`, and the `clip` parameter with section-then-fallback.
- `workers/download_worker.py` (modify) — forward `clip`.
- `ui/single_tab.py` (modify) — the Clip controls.
- `cli.py` (modify) — `--start/--end/--duration/--exact-cut`.
- `tests/test_clip.py` (new).
- `README.md`, `CHANGELOG.md`, `AGENTS.md` (modify).

---

### Task 1: Time parsing and cut arguments

**Files:**
- Create: `core/clip.py`
- Test: `tests/test_clip.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ClipSpec(start: float, end: float | None, exact: bool)`; `parse_time(text) -> float | None`; `resolve_range(start_text, end_text, duration_text, mode, exact=False) -> (ClipSpec | None, str | None)`; `clip_ffmpeg_args(spec) -> list[str]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_clip.py`:

```python
import pytest

from core.clip import ClipSpec, clip_ffmpeg_args, parse_time, resolve_range


@pytest.mark.parametrize(
    "text,expected",
    [
        ("90", 90.0),
        ("0", 0.0),
        ("1:30", 90.0),
        ("00:01:30", 90.0),
        ("1:2:3", 3723.0),
        ("90.5", 90.5),
        ("", None),
        ("   ", None),
        (None, None),
        ("abc", None),
        ("-5", None),
        ("1:-30", None),
        ("1:2:3:4", None),
    ],
)
def test_parse_time(text, expected):
    assert parse_time(text) == expected


def test_resolve_range_end_mode():
    spec, error = resolve_range("1:00", "1:30", "", "end")
    assert error is None
    assert spec == ClipSpec(start=60.0, end=90.0, exact=False)


def test_resolve_range_duration_mode():
    spec, error = resolve_range("60", "", "30", "duration")
    assert error is None
    assert spec.start == 60.0 and spec.end == 90.0


def test_resolve_range_open_end():
    spec, error = resolve_range("60", "", "", "end")
    assert error is None
    assert spec.end is None


def test_resolve_range_no_clip():
    spec, error = resolve_range("", "", "", "end")
    assert spec is None and error is None


def test_resolve_range_bad_start():
    spec, error = resolve_range("abc", "", "", "end")
    assert spec is None and error


def test_resolve_range_end_before_start():
    spec, error = resolve_range("90", "60", "", "end")
    assert spec is None and "after" in error.lower()


def test_resolve_range_carries_exact():
    spec, _ = resolve_range("10", "20", "", "end", exact=True)
    assert spec.exact is True


def test_clip_ffmpeg_args_stream_copy():
    args = clip_ffmpeg_args(ClipSpec(start=10.0, end=20.0, exact=False))
    assert args[:4] == ["-ss", "10", "-to", "20"]
    assert "-c" in args and args[args.index("-c") + 1] == "copy"


def test_clip_ffmpeg_args_exact_reencodes():
    args = clip_ffmpeg_args(ClipSpec(start=10.0, end=None, exact=True))
    assert "libx264" in args
    assert "-to" not in args  # open end
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_clip.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.clip'`

- [ ] **Step 3: Write minimal implementation**

Create `core/clip.py`:

```python
"""Time-range parsing and ffmpeg cut arguments for clip downloads.

Pure: no network, no Qt. The download and the cut live in core/download.py.
"""

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ClipSpec:
    start: float
    end: Optional[float]
    exact: bool


_TIME_PART = re.compile(r"\d+(?:\.\d+)?")


def parse_time(text) -> Optional[float]:
    """Seconds from "90", "1:30", or "00:01:30". None for empty or invalid."""
    if text is None:
        return None
    text = str(text).strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) > 3:
        return None
    total = 0.0
    for part in parts:
        part = part.strip()
        if not _TIME_PART.fullmatch(part):
            return None
        total = total * 60 + float(part)
    return total


def _secs(value: Optional[float]) -> str:
    return "end" if value is None else str(int(round(value)))


def resolve_range(start_text, end_text, duration_text, mode, exact=False):
    """(ClipSpec | None, error | None). An empty start means no clip."""
    start = parse_time(start_text)
    if start is None:
        if str(start_text or "").strip():
            return None, "Start time is not valid. Use 90, 1:30, or 00:01:30."
        return None, None

    end: Optional[float] = None
    if mode == "duration":
        duration = parse_time(duration_text)
        if duration is None:
            if str(duration_text or "").strip():
                return None, "Duration is not valid. Use 30, 1:30, or 00:01:30."
        elif duration <= 0:
            return None, "Duration must be greater than zero."
        else:
            end = start + duration
    else:
        end = parse_time(end_text)
        if end is None and str(end_text or "").strip():
            return None, "End time is not valid. Use 90, 1:30, or 00:01:30."

    if end is not None and end <= start:
        return None, "End must be after start."
    return ClipSpec(start=start, end=end, exact=exact), None


def clip_ffmpeg_args(spec: ClipSpec) -> List[str]:
    """ffmpeg args placed between -i input and the output path."""
    args = ["-ss", _secs(spec.start)]
    if spec.end is not None:
        args += ["-to", _secs(spec.end)]
    if spec.exact:
        args += [
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        ]
    else:
        args += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
    return args
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_clip.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/clip.py tests/test_clip.py
git commit -m "feat(clip): time parsing and ffmpeg cut arguments"
```

---

### Task 2: The download path with section-then-fallback

**Files:**
- Modify: `core/download.py`
- Test: `tests/test_clip.py` (extend)

**Interfaces:**
- Consumes: `ClipSpec`, `clip_ffmpeg_args` (Task 1).
- Produces: `download_one(..., clip=None)`; `_clip_name(path, clip) -> str`; `_cut_file(path, clip) -> str | None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_clip.py`:

```python
import os

from core.download import _clip_name, download_one


def test_clip_name_whole_seconds():
    assert _clip_name("D:/a/Title.mp4", ClipSpec(90.0, 120.0, False)) == \
        "D:/a/Title_clip_90-120.mp4"


def test_clip_name_open_end():
    assert _clip_name("D:/a/Title.mp4", ClipSpec(90.0, None, False)) == \
        "D:/a/Title_clip_90-end.mp4"


class _SectionFailYDL:
    """Fails when asked for a section, succeeds on the full download."""

    def __init__(self, full_path):
        self._full = full_path

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True, **kw):
        return {"id": "x", "title": "T", "height": 1080, "ext": "mp4"}

    def prepare_filename(self, info):
        return self._full


def test_download_one_clip_falls_back_and_cuts(monkeypatch, tmp_path):
    full = tmp_path / "T.mp4"
    full.write_bytes(b"full")

    class YDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True, **kw):
            if "download_ranges" in self.opts:
                raise RuntimeError("section download failed")
            return {"id": "x", "title": "T", "height": 1080, "ext": "mp4"}

        def prepare_filename(self, info):
            return str(full)

    monkeypatch.setattr("yt_dlp.YoutubeDL", YDL)

    class Proc:
        returncode = 0
        stdout = b""
        stderr = b""

    def fake_run(cmd, *a, **k):
        # ffmpeg writes the cut file as the last argument
        with open(cmd[-1], "wb") as fh:
            fh.write(b"cut")
        return Proc()

    monkeypatch.setattr("core.download.subprocess.run", fake_run)
    monkeypatch.setattr("core.download.os.path.getsize", lambda p: 3)
    monkeypatch.setattr(
        "core.download.probe_media",
        lambda path, **k: {"vcodec": "h264", "acodec": "aac", "height": 1080,
                           "container": "mp4"},
    )

    result = download_one(
        "https://youtu.be/x", outtmpl=str(tmp_path / "%(title)s.%(ext)s"),
        output_type="MP4", convert=False, target_resolution=1080,
        clip=ClipSpec(10.0, 20.0, False),
    )
    assert result.status == "ok"
    assert result.path.endswith("_clip_10-20.mp4")
    assert os.path.isfile(result.path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_clip.py -k clip_name -v`
Expected: FAIL with `ImportError: cannot import name '_clip_name'`

- [ ] **Step 3: Write minimal implementation**

In `core/download.py`, add the imports and helpers near the top (after the existing imports):

```python
from core.clip import ClipSpec, clip_ffmpeg_args
```

Add the helpers before `download_one`:

```python
def _clip_name(path, clip):
    """<base>_clip_<start>-<end><ext> with whole seconds."""
    base, ext = os.path.splitext(path)
    start = int(round(clip.start))
    end = "end" if clip.end is None else str(int(round(clip.end)))
    return "%s_clip_%s-%s%s" % (base, start, end, ext)


def _cut_file(path, clip):
    """Cut `path` to `clip`. Returns the new path, or None on failure."""
    out = _clip_name(path, clip)
    cmd = [ffmpeg_path(), "-i", path] + clip_ffmpeg_args(clip) + ["-y", out]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        return None
    return out


def _section_range(clip):
    rng = {"start_time": clip.start}
    if clip.end is not None:
        rng["end_time"] = clip.end
    return lambda info, ydl: [rng]
```

Change the `download_one` signature to accept `clip=None`:

```python
def download_one(url, outtmpl, output_type, convert, target_resolution,
                 cookies_file=None, progress=None, cancel=None,
                 subtitles=False, embed_thumbnail=False, format_id=None,
                 clip=None):
```

Replace the block that opens `YoutubeDL` (the `with YoutubeDL(ydl_opts) as ydl: info = ydl.extract_info(...)` part) with:

```python
        section_ok = False
        if clip is not None:
            ydl_opts["download_ranges"] = _section_range(clip)
            if clip.exact:
                ydl_opts["force_keyframes_at_cuts"] = True
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded_file = ydl.prepare_filename(info)
            section_ok = clip is not None
        except Exception:
            if clip is None:
                raise
            full_opts = _nle_ydl_opts(
                outtmpl=outtmpl, progress_hooks=hooks, cookies_file=cookies_file
            )
            with YoutubeDL(full_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded_file = ydl.prepare_filename(info)
```

Immediately after that block, add the clip normalization:

```python
        if clip is not None and os.path.isfile(downloaded_file):
            if section_ok:
                # yt-dlp already cut the section; just give it our name.
                renamed = _clip_name(downloaded_file, clip)
                try:
                    os.replace(downloaded_file, renamed)
                    downloaded_file = renamed
                except OSError:
                    pass
            else:
                cut = _cut_file(downloaded_file, clip)
                if cut:
                    os.remove(downloaded_file)
                    downloaded_file = cut
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_clip.py -v`
Expected: PASS

- [ ] **Step 5: Verify the full suite and core isolation**

Run: `python -m pytest -q` then `python -m pytest tests/test_core_isolation.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add core/download.py tests/test_clip.py
git commit -m "feat(download): clip a download via a section, or cut a full file"
```

---

### Task 3: Forward clip through the worker

**Files:**
- Modify: `workers/download_worker.py`

**Interfaces:**
- Consumes: `download_one(..., clip=None)` (Task 2).
- Produces: `DownloadWorker(..., clip=None)` forwards `clip` to `download_one`.

- [ ] **Step 1: Add the parameter**

In `workers/download_worker.py`, add `clip=None` to `DownloadWorker.__init__`, store it as `self.clip = clip`, and pass `clip=self.clip` in the `download_one(...)` call inside `run()`.

- [ ] **Step 2: Verify it compiles and lints**

Run: `python -m py_compile workers/download_worker.py` then `python -m flake8 workers/download_worker.py --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: `0`

- [ ] **Step 3: Run the suite**

Run: `python -m pytest -q`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add workers/download_worker.py
git commit -m "feat(worker): forward the clip spec to the download"
```

---

### Task 4: The Download-tab controls

**Files:**
- Modify: `ui/single_tab.py`

**Interfaces:**
- Consumes: `resolve_range`, `ClipSpec` (Task 1); `DownloadWorker(..., clip=)` (Task 3).
- Produces: a `self.clip_check`, `self.clip_mode_combo`, `self.clip_start_input`, `self.clip_end_input`, `self.clip_exact_check`; `_resolve_clip() -> ClipSpec | None` (shows a hint and returns None on error).

- [ ] **Step 1: Add the controls**

In `ui/single_tab.py`, add the import:

```python
from core.clip import resolve_range
```

After the download bar / hint label, add a clip row:

```python
        self.clip_check = QtWidgets.QCheckBox("Download a clip (time range)")
        self.clip_check.toggled.connect(self._on_clip_toggled)
        main.addWidget(self.clip_check)

        self.clip_row = QtWidgets.QWidget()
        clip_layout = QtWidgets.QHBoxLayout(self.clip_row)
        clip_layout.setContentsMargins(0, 0, 0, 0)
        self.clip_mode_combo = QtWidgets.QComboBox()
        self.clip_mode_combo.setAccessibleName("Clip range mode")
        self.clip_mode_combo.addItem("Start + End", "end")
        self.clip_mode_combo.addItem("Start + Duration", "duration")
        self.clip_mode_combo.currentIndexChanged.connect(self._on_clip_mode_changed)
        clip_layout.addWidget(self.clip_mode_combo)
        self.clip_start_input = QtWidgets.QLineEdit()
        self.clip_start_input.setAccessibleName("Clip start time")
        self.clip_start_input.setPlaceholderText("Start, e.g. 1:30")
        clip_layout.addWidget(self.clip_start_input)
        self.clip_end_label = QtWidgets.QLabel("End")
        clip_layout.addWidget(self.clip_end_label)
        self.clip_end_input = QtWidgets.QLineEdit()
        self.clip_end_input.setAccessibleName("Clip end time or duration")
        self.clip_end_input.setPlaceholderText("End, e.g. 2:00")
        clip_layout.addWidget(self.clip_end_input)
        self.clip_exact_check = QtWidgets.QCheckBox("Exact cut")
        self.clip_exact_check.setToolTip("Re-encode for a frame-accurate cut")
        clip_layout.addWidget(self.clip_exact_check)
        clip_layout.addStretch(1)
        self.clip_row.setVisible(False)
        main.addWidget(self.clip_row)
```

Add the methods:

```python
    def _on_clip_toggled(self, checked):
        self.clip_row.setVisible(checked)

    def _on_clip_mode_changed(self, _index):
        mode = self.clip_mode_combo.currentData()
        if mode == "duration":
            self.clip_end_label.setText("Duration")
            self.clip_end_input.setPlaceholderText("Duration, e.g. 0:30")
        else:
            self.clip_end_label.setText("End")
            self.clip_end_input.setPlaceholderText("End, e.g. 2:00")

    def _resolve_clip(self):
        if not self.clip_check.isChecked():
            return None
        spec, error = resolve_range(
            self.clip_start_input.text(), self.clip_end_input.text(),
            self.clip_end_input.text(), self.clip_mode_combo.currentData(),
            exact=self.clip_exact_check.isChecked(),
        )
        if error:
            self.show_hint(error)
            return False  # invalid: block the download
        return spec
```

`_resolve_clip` returns `None` (no clip), `False` (invalid), or a `ClipSpec`.

- [ ] **Step 2: Use it in on_download**

In `on_download`, after the existing URL/info checks, add:

```python
        clip = self._resolve_clip()
        if clip is False:
            return
        self.show_hint("")
```

and pass it to the worker:

```python
        self.worker = DownloadWorker(
            url, final_outtmpl, convert, target_resolution, output_type,
            cookies_file=self._get_cookies_path(), clip=clip,
        )
```

- [ ] **Step 3: Verify it compiles and lints**

Run: `python -m py_compile ui/single_tab.py` then `python -m flake8 ui/single_tab.py --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: `0`

- [ ] **Step 4: Verify the controls construct offscreen**

Run:

```bash
python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PyQt5 import QtWidgets, QtCore; app=QtWidgets.QApplication([]); app.setOrganizationName('petra-dot'); app.setApplicationName('SocialClip Downloader'); QtCore.QSettings().setValue('first_run_done', True); from ui.single_tab import SingleTab; t=SingleTab({'path':''}); t.clip_check.setChecked(True); t.clip_start_input.setText('1:00'); t.clip_end_input.setText('1:30'); spec=t._resolve_clip(); print('clip', spec.start, spec.end, 'visible', not t.clip_row.isHidden())"
```

Expected: `clip 60.0 90.0 visible True`

- [ ] **Step 5: Commit**

```bash
git add ui/single_tab.py
git commit -m "feat(ui): clip controls on the download tab"
```

---

### Task 5: CLI flags

**Files:**
- Modify: `cli.py`
- Test: `tests/test_cli.py` (extend)

**Interfaces:**
- Consumes: `resolve_range` (Task 1); `download_one(..., clip=)` (Task 2).
- Produces: `socialclip download --start --end --duration --exact-cut`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_download_bad_clip_range_exits_usage(monkeypatch, tmp_path):
    import cli
    rc = cli.main([
        "download", "https://youtu.be/x", "--start", "90", "--end", "60",
        "--output", str(tmp_path),
    ])
    assert rc == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py::test_download_bad_clip_range_exits_usage -v`
Expected: FAIL with `SystemExit` from argparse (unknown arguments `--start`/`--end`)

- [ ] **Step 3: Write minimal implementation**

In `cli.py`, add the flags to the `download` parser (near `d.add_argument("--cookies", ...)`):

```python
    d.add_argument("--start", default="")
    d.add_argument("--end", default="")
    d.add_argument("--duration", default="")
    d.add_argument("--exact-cut", action="store_true")
```

In `_cmd_download`, after the two dependency checks and before `out_dir` is built:

```python
    from core.clip import resolve_range

    mode = "duration" if args.duration else "end"
    clip, clip_error = resolve_range(
        args.start, args.end, args.duration, mode, exact=args.exact_cut,
    )
    if clip_error:
        print("error: %s" % clip_error, file=sys.stderr)
        return EXIT_USAGE
```

Then pass `clip=clip` to the `download_one(...)` call.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Verify the full suite and lint**

Run: `python -m pytest -q` then `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: all pass; `0`

- [ ] **Step 6: Commit**

```bash
git add cli.py tests/test_cli.py
git commit -m "feat(cli): clip download flags"
```

---

### Task 6: Documentation

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `AGENTS.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing code-facing.

- [ ] **Step 1: README**

Add a short note under the download features: a clip option downloads only a time range (start/end or start/duration), lossless by default with an exact-cut option, plus the CLI `--start/--end/--duration/--exact-cut`.

- [ ] **Step 2: CHANGELOG**

Under `## Unreleased`, add `### Added` for clip downloads.

- [ ] **Step 3: AGENTS.md**

Add `core/clip.py` to the layout list and one line: clip downloads use yt-dlp `download_ranges` first, then a full download cut with ffmpeg.

- [ ] **Step 4: Commit**

```bash
git add README.md CHANGELOG.md AGENTS.md
git commit -m "docs: clip downloads"
```

---

## Self-Review

- **Spec coverage:** pure helpers (Task 1), section-then-fallback download + naming (Task 2), worker pass-through (Task 3), Download-tab controls (Task 4), CLI flags (Task 5), docs (Task 6). The editor-safe guarantee is the existing `needs_universal_reencode` step, unchanged, which the Task 2 test exercises via the `probe_media` stub. The mode toggle is `resolve_range(mode=...)` (Task 1) and `clip_mode_combo` (Task 4).
- **Placeholder scan:** no TBD/TODO; every code step carries real code.
- **Type consistency:** `ClipSpec(start, end, exact)` is identical across Tasks 1, 2, 4; `resolve_range` returns `(spec, error)` everywhere it is used; `_clip_name`/`_cut_file`/`_section_range` are defined in Task 2 and used only there; `DownloadWorker(..., clip=)` matches Task 4's call.
- **Known limitation:** the yt-dlp section path's exact output filename varies, so Task 2 renames the produced file to the clip name; the section path itself is verified by hand (network), matching repo convention.
