import os
import sys

from core import maintenance
from core.maintenance import Component


def _by_key(components):
    return {c.key: c for c in components}


def test_check_all_reports_missing_ytdlp(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    # yt-dlp is installed in this environment, so force the "missing" case.
    monkeypatch.setattr(maintenance, "_ytdlp_version", lambda: "")
    # find_ffmpeg scans host candidate dirs too, so neutralise the
    # filesystem probe as well as PATH to force the "missing" case.
    comps = _by_key(maintenance.check_all(
        which=lambda _n: None, exists=lambda _p: False, runner=lambda _c: None,
    ))
    assert comps["yt-dlp"].state == "missing"
    assert comps["yt-dlp"].action == "install"
    assert comps["ffmpeg"].state == "missing"
    assert comps["js-runtime"].state == "missing"


def test_check_all_reports_stale_ytdlp(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    monkeypatch.setattr(maintenance, "_ytdlp_version", lambda: "2020.01.01")
    comps = _by_key(maintenance.check_all(which=lambda _n: None))
    assert comps["yt-dlp"].state == "stale"
    assert comps["yt-dlp"].action == "update"


def test_check_all_reports_found_components(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    monkeypatch.setattr(maintenance, "_ytdlp_version", lambda: "2099.01.01")
    monkeypatch.setattr(
        maintenance, "find_ffmpeg", lambda **kw: "/usr/bin/ffmpeg"
    )
    monkeypatch.setattr(
        maintenance, "find_js_runtime", lambda which=None: ("node", "/usr/bin/node")
    )
    comps = _by_key(maintenance.check_all())
    assert comps["yt-dlp"].state == "ok"
    assert comps["ffmpeg"].state == "ok"
    assert comps["js-runtime"].state == "ok"
    assert comps["app"].state == "ok"
    assert comps["data-dir"].state == "ok"


def test_plan_repairs_selects_only_repairable():
    comps = [
        Component("yt-dlp", "yt-dlp", "stale", action="update"),
        Component("ffmpeg", "ffmpeg", "ok"),
        Component("js-runtime", "JavaScript runtime", "missing", action="install"),
        Component("app", "App", "stale", action="update"),
        Component("data-dir", "Data directory", "ok"),
    ]
    assert maintenance.plan_repairs(comps) == ["yt-dlp", "js-runtime"]


def test_plan_repairs_ignores_unknown():
    comps = [Component("yt-dlp", "yt-dlp", "unknown", action="install")]
    assert maintenance.plan_repairs(comps) == []


def test_latest_ytdlp_parses_the_release(monkeypatch):
    payload = {
        "tag_name": "2026.08.19",
        "assets": [
            {"name": "SHA2-256SUMS",
             "browser_download_url": "https://github.com/x/sums"},
            {"name": "yt_dlp-2026.08.19-py3-none-any.whl",
             "browser_download_url": "https://github.com/x/w.whl"},
        ],
    }
    monkeypatch.setattr(maintenance, "_get_json", lambda url, opener=None: payload)
    version, wheel, sums = maintenance.latest_ytdlp()
    assert version == "2026.08.19"
    assert wheel.endswith(".whl")
    assert sums.endswith("sums")


def test_get_refuses_http_and_unlisted_hosts():
    import pytest as _pytest
    from core.maintenance import _get
    for url in ("http://github.com/x", "https://evil.example/x"):
        with _pytest.raises(ValueError):
            _get(url)


def test_redirect_handler_refuses_an_unlisted_host():
    import pytest as _pytest
    from core.maintenance import _ValidatingRedirectHandler
    handler = _ValidatingRedirectHandler()
    with _pytest.raises(ValueError):
        handler.redirect_request(
            None, None, 302, "Found", {}, "http://evil.example/x"
        )


def test_redirect_handler_allows_an_allow_listed_host():
    import urllib.request

    from core.maintenance import _ValidatingRedirectHandler
    handler = _ValidatingRedirectHandler()
    # Must not raise for an allow-listed HTTPS host (the GitHub asset CDN).
    request = urllib.request.Request("https://github.com/x")
    result = handler.redirect_request(
        request, None, 302, "Found", {},
        "https://objects.githubusercontent.com/x",
    )
    assert result is not None
