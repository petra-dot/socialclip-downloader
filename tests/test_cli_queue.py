import json
import os
import subprocess
import sys
from pathlib import Path

import cli


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


def test_queue_override_used_in_process(tmp_path, monkeypatch, capsys):
    from sites.cookies import default_cookie_dir
    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(tmp_path / "q.json"))
    default_path = Path(default_cookie_dir()) / "queue.json"
    assert not default_path.exists(), f"precondition: {default_path} already exists"

    rc = cli.main(["queue", "add", "https://a.com/1", "--json"])
    capsys.readouterr()

    assert rc == cli.EXIT_OK
    assert (tmp_path / "q.json").exists()
    assert not default_path.exists()


def test_queue_executor_resolves_outtmpl_precedence(monkeypatch):
    import core.download
    from core.manifest import DownloadResult
    from core.queue import QueueJob
    from utils.file_utils import default_download_folder

    captured = []

    def fake_download_one(url, **kw):
        captured.append(kw["outtmpl"])
        return DownloadResult(status="ok", path="o.mp4")

    monkeypatch.setattr(core.download, "download_one", fake_download_one)

    cli._queue_executor(QueueJob(url="u", options={"outtmpl": "C:/chosen/t.%(ext)s"}))
    cli._queue_executor(QueueJob(url="u", options={"output_dir": "C:/dir"}))
    cli._queue_executor(QueueJob(url="u", options={}))

    assert captured[0] == "C:/chosen/t.%(ext)s"
    assert captured[1] == os.path.join("C:/dir", "%(title)s.%(ext)s")
    assert captured[2] == os.path.join(
        default_download_folder(), "%(title)s.%(ext)s"
    )


def test_queue_run_ytdlp_missing_exit3(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(tmp_path / "q.json"))
    monkeypatch.setattr(cli, "_ytdlp_missing", lambda: True)
    monkeypatch.setattr(cli, "_ffmpeg_missing", lambda: False)

    rc = cli.main(["queue", "run", "--json"])
    data = json.loads(capsys.readouterr().out)

    assert rc == cli.EXIT_DEP == 3
    assert data["status"] == "error"
    assert data["error_category"] == "other"
    assert "yt-dlp" in data["message"]


def test_queue_run_ffmpeg_missing_exit3(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(tmp_path / "q.json"))
    monkeypatch.setattr(cli, "_ytdlp_missing", lambda: False)
    monkeypatch.setattr(cli, "_ffmpeg_missing", lambda: True)

    rc = cli.main(["queue", "run", "--json"])
    data = json.loads(capsys.readouterr().out)

    assert rc == cli.EXIT_DEP == 3
    assert data["status"] == "error"
    assert data["error_category"] == "ffmpeg"


def test_queue_run_ok_summary(tmp_path, monkeypatch, capsys):
    import core.download
    from core.manifest import DownloadResult

    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(tmp_path / "q.json"))
    assert cli.main(["queue", "add", "https://a.com/1", "--json"]) == cli.EXIT_OK
    capsys.readouterr()

    monkeypatch.setattr(cli, "_ytdlp_missing", lambda: False)
    monkeypatch.setattr(cli, "_ffmpeg_missing", lambda: False)
    monkeypatch.setattr(
        core.download, "download_one",
        lambda *a, **k: DownloadResult(status="ok", path=str(tmp_path / "o.mp4")),
    )

    rc = cli.main(["queue", "run", "--json"])
    data = json.loads(capsys.readouterr().out)

    assert rc == cli.EXIT_OK
    for key in ("run", "done", "failed", "cancelled"):
        assert key in data
    assert data["run"] == 1
    assert data["done"] == 1
