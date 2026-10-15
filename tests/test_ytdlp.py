import datetime

from utils.ytdlp import (
    RUNTIMES, find_js_runtime, is_stale, js_runtimes, version_age_days,
)


def test_find_js_runtime_prefers_deno_then_node():
    node_only = {"node": r"C:\nodejs\node.exe"}
    assert find_js_runtime(which=node_only.get) == ("node", r"C:\nodejs\node.exe")

    both = {"deno": r"C:\deno\deno.exe", "node": r"C:\nodejs\node.exe"}
    assert find_js_runtime(which=both.get)[0] == "deno"


def test_find_js_runtime_when_none_installed():
    assert find_js_runtime(which=lambda name: None) == ("", "")


def test_find_js_runtime_survives_a_failing_lookup():
    def boom(name):
        raise OSError("path is broken")

    assert find_js_runtime(which=boom) == ("", "")


def test_js_runtimes_option_shape():
    assert js_runtimes(which=lambda name: None) == {}
    got = js_runtimes(
        which=lambda name: "C:/x/node.exe" if name == "node" else None
    )
    assert got == {"node": {"path": "C:/x/node.exe"}}


def test_version_age_days_parses_a_date_stamp():
    today = datetime.date(2026, 10, 16)
    assert version_age_days("2026.07.04", today=today) == 104
    assert version_age_days("2026.10.16", today=today) == 0


def test_version_age_days_rejects_non_dates():
    today = datetime.date(2026, 10, 16)
    assert version_age_days("", today=today) is None
    assert version_age_days("2026.07", today=today) is None
    assert version_age_days("nightly", today=today) is None
    assert version_age_days("2026.13.40", today=today) is None


def test_is_stale_threshold():
    today = datetime.date(2026, 10, 16)
    assert is_stale("2026.07.04", today=today) is True
    assert is_stale("2026.10.01", today=today) is False
    assert is_stale("not-a-date", today=today) is False


def test_runtimes_order_and_membership():
    assert RUNTIMES[0] == "deno"
    assert "node" in RUNTIMES


import os
import subprocess
import sys
import textwrap


def test_managed_ytdlp_dir_uses_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    from utils import ytdlp
    assert ytdlp.managed_ytdlp_dir() == os.path.join(str(tmp_path), "yt-dlp")


def test_load_prefers_managed_copy(tmp_path, monkeypatch):
    """A package in the managed dir must win over the installed one."""
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    pkg = tmp_path / "yt-dlp" / "yt_dlp"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "version.py").write_text('__version__ = "9999.01.01"\n',
                                     encoding="utf-8")

    code = textwrap.dedent(
        """
        from utils.ytdlp import load
        state = load()
        from yt_dlp.version import __version__
        print(state, __version__)
        """
    )
    env = dict(os.environ, PYTHONPATH=os.getcwd())
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env,
        cwd=os.getcwd(),
    )
    assert out.stdout.split() == ["managed", "9999.01.01"], out.stderr


def test_load_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    from utils import ytdlp
    first = ytdlp.load()
    second = ytdlp.load()
    assert first == second
    assert sys.path.count(ytdlp.managed_ytdlp_dir()) == 1


def test_find_js_runtime_prefers_managed_deno(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    name = "deno.exe" if sys.platform == "win32" else "deno"
    (bin_dir / name).write_text("", encoding="utf-8")
    from utils import ytdlp
    found_name, found_path = ytdlp.find_js_runtime(which=lambda _n: None)
    assert found_name == "deno"
    assert found_path == os.path.join(str(bin_dir), name)
