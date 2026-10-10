"""Platform badges for the queue table.

A small rounded square in the platform's brand colour with its initial. Drawn
at runtime, so there are no image assets to ship and no trademark artwork to
redistribute; unknown platforms fall back to a neutral badge.

The colour/letter mapping is pure and unit-tested. The Qt rendering is a thin
wrapper on top of it.
"""

from sites.cookies import detect_platform, get_platform_display_name

# Brand-ish colours per platform key (from PLATFORM_NAMES in sites/cookies.py).
PLATFORM_COLORS = {
    "youtube": "#FF0000",
    "tiktok": "#111111",
    "instagram": "#E1306C",
    "twitter": "#1DA1F2",
    "facebook": "#1877F2",
    "bilibili": "#FB7299",
    "douyin": "#111111",
}

DEFAULT_COLOR = "#6B7280"  # neutral grey for unknown platforms


def badge_spec(platform: str):
    """Return (letter, colour_hex) for a platform key.

    Pure: no Qt. The letter is the platform's display-name initial, or "?" for
    an unknown platform.
    """
    platform = (platform or "").strip().lower()
    if not platform:
        return "?", DEFAULT_COLOR
    name = get_platform_display_name(platform)
    letter = (name[:1] or "?").upper()
    return letter, PLATFORM_COLORS.get(platform, DEFAULT_COLOR)


def badge_for_url(url: str):
    """Convenience: the badge spec for a URL, via platform detection."""
    return badge_spec(detect_platform(url or ""))


_cache = {}


def platform_icon(platform: str, size: int = 16):
    """A QIcon badge for a platform key. Cached; requires a Qt app."""
    from PyQt5 import QtGui, QtCore

    key = (platform or "", size)
    if key in _cache:
        return _cache[key]

    letter, color = badge_spec(platform)
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.transparent)

    painter = QtGui.QPainter(pixmap)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setBrush(QtGui.QColor(color))
        painter.setPen(QtCore.Qt.NoPen)
        radius = size * 0.28
        painter.drawRoundedRect(0, 0, size, size, radius, radius)

        font = painter.font()
        font.setPixelSize(int(size * 0.62))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QtGui.QColor("#FFFFFF"))
        painter.drawText(pixmap.rect(), QtCore.Qt.AlignCenter, letter)
    finally:
        painter.end()

    icon = QtGui.QIcon(pixmap)
    _cache[key] = icon
    return icon


def icon_for_url(url: str, size: int = 16):
    """A QIcon badge for a URL. Requires a Qt app."""
    return platform_icon(detect_platform(url or ""), size)
