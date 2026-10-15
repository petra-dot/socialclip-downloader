from workers.maintenance_worker import run_repairs


def test_run_repairs_calls_the_right_installer(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    calls = []

    # Patch the names the worker module bound, not core.maintenance's: the
    # worker imported them directly.
    from workers import maintenance_worker

    monkeypatch.setattr(
        maintenance_worker, "install_ytdlp",
        lambda dest=None, opener=None: calls.append("yt-dlp") or "1.0",
    )
    monkeypatch.setattr(
        maintenance_worker, "install_ffmpeg",
        lambda dest=None, opener=None: calls.append("ffmpeg") or "1.0",
    )
    monkeypatch.setattr(
        maintenance_worker, "install_deno",
        lambda dest=None, opener=None: calls.append("deno") or "1.0",
    )
    monkeypatch.setattr(maintenance_worker, "check_all", lambda *a, **kw: [])

    seen = []
    result = run_repairs(
        ["yt-dlp", "js-runtime"],
        progress=lambda key, detail: seen.append((key, detail)),
    )

    # The right installer ran for each key.
    assert calls == ["yt-dlp", "deno"]
    assert result == []
    # yt-dlp gets an extra note: the running process still holds the old copy.
    assert seen == [
        ("yt-dlp", "installing"),
        ("yt-dlp", "installed 1.0"),
        ("yt-dlp", "restart to use the new version"),
        ("js-runtime", "installing"),
        ("js-runtime", "installed 1.0"),
    ]


def test_run_repairs_reports_failure_and_continues(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    calls = []

    from workers import maintenance_worker

    def boom(dest=None, opener=None):
        calls.append("ffmpeg")
        raise RuntimeError("network down")

    monkeypatch.setattr(maintenance_worker, "install_ffmpeg", boom)
    monkeypatch.setattr(
        maintenance_worker, "install_deno",
        lambda dest=None, opener=None: calls.append("deno") or "1.0",
    )
    monkeypatch.setattr(
        maintenance_worker, "check_all", lambda *a, **kw: ["fresh"],
    )

    seen = []
    result = run_repairs(
        ["ffmpeg", "js-runtime"],
        progress=lambda key, detail: seen.append((key, detail)),
    )

    # The failed component did not abort the loop.
    assert calls == ["ffmpeg", "deno"]
    assert seen == [
        ("ffmpeg", "installing"),
        ("ffmpeg", "failed: network down"),
        ("js-runtime", "installing"),
        ("js-runtime", "installed 1.0"),
    ]
    # A fresh re-check is returned.
    assert result == ["fresh"]


def test_run_repairs_reports_an_unknown_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    from workers import maintenance_worker
    monkeypatch.setattr(maintenance_worker, "check_all", lambda *a, **kw: [])
    seen = []
    maintenance_worker.run_repairs(
        ["yt-dlpp"], progress=lambda k, d: seen.append((k, d)),
    )
    assert seen == [("yt-dlpp", "unknown component")]
