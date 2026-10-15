import json
import os
import subprocess
import sys

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
    # Isolate the default location too, so the test does not depend on whether
    # the developer's machine happens to have a real queue.json.
    default_dir = tmp_path / "default"
    default_dir.mkdir()
    monkeypatch.setattr(
        "sites.cookies.default_cookie_dir", lambda: str(default_dir)
    )
    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(tmp_path / "q.json"))

    rc = cli.main(["queue", "add", "https://a.com/1", "--json"])
    capsys.readouterr()

    assert rc == cli.EXIT_OK
    assert (tmp_path / "q.json").exists()
    assert not (default_dir / "queue.json").exists()


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


def test_queue_add_expand_lists_and_enqueues(monkeypatch, tmp_path):
    import cli
    from core.collections import CollectionEntry, ExpandResult

    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(tmp_path / "queue.json"))
    monkeypatch.setattr(
        cli, "_expand_for_cli",
        lambda url, cookies: ExpandResult(
            platform="youtube",
            entries=[CollectionEntry("https://www.youtube.com/watch?v=a", "A")],
        ),
    )
    rc = cli.main(["queue", "add", "--expand", "https://www.youtube.com/@x"])
    assert rc == 0

    from core.queue import QueueStore
    store = QueueStore(str(tmp_path / "queue.json"))
    store.load()
    assert [j.title for j in store.jobs] == ["A"]


def test_queue_add_expand_skips_already_queued(monkeypatch, tmp_path):
    import cli
    from core.collections import CollectionEntry, ExpandResult

    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(tmp_path / "queue.json"))
    assert cli.main(
        ["queue", "add", "https://www.youtube.com/watch?v=a"]
    ) == cli.EXIT_OK

    monkeypatch.setattr(
        cli, "_expand_for_cli",
        lambda url, cookies: ExpandResult(
            platform="youtube",
            entries=[
                CollectionEntry("https://www.youtube.com/watch?v=a", "A"),
                CollectionEntry("https://www.youtube.com/watch?v=b", "B"),
            ],
        ),
    )
    rc = cli.main(["queue", "add", "--expand", "https://www.youtube.com/@x"])
    assert rc == cli.EXIT_OK

    from core.queue import QueueStore
    store = QueueStore(str(tmp_path / "queue.json"))
    store.load()
    assert [j.url for j in store.jobs] == [
        "https://www.youtube.com/watch?v=a",
        "https://www.youtube.com/watch?v=b",
    ]


def test_queue_run_rejects_bad_jobs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(tmp_path / "q.json"))
    rc = cli.main(["queue", "run", "--jobs", "99"])
    assert rc == cli.EXIT_USAGE == 2
    assert "invalid choice" in capsys.readouterr().err


def test_queue_run_archive_flag_reaches_download_one(tmp_path, monkeypatch, capsys):
    import core.download
    from core.manifest import DownloadResult

    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(tmp_path / "q.json"))
    assert cli.main(["queue", "add", "https://a.com/1", "--json"]) == cli.EXIT_OK
    capsys.readouterr()

    seen = {}

    def fake_download_one(url, **kw):
        seen.update(kw)
        return DownloadResult(status="ok", path=str(tmp_path / "o.mp4"))

    monkeypatch.setattr(cli, "_ytdlp_missing", lambda: False)
    monkeypatch.setattr(cli, "_ffmpeg_missing", lambda: False)
    monkeypatch.setattr(core.download, "download_one", fake_download_one)

    rc = cli.main(["queue", "run", "--archive", "--json"])
    data = json.loads(capsys.readouterr().out)

    assert rc == cli.EXIT_OK
    assert seen.get("archive", "").endswith("archive.txt")
    assert "skipped" in data


def test_queue_archive_clear_removes_the_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(tmp_path / "q.json"))
    target = tmp_path / "archive.txt"
    target.write_text("youtube abc\n")

    rc = cli.main(["queue", "archive", "--clear", "--json"])
    data = json.loads(capsys.readouterr().out)

    assert rc == cli.EXIT_OK
    assert data["cleared"] is True
    assert not target.exists()


def test_queue_add_stores_browser_cookies(tmp_path, monkeypatch):
    import cli
    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(tmp_path / "q.json"))
    rc = cli.main(["queue", "add", "https://a.com/1",
                   "--cookies-from-browser", "chrome"])
    assert rc == cli.EXIT_OK
    from core.queue import QueueStore
    store = QueueStore(str(tmp_path / "q.json"))
    store.load()
    assert store.jobs[0].options["cookies_from_browser"] == "chrome"


def test_queue_add_rejects_unknown_browser(tmp_path, monkeypatch, capsys):
    import cli
    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(tmp_path / "q.json"))
    rc = cli.main(["queue", "add", "https://a.com/1",
                   "--cookies-from-browser", "netscape"])
    assert rc == cli.EXIT_USAGE
    assert "invalid choice" in capsys.readouterr().err


def test_queue_retry_requeues_failed(tmp_path, monkeypatch, capsys):
    import cli
    import json
    from core.queue import QueueStore

    monkeypatch.setenv("SOCIALCLIP_QUEUE", str(tmp_path / "q.json"))
    assert cli.main(["queue", "add", "https://a.com/1", "--json"]) == cli.EXIT_OK
    capsys.readouterr()

    store = QueueStore(str(tmp_path / "q.json"))
    store.load()
    store.jobs[0].state = "failed"
    store.save()

    rc = cli.main(["queue", "retry", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == cli.EXIT_OK
    assert data["retried"] == 1

    again = QueueStore(str(tmp_path / "q.json"))
    again.load()
    assert again.jobs[0].state == "pending"
