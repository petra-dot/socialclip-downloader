from collections import namedtuple
from typing import Optional

Progress = namedtuple(
    "Progress", ("percent", "speed", "eta", "downloaded", "total")
)

_UNITS = (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024))


def format_bytes(n) -> str:
    """1024-based size: '512 B', '48.3 KB', '14.2 MB', '1.4 GB'."""
    if n is None:
        return ""
    n = float(n)
    for label, scale in _UNITS:
        if n >= scale:
            return "%.1f %s" % (n / scale, label)
    return "%d B" % int(n)


def format_speed(bps: Optional[float]) -> str:
    """'3.2 MB/s', or '' when unknown."""
    if bps is None:
        return ""
    return format_bytes(bps) + "/s"


def format_eta(seconds: Optional[int]) -> str:
    """'ETA MM:SS' (or 'ETA H:MM:SS'), or '' when unknown."""
    if seconds is None:
        return ""
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return "ETA %d:%02d:%02d" % (hours, minutes, secs)
    return "ETA %02d:%02d" % (minutes, secs)


def _format_pair(downloaded, total) -> str:
    """'14.2/31.0 MB': one shared unit for a downloaded/total pair."""
    for label, scale in _UNITS:
        if total >= scale:
            return "%.1f/%.1f %s" % (
                float(downloaded) / scale, float(total) / scale, label
            )
    return "%d/%d B" % (int(downloaded), int(total))


def format_progress(p: Progress) -> str:
    """'45%  3.2 MB/s  ETA 00:12  14.2/31.0 MB'; unknown parts drop out."""
    parts = ["%d%%" % int(p.percent)]
    if p.speed is not None:
        parts.append(format_speed(p.speed))
    if p.eta is not None:
        parts.append(format_eta(p.eta))
    if p.total:
        parts.append(_format_pair(p.downloaded, p.total))
    elif p.downloaded:
        parts.append(format_bytes(p.downloaded))
    return "  ".join(parts)
