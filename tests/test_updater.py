import pytest

from core.updater import (
    AssetInfo,
    is_newer,
    parse_version,
    release_from_json,
    select_asset,
    verify_digest,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("v0.9.2", (0, 9, 2)),
        ("0.9.2", (0, 9, 2)),
        ("v0.10.0", (0, 10, 0)),
        ("1.2", (1, 2)),
        ("", ()),
        ("nonsense", ()),
        ("v0.9.2-beta", (0, 9, 2)),
    ],
)
def test_parse_version(text, expected):
    assert parse_version(text) == expected


@pytest.mark.parametrize(
    "latest,current,expected",
    [
        ("v0.10.0", "0.9.2", True),
        ("v0.9.2", "0.9.2", False),
        ("v0.9.1", "0.9.2", False),
        ("v0.9.10", "0.9.2", True),
        ("", "0.9.2", False),
    ],
)
def test_is_newer(latest, current, expected):
    assert is_newer(latest, current) is expected


def test_release_from_json_full():
    data = {
        "tag_name": "v0.10.0",
        "html_url": "https://github.com/petra-dot/socialclip-downloader/releases/tag/v0.10.0",
        "assets": [
            {"name": "socialclip-downloader-windows.exe",
             "browser_download_url": "https://github.com/x/a.exe",
             "digest": "sha256:abc123"},
            {"name": "socialclip-windows.exe",
             "browser_download_url": "https://github.com/x/cli.exe"},
        ],
    }
    release = release_from_json(data)
    assert release.tag == "v0.10.0"
    assert release.version == "0.10.0"
    assert release.assets[0].digest == "abc123"
    assert release.assets[1].digest is None


def test_release_from_json_missing_fields():
    release = release_from_json({"tag_name": "v1.0.0"})
    assert release.assets == []
    assert release.page_url


def test_release_from_json_drops_incomplete_assets():
    data = {"tag_name": "v1", "assets": [{"name": "x"}, {"browser_download_url": "u"}]}
    assert release_from_json(data).assets == []


def test_select_asset_by_platform():
    assets = [
        AssetInfo("socialclip-downloader-windows.exe", "u1", "d1"),
        AssetInfo("socialclip-downloader-macos", "u2", "d2"),
    ]
    assert select_asset(assets, "win32").name.endswith("windows.exe")
    assert select_asset(assets, "darwin").name.endswith("macos")
    assert select_asset(assets, "linux") is None


def test_verify_digest_match_and_mismatch(tmp_path):
    import hashlib
    path = tmp_path / "f.bin"
    path.write_bytes(b"hello")
    good = hashlib.sha256(b"hello").hexdigest()
    assert verify_digest(str(path), good) is True
    assert verify_digest(str(path), "deadbeef") is False
    assert not path.exists()  # mismatch deletes the file


def test_verify_digest_no_expected_returns_false(tmp_path):
    path = tmp_path / "f.bin"
    path.write_bytes(b"hello")
    assert verify_digest(str(path), None) is False
    assert not path.exists()  # no digest deletes the file too


from core.updater import DownloadCancelled, download_asset, fetch_latest_release


class _FakeResponse:
    def __init__(self, body, headers=None):
        self._body = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, size=-1):
        if size is None or size < 0:
            data, self._body = self._body, b""
            return data
        data, self._body = self._body[:size], self._body[size:]
        return data


def test_fetch_latest_release_parses(monkeypatch):
    payload = b'{"tag_name": "v0.10.0", "assets": []}'
    monkeypatch.setattr(
        "core.updater.urllib.request.urlopen",
        lambda req, timeout=None: _FakeResponse(payload),
    )
    release = fetch_latest_release()
    assert release.tag == "v0.10.0"


def test_download_asset_writes_and_reports_progress(tmp_path):
    asset = AssetInfo("x", "https://github.com/petra-dot/socialclip-downloader/releases/x", None)
    seen = []
    dest = str(tmp_path / "out.bin")
    body = b"abcdef" * 20000
    download_asset(
        asset, dest, progress=lambda done, total: seen.append(done),
        opener=lambda req, timeout=None: _FakeResponse(body, {"Content-Length": str(len(body))}),
    )
    assert open(dest, "rb").read() == body
    assert seen and seen[-1] == len(body)


def test_download_asset_refuses_foreign_host(tmp_path):
    asset = AssetInfo("x", "https://evil.example.com/x", None)
    with pytest.raises(ValueError):
        download_asset(asset, str(tmp_path / "o"), opener=lambda *a, **k: _FakeResponse(b""))


def test_download_asset_honors_cancel(tmp_path):
    asset = AssetInfo("x", "https://github.com/petra-dot/socialclip-downloader/releases/x", None)
    with pytest.raises(DownloadCancelled):
        download_asset(
            asset, str(tmp_path / "o"), cancel=lambda: True,
            opener=lambda req, timeout=None: _FakeResponse(b"x" * 10, {}),
        )


from core.updater import ApplyPlan, cleanup_update_temp, update_temp_path, write_batch_fallback


def test_update_temp_path_is_prefixed():
    path = update_temp_path("0.10.0")
    assert "socialclip-update-0.10.0" in path


def test_update_temp_path_sanitizes_version():
    import os
    path = update_temp_path("release/1.0")
    name = os.path.basename(path)
    assert os.sep not in name
    assert "/" not in name
    assert ".." not in name
    assert "socialclip-update-release_1.0.exe" == name


def test_write_batch_fallback_names_source_and_target(tmp_path):
    plan = ApplyPlan(target="C:/app/old.exe", source="C:/tmp/new.exe")
    bat = write_batch_fallback(plan, temp_dir=str(tmp_path))
    assert bat.endswith(".bat")
    text = open(bat, encoding="ascii").read()
    assert "C:/app/old.exe" in text
    assert "C:/tmp/new.exe" in text
    assert "start" in text


def test_cleanup_update_temp_removes_leftovers(tmp_path):
    (tmp_path / "socialclip-update-0.10.0.exe").write_bytes(b"x")
    (tmp_path / "unrelated.exe").write_bytes(b"x")
    removed = cleanup_update_temp(temp_dir=str(tmp_path))
    assert removed == 1
    assert not (tmp_path / "socialclip-update-0.10.0.exe").exists()
    assert (tmp_path / "unrelated.exe").exists()


def test_apply_update_retries_then_succeeds(monkeypatch, tmp_path):
    import core.updater as updater
    source = tmp_path / "src.exe"
    source.write_bytes(b"new")
    target = tmp_path / "tgt.exe"
    target.write_bytes(b"old")
    monkeypatch.setattr(updater.sys, "executable", str(source))
    monkeypatch.setattr(updater, "_spawn_detached", lambda cmd: None)
    calls = {"n": 0}
    real_copy = updater.shutil.copy2

    def flaky_copy(a, b):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("locked")
        return real_copy(a, b)

    monkeypatch.setattr(updater.shutil, "copy2", flaky_copy)
    rc = updater.apply_update(str(target), timeout=5, sleep=lambda s: None)
    assert rc == 0
    assert target.read_bytes() == b"new"
    assert calls["n"] == 3
