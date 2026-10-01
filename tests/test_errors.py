from sites.errors import classify_error


def test_blocked_uses_platform_display_name():
    category, message = classify_error(
        "Sign in to confirm you're not a bot", "https://www.facebook.com/reel/1"
    )
    assert category == "blocked"
    assert "Facebook" in message


def test_blocked_with_unknown_platform_says_the_site():
    category, message = classify_error("cookies required", "https://example.com/x")
    assert category == "blocked"
    assert "The site" in message


def test_requested_format_is_classified():
    category, _ = classify_error("Requested format is not available", "https://youtu.be/x")
    assert category == "format"


def test_missing_ffmpeg_is_classified():
    category, message = classify_error(
        "ffmpeg is not installed. Aborting due to --abort-on-error",
        "https://www.facebook.com/reel/1",
    )
    assert category == "ffmpeg"
    assert "ffmpeg" in message.lower()


def test_unknown_error_passes_message_through():
    category, message = classify_error("some weird failure", "https://youtu.be/x")
    assert category == "other"
    assert "some weird failure" in message
