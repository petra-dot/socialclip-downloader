import json
import subprocess
import sys


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "cli.py", *args],
        capture_output=True, text=True,
    )


def test_manifest_schema_prints_json_with_version():
    proc = run_cli("manifest-schema")
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["properties"]["schema_version"]["const"] == "1.0"


def test_convert_json_stdout_is_pure_json(tmp_path):
    src = tmp_path / "missing.mp4"
    proc = run_cli("convert", str(src), "--json")
    # one JSON object on stdout, nothing else
    data = json.loads(proc.stdout)
    assert data["status"] == "error"
    assert data["error_category"] == "not_found"
    assert proc.returncode == 1


def test_usage_error_returns_2():
    proc = run_cli("download")  # missing URL
    assert proc.returncode == 2
