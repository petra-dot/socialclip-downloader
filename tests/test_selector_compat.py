"""The downloaded MP4 must be universally playable (H.264 + AAC).

Sites like Instagram often serve only VP9/AV1. The selector must therefore
accept whatever is available, and a post-download step must guarantee the
final file is H.264/AAC -- otherwise WhatsApp and Facebook reject it.
"""

from utils.ydl_opts import _nle_safe_format_selector


def test_selector_accepts_non_h264_sources():
    """Instagram offers vp9/av01; the selector must not demand avc1 only."""
    sel = _nle_safe_format_selector()
    parts = [p.strip() for p in sel.split("/")]
    assert any("bestvideo[vcodec^=avc1]" not in p for p in parts), (
        "selector is H.264-only and will fail on VP9/AV1-only sources: %r" % sel
    )


def test_selector_still_prefers_h264_first():
    """Prefer H.264 so the common case avoids a re-encode, but allow others."""
    sel = _nle_safe_format_selector()
    first = sel.split("/")[0]
    assert "avc1" in first, sel


def test_selector_has_a_general_fallback():
    """There must be a final branch that matches any available best stream."""
    sel = _nle_safe_format_selector()
    last = sel.split("/")[-1].strip()
    assert last in ("bestvideo+bestaudio", "bestvideo*+bestaudio", "best"), sel
