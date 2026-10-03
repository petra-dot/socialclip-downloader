"""The format selector must not let a non-H.264 codec land inside an MP4.

WhatsApp and Facebook reject VP9/AV1-in-MP4 and Opus-in-MP4. The selector
must therefore refuse those fallbacks rather than mux them into an .mp4.
"""

from utils.ydl_opts import _nle_safe_format_selector


def test_selector_prefers_h264_and_aac():
    selector = _nle_safe_format_selector()
    assert "avc1" in selector
    assert "m4a" in selector


def test_selector_never_falls_back_to_an_unconstrained_bestalias():
    """A bare `bestvideo+bestaudio` or bare `best` can yield VP9/Opus in mp4."""
    selector = _nle_safe_format_selector()
    parts = [p.strip() for p in selector.split("/")]
    for part in parts:
        assert part != "bestvideo+bestaudio", selector
        assert part != "best", selector


def test_every_selector_fallback_is_h264_constrained():
    """Each fallback branch must constrain the video codec to H.264."""
    selector = _nle_safe_format_selector()
    for part in [p.strip() for p in selector.split("/")]:
        assert "avc1" in part, "unconstrained fallback: %r in %r" % (part, selector)
