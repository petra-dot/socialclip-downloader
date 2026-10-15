from core.doctor import DOCTOR_SCHEMA_VERSION, run_checks


def test_report_shape_and_version():
    report = run_checks(
        which=lambda name: "/usr/bin/ffmpeg",
        exists=lambda p: False,
        probe=lambda: (True, "reachable"),
        runner=lambda cmd: _FakeProc("ffmpeg version 6.1.1\nbuilt with gcc"),
    )
    assert report["schema_version"] == DOCTOR_SCHEMA_VERSION == "1.2"
    assert report["ffmpeg"]["found"] is True
    assert report["ffmpeg"]["path"] == "/usr/bin/ffmpeg"
    assert report["ffmpeg"]["version"].startswith("ffmpeg version 6.1.1")
    assert isinstance(report["cookies"], list)
    assert set(report["cookies"][0]) == {"platform", "found", "path"}
    assert report["network"] == {"ok": True, "detail": "reachable"}
    assert set(report["js_runtime"]) == {"found", "name", "path", "candidates"}
    assert set(report["ytdlp"]) == {"version", "age_days", "stale"}


def test_missing_ffmpeg_is_reported_not_raised():
    report = run_checks(
        which=lambda name: None,
        exists=lambda p: False,
        probe=lambda: (False, "offline"),
        runner=lambda cmd: _FakeProc("", 1),
        candidate_dirs=[],
    )
    assert report["ffmpeg"]["found"] is False
    assert report["ffmpeg"]["path"] is None
    assert report["ffmpeg"]["version"] is None
    assert report["network"] == {"ok": False, "detail": "offline"}


def test_probe_exception_degrades_to_none():
    def boom():
        raise OSError("no route")

    report = run_checks(
        which=lambda name: None, exists=lambda p: False,
        probe=boom, runner=lambda cmd: _FakeProc("", 1), candidate_dirs=[],
    )
    assert report["network"]["ok"] is None
    assert "no route" in report["network"]["detail"]


def test_no_js_runtime_is_reported_not_raised():
    report = run_checks(
        which=lambda name: None, exists=lambda p: False,
        probe=lambda: (True, "reachable"), runner=lambda cmd: _FakeProc("", 1),
        candidate_dirs=[],
    )
    assert report["js_runtime"]["found"] is False
    assert report["js_runtime"]["name"] is None


def test_stale_ytdlp_is_reported(monkeypatch):
    from core import doctor
    monkeypatch.setattr(doctor, "ytdlp_version", lambda: "2020.01.01")
    report = run_checks(
        which=lambda name: None, exists=lambda p: False,
        probe=lambda: (True, "reachable"), runner=lambda cmd: _FakeProc("", 1),
        candidate_dirs=[],
    )
    assert report["ytdlp"]["version"] == "2020.01.01"
    assert report["ytdlp"]["stale"] is True
    assert report["ytdlp"]["age_days"] > 90


class _FakeProc:
    def __init__(self, out, rc=0):
        self.stdout = out
        self.returncode = rc
