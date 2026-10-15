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
    for index, part in enumerate(parts):
        part = part.strip()
        if not _TIME_PART.fullmatch(part):
            return None
        value = float(part)
        # Only the leading field may exceed 59: "1:90" is a typo, not 150s.
        if index and value >= 60:
            return None
        total = total * 60 + value
    return total


def _fmt_time(value: float) -> str:
    """Trimmed decimal seconds: 90.5 -> "90.5", 90.0 -> "90"."""
    return "%g" % value


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
    args = ["-ss", _fmt_time(spec.start)]
    if spec.end is not None:
        args += ["-to", _fmt_time(spec.end)]
    if spec.exact:
        args += [
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        ]
    else:
        args += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
    return args
