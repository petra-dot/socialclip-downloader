from sites.errors import classify_error, looks_like_auth_error


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


def test_silent_video_ffmpeg_failure_is_not_a_missing_install():
    category, message = classify_error(
        "ffmpeg version 6.1 ...\nStream map '0:a' matches no streams.\n",
        "",
    )
    assert category == "ffmpeg"
    assert "no audio track" in message.lower()
    assert "not installed" not in message.lower()


def test_genuine_missing_ffmpeg_still_reports_install_hint():
    category, message = classify_error("ffmpeg: command not found", "")
    assert category == "ffmpeg"
    assert "not installed" in message.lower() or "not in path" in message.lower()


def test_unknown_error_passes_message_through():
    category, message = classify_error("some weird failure", "https://youtu.be/x")
    assert category == "other"
    assert "some weird failure" in message


def test_network_error_is_classified():
    category, message = classify_error(
        "Unable to download webpage: <urlopen error timed out>", "https://youtu.be/x"
    )
    assert category == "network"
    assert "network" in message.lower() or "connect" in message.lower()


def test_not_found_error_is_classified():
    category, message = classify_error(
        "Video unavailable: 404 Not Found", "https://youtu.be/x"
    )
    assert category == "not_found"
    assert "not found" in message.lower() or "unavailable" in message.lower()


def test_looks_like_auth_error_true_for_authentication_signals():
    for message in (
        "Login required",
        "Sign in to confirm you're not a bot",
        "HTTP Error 403: Forbidden",
        "This video is private",
    ):
        assert looks_like_auth_error(message) is True, message


def test_looks_like_auth_error_false_for_genuinely_unavailable():
    for message in ("Video unavailable", "Unsupported URL", ""):
        assert looks_like_auth_error(message) is False, message


def test_looks_like_auth_error_tolerates_none():
    assert looks_like_auth_error(None) is False


def test_unsupported_url_is_classified_friendly():
    category, message = classify_error(
        "ERROR: Unsupported URL: https://a.com/1", "https://a.com/1"
    )
    assert category == "unsupported"
    assert message == "That link is not a video yt-dlp can download from."


def test_generic_fallback_is_not_unsupported():
    # The generic extractor's own message mentions "generic", not a missing
    # extractor, so it must fall through rather than be mislabelled.
    category, _ = classify_error(
        "ERROR: [generic] Falling back on generic information extractor",
        "https://a.com/1",
    )
    assert category != "unsupported"
