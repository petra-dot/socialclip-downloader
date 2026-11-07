import io

import pytest

from core.native import (
    ProtocolError,
    already_known,
    encode_message,
    normalize_url,
    read_message,
)
from core.queue import QueueJob


def test_message_round_trip_preserves_the_payload():
    payload = {"cmd": "ping", "urls": ["https://youtu.be/x"]}
    assert read_message(io.BytesIO(encode_message(payload))) == payload


def test_read_message_rejects_a_short_body():
    frame = encode_message({"cmd": "ping"})
    with pytest.raises(ProtocolError):
        read_message(io.BytesIO(frame[: len(frame) - 2]))


def test_normalize_url_drops_tracking_query_and_trailing_slash():
    assert (
        normalize_url("https://WWW.Facebook.com/reel/123/?s=f&stack_idx=0")
        == "https://www.facebook.com/reel/123"
    )
    assert normalize_url("not a url") == ""


def test_already_known_matches_across_query_strings():
    jobs = [QueueJob(url="https://youtu.be/x?t=10", state="pending")]
    found = already_known(["https://youtu.be/x"], jobs, [])
    assert found == {"in_queue": ["https://youtu.be/x"], "in_history": []}
