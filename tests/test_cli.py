import json
import subprocess
import sys

import cli
from core.manifest import DownloadResult


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
    assert proc.stdout == ""
    assert "usage:" in proc.stderr.lower()


def test_download_json_success_stdout_is_pure_json(monkeypatch, capsys):
    def fake_download_one(url, outtmpl, output_type, convert,
                          target_resolution, cookies_file=None, progress=None):
        return DownloadResult(
            status="ok", url=url, title="t", path="C:/fake/out.mp4",
            extension="mp4", message="Download finished: C:/fake/out.mp4",
        )

    monkeypatch.setattr("utils.ffmpeg.ffmpeg_path", lambda: "ffmpeg-real")
    monkeypatch.setattr("core.download.download_one", fake_download_one)

    rc = cli.main(["download", "https://example.com/x", "--json"])

    captured = capsys.readouterr()
    assert rc == 0
    assert captured.err == ""
    data = json.loads(captured.out)  # raises if stdout is not pure JSON
    assert data["status"] == "ok"
    assert data["path"] == "C:/fake/out.mp4"
    assert captured.out.strip().startswith("{")
    assert captured.out.strip().endswith("}")


def test_download_ffmpeg_missing_json_emits_pure_json(monkeypatch, capsys):
    monkeypatch.setattr("utils.ffmpeg.ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr("cli._on_path", lambda name: False)

    rc = cli.main(["download", "https://example.com/x", "--json"])

    captured = capsys.readouterr()
    assert rc == 3
    assert captured.err == ""
    data = json.loads(captured.out)
    assert data["schema_version"] == "1.0"
    assert data["status"] == "error"
    assert data["error_category"] == "ffmpeg"
