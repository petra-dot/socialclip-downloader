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


import hashlib
import io
import json
import zipfile


def _wheel_bytes(version="2099.01.01"):
    """A minimal wheel: a zip whose root holds the yt_dlp package."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("yt_dlp/__init__.py", "")
        zf.writestr("yt_dlp/version.py", '__version__ = "%s"\n' % version)
    return buffer.getvalue()


def _release_opener(wheel, wheel_name, good_digest=True):
    sums = hashlib.sha256(wheel).hexdigest()
    if not good_digest:
        sums = "0" * 64

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def read(self):
            return self._payload

        def geturl(self):
            return "https://github.com/x/x"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opener(request, timeout=None):
        url = getattr(request, "full_url", request)
        if "latest" in url:
            body = json.dumps({
                "tag_name": "2099.01.01",
                "assets": [
                    {"name": "SHA2-256SUMS",
                     "browser_download_url": "https://github.com/x/sums"},
                    {"name": wheel_name,
                     "browser_download_url": "https://github.com/x/" + wheel_name},
                ],
            }).encode("utf-8")
            return _Response(body)
        if url.endswith("sums"):
            return _Response(("%s  %s\n" % (sums, wheel_name)).encode("utf-8"))
        return _Response(wheel)

    return opener


def test_parse_sums_reads_the_checksum_file():
    text = "abc123  yt_dlp-1-py3-none-any.whl\ndef456  other.zip\n"
    assert maintenance._parse_sums(text) == {
        "yt_dlp-1-py3-none-any.whl": "abc123",
        "other.zip": "def456",
    }


def test_install_ytdlp_unpacks_a_verified_wheel(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    wheel = _wheel_bytes()
    dest = tmp_path / "yt-dlp"
    version = maintenance.install_ytdlp(
        dest=str(dest),
        opener=_release_opener(wheel, "yt_dlp-2099.01.01-py3-none-any.whl"),
    )
    assert version == "2099.01.01"
    assert (dest / "yt_dlp" / "version.py").is_file()


def test_install_ytdlp_refuses_a_bad_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    dest = tmp_path / "yt-dlp"
    wheel = _wheel_bytes()
    try:
        maintenance.install_ytdlp(
            dest=str(dest),
            opener=_release_opener(
                wheel, "yt_dlp-2099.01.01-py3-none-any.whl", good_digest=False
            ),
        )
        raised = False
    except ValueError:
        raised = True
    assert raised
    assert not (dest / "yt_dlp").exists()


def test_install_ytdlp_keeps_a_previous_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    dest = tmp_path / "yt-dlp"
    (dest / "yt_dlp").mkdir(parents=True)
    (dest / "yt_dlp" / "version.py").write_text(
        '__version__ = "1.0.0"\n', encoding="utf-8"
    )
    maintenance.install_ytdlp(
        dest=str(dest),
        opener=_release_opener(_wheel_bytes(), "yt_dlp-2099.01.01-py3-none-any.whl"),
    )
    assert (tmp_path / "yt-dlp.prev" / "yt_dlp" / "version.py").is_file()
