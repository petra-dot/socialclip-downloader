import io

import pytest

from core.history import HistoryEntry, HistoryStore
from core.native import (
    PROTOCOL_VERSION,
    ProtocolError,
    already_known,
    download_choices,
    encode_message,
    handle_message,
    normalize_url,
    read_message,
    supported_sites,
)
from core.queue import QueueJob, QueueStore


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


def _store(tmp_path):
    store = QueueStore(str(tmp_path / "queue.json"))
    store.load_strict()
    return store


def _history(tmp_path):
    return HistoryStore(str(tmp_path / "history.json"))


def test_ping_reports_the_protocol_version(tmp_path):
    reply = handle_message({"cmd": "ping"}, _store(tmp_path), _history(tmp_path), {})
    assert reply["ok"] is True
    assert reply["protocol"] == PROTOCOL_VERSION
    assert reply["version"]


def test_sites_come_from_the_app_registry():
    sites = supported_sites()
    assert {s["platform"] for s in sites} >= {"youtube", "facebook", "tiktok"}
    assert all(s["name"] and s["pattern"] for s in sites)


def test_formats_offer_mp4_mp3_and_resolutions(tmp_path):
    reply = handle_message({"cmd": "formats"}, _store(tmp_path), _history(tmp_path), {})
    assert reply["outputs"] == ["MP4", "MP3"]
    assert reply["resolutions"] == download_choices()["resolutions"]
    assert "720" in reply["resolutions"]


def test_add_writes_jobs_with_the_given_options(tmp_path):
    store = _store(tmp_path)
    reply = handle_message(
        {"cmd": "add", "urls": ["https://youtu.be/x"], "start": False},
        store,
        _history(tmp_path),
        {"output_type": "MP3"},
    )
    assert reply == {"ok": True, "added": 1}
    reloaded = QueueStore(store.path)
    reloaded.load_strict()
    assert reloaded.jobs[0].options == {"output_type": "MP3"}


def test_check_separates_queue_from_history(tmp_path):
    store = _store(tmp_path)
    store.jobs.append(QueueJob(url="https://youtu.be/x", state="pending"))
    history = _history(tmp_path)
    history.add(HistoryEntry(url="https://youtu.be/y"))
    reply = handle_message(
        {"cmd": "check", "urls": ["https://youtu.be/x", "https://youtu.be/y"]},
        store,
        history,
        {},
    )
    assert reply["in_queue"] == ["https://youtu.be/x"]
    assert reply["in_history"] == ["https://youtu.be/y"]


def test_unknown_command_fails_cleanly(tmp_path):
    reply = handle_message({"cmd": "nope"}, _store(tmp_path), _history(tmp_path), {})
    assert reply == {"ok": False, "error": "unknown command"}
