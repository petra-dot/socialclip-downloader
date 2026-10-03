"""The format selector must prefer H.264 but accept any available stream.

Rationale: preferring H.264 avoids a needless re-encode, but sites such as
Instagram Reels serve only VP9/AV1. An H.264-only selector fails there with
"Requested format is not available". Universal playability (WhatsApp/Facebook)
is guaranteed after download, not by refusing non-H.264 sources here.
"""

from utils.ydl_opts import _nle_safe_format_selector


def test_selector_prefers_h264_and_aac_first():
    first = _nle_safe_format_selector().split("/")[0]
    assert "avc1" in first
    assert "m4a" in first


def test_selector_accepts_a_non_h264_source():
    """A VP9/AV1-only source (Instagram) must still match a branch."""
    parts = [p.strip() for p in _nle_safe_format_selector().split("/")]
    assert any("avc1" not in p for p in parts), (
        "selector is H.264-only; it will fail on VP9/AV1-only sources"
    )


def test_selector_ends_with_a_general_fallback():
    last = _nle_safe_format_selector().split("/")[-1].strip()
    assert last in ("bestvideo+bestaudio", "bestvideo*+bestaudio", "best")
