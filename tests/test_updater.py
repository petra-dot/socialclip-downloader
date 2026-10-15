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
