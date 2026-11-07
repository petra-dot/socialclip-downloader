import json
import os
import struct
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_host(payload, tmp_path):
    body = json.dumps(payload).encode("utf-8")
    env = dict(
        os.environ,
        SOCIALCLIP_DATA=str(tmp_path),
        # A running app must not take the job during the test.
        SOCIALCLIP_IPC="socialclip-test-%d" % os.getpid(),
    )
    return subprocess.run(
        [sys.executable, os.path.join(REPO, "socialclip_downloader.py"), "--native-host"],
        input=struct.pack("<I", len(body)) + body,
        capture_output=True,
        env=env,
        timeout=120,
    )


def test_native_host_answers_ping_on_a_clean_stdout(tmp_path):
    proc = _run_host({"cmd": "ping"}, tmp_path)
    assert proc.returncode == 0
    length = struct.unpack("<I", proc.stdout[:4])[0]
    reply = json.loads(proc.stdout[4:4 + length])
    assert reply["ok"] is True
    assert reply["protocol"] == 1
    assert reply["version"]
    assert proc.stdout[4 + length:] == b""


def test_native_host_add_writes_the_queue(tmp_path):
    proc = _run_host(
        {"cmd": "add", "urls": ["https://youtu.be/x"], "output": "MP3",
         "resolution": "720", "start": False},
        tmp_path,
    )
    assert proc.returncode == 0
    queue_file = tmp_path / "queue.json"
    data = json.loads(queue_file.read_text(encoding="utf-8"))
    assert data["jobs"][0]["url"] == "https://youtu.be/x"
    assert data["jobs"][0]["options"]["output_type"] == "MP3"
