import json
import os
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


def test_manifest_schema_error_category_includes_cancelled():
    proc = run_cli("manifest-schema")
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert "cancelled" in data["properties"]["error_category"]["enum"]


def test_convert_json_stdout_is_pure_json(tmp_path):
    src = tmp_path / "missing.mp4"
    # Point the ffmpeg resolver at a real file so the dependency gate passes
    # deterministically on runners that lack ffmpeg; the test targets the
    # missing-input path, not the dependency path.
    fake_ffmpeg = tmp_path / "ffmpeg"
    fake_ffmpeg.write_text("")
    env = {**os.environ, "SOCIALCLIP_FFMPEG": str(fake_ffmpeg)}
    proc = subprocess.run(
        [sys.executable, "cli.py", "convert", str(src), "--json"],
        capture_output=True, text=True, env=env,
    )
    # one JSON object on stdout, nothing else
    data = json.loads(proc.stdout)
    assert data["status"] == "error"
    assert data["error_category"] == "not_found"
    assert proc.returncode == 1


def test_doctor_json_reports_schema_1_1(monkeypatch, capsys):
    monkeypatch.setattr(
        "core.doctor.run_checks",
        lambda **kw: {
            "schema_version": "1.1",
            "ffmpeg": {"found": True, "path": "/x/ffmpeg", "version": "ffmpeg version 6"},
            "cookies": [],
            "network": {"ok": True, "detail": "ok"},
        },
    )
    rc = cli.main(["doctor", "--json"])
    captured = capsys.readouterr()
    assert rc == 0
    data = json.loads(captured.out)
    assert data["schema_version"] == "1.1"
    assert data["ffmpeg"]["found"] is True
    assert "cookies" in data and "network" in data


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

    monkeypatch.setattr(cli, "_ffmpeg_missing", lambda: False)
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


def test_download_ytdlp_missing_returns_dep_exit(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_ytdlp_missing", lambda: True)
    monkeypatch.setattr(cli, "_ffmpeg_missing", lambda: False)

    rc = cli.main(["download", "https://example.com/x", "--json"])

    captured = capsys.readouterr()
    assert rc == 3
    assert captured.err == ""
    data = json.loads(captured.out)
    assert data["status"] == "error"


def test_convert_ffmpeg_missing_returns_dep_exit(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_ffmpeg_missing", lambda: True)

    rc = cli.main(["convert", "x.mp4", "--json"])

    captured = capsys.readouterr()
    assert rc == 3
    assert captured.err == ""
    data = json.loads(captured.out)
    assert data["status"] == "error"
    assert data["error_category"] == "ffmpeg"


def test_download_defaults_to_no_convert(monkeypatch, capsys):
    """Without --convert the CLI must keep the original quality, like the GUI."""
    seen = {}

    def fake_download_one(url, outtmpl, output_type, convert,
                          target_resolution, cookies_file=None, progress=None):
        seen["convert"] = convert
        return DownloadResult(status="ok", url=url, path="C:/fake/out.mp4",
                              extension="mp4", message="Download finished")

    monkeypatch.setattr(cli, "_ffmpeg_missing", lambda: False)
    monkeypatch.setattr("core.download.download_one", fake_download_one)

    rc = cli.main(["download", "https://example.com/x", "--json"])

    assert rc == 0
    assert seen["convert"] is False


def test_download_convert_flag_opts_in(monkeypatch, capsys):
    seen = {}

    def fake_download_one(url, outtmpl, output_type, convert,
                          target_resolution, cookies_file=None, progress=None):
        seen["convert"] = convert
        seen["resolution"] = target_resolution
        return DownloadResult(status="ok", url=url, path="C:/fake/out.mp4",
                              extension="mp4", message="Conversion completed")

    monkeypatch.setattr(cli, "_ffmpeg_missing", lambda: False)
    monkeypatch.setattr("core.download.download_one", fake_download_one)

    rc = cli.main(["download", "https://example.com/x", "--json",
                   "--convert", "--resolution", "720"])

    assert rc == 0
    assert seen["convert"] is True
    assert seen["resolution"] == 720


def test_download_json_real_ytdlp_stdout_is_one_object(monkeypatch, capsys, tmp_path):
    """Exercise the real yt-dlp layer offline; only the dep gate is bypassed.

    Regression guard: without silencing yt-dlp, `[generic] ...` lines land on
    stdout ahead of the JSON and break the one-object contract.
    """
    monkeypatch.setattr(cli, "_ffmpeg_missing", lambda: False)
    monkeypatch.setattr(cli, "_ytdlp_missing", lambda: False)

    rc = cli.main([
        "download", "not-a-real-url://x", "--json", "--output", str(tmp_path),
    ])

    captured = capsys.readouterr()
    assert rc == 1
    # Contract: stdout carries exactly one JSON object. stderr may carry
    # yt-dlp's own warnings (e.g. Python-version deprecation on CI).
    assert "[generic]" not in captured.out
    data = json.loads(captured.out)  # exactly one JSON object, nothing else
    assert data["status"] == "error"
    assert captured.out.strip().startswith("{")
    assert captured.out.strip().endswith("}")


def test_convert_to_mkv_routes_target_format(monkeypatch, capsys):
    captured = {}

    def fake(input_path, output_type=None, target_resolution=None,
             target_format=None, copy_streams=None):
        captured["fmt"] = target_format
        captured["copy"] = copy_streams
        from core.manifest import DownloadResult
        return DownloadResult(status="ok", path="C:/o.mkv", extension="mkv",
                              message="Converted to C:/o.mkv")

    monkeypatch.setattr(cli, "_ffmpeg_missing", lambda: False)
    monkeypatch.setattr("core.convert.convert_file", fake)
    rc = cli.main(["convert", "x.mp4", "--to", "mkv", "--copy", "--json"])
    assert rc == 0
    assert captured["fmt"] == "mkv"
    assert captured["copy"] is True


def test_convert_unknown_to_is_usage_error():
    proc = run_cli("convert", "x.mp4", "--to", "nope")
    assert proc.returncode == 2
    assert "nope" in proc.stderr


def test_convert_to_mp4_routes_format_path_not_legacy(monkeypatch, capsys):
    """`--to mp4` is a format key, never the legacy MP4 output_type."""
    captured = {}

    def fake(input_path, output_type=None, target_resolution=None,
             target_format=None, copy_streams=None):
        captured["fmt"] = target_format
        captured["output_type"] = output_type
        from core.manifest import DownloadResult
        return DownloadResult(status="ok", path="C:/o.mp4", extension="mp4",
                              message="Converted to C:/o.mp4")

    monkeypatch.setattr(cli, "_ffmpeg_missing", lambda: False)
    monkeypatch.setattr("core.convert.convert_file", fake)
    rc = cli.main(["convert", "x.mp4", "--to", "mp4", "--json"])
    assert rc == 0
    assert captured["fmt"] == "mp4"
    assert captured["output_type"] is None


def test_convert_no_copy_without_to_is_usage_error():
    proc = run_cli("convert", "x.mp4", "--no-copy")
    assert proc.returncode == 2
    assert "--to" in proc.stderr
