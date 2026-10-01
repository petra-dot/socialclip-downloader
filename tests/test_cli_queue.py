import json
import os
import subprocess
import sys


def run_cli(*args, env=None):
    return subprocess.run([sys.executable, "cli.py", *args],
                          capture_output=True, text=True, env=env)


def test_queue_add_and_list_round_trip(tmp_path):
    env = {**os.environ, "SOCIALCLIP_QUEUE": str(tmp_path / "q.json")}
    proc = run_cli("queue", "add", "https://a.com/1", "--json", env=env)
    assert proc.returncode == 0
    added = json.loads(proc.stdout)
    assert added["added"] == 1

    proc = run_cli("queue", "list", "--json", env=env)
    data = json.loads(proc.stdout)
    assert data["jobs"][0]["url"] == "https://a.com/1"


def test_queue_clear_empties(tmp_path):
    env = {**os.environ, "SOCIALCLIP_QUEUE": str(tmp_path / "q.json")}
    run_cli("queue", "add", "https://a.com/1", env=env)
    proc = run_cli("queue", "clear", "--json", env=env)
    assert json.loads(proc.stdout)["cleared"] >= 1
    proc = run_cli("queue", "list", "--json", env=env)
    assert json.loads(proc.stdout)["jobs"] == []
