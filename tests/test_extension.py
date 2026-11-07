import json
from pathlib import Path

import pytest

from core.extension import CHROMIUM_EXTENSION_ID, chrome_id_from_key, copy_tree, ensure_installed

EXT = Path(__file__).resolve().parent.parent / "extension"

# The key the shipped manifest carries. Pinned here so a refactor cannot
# silently change the id every registered host points at.
KEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArx5Z3HNouM+Lbec9iojW/J+BIFZC"
    "ks574T2ewXiDshuesSllEEGUaMW5DCtIubtoI/fcCD1q6od+fp5tO5VT47suTKL/ReSvKifOD"
    "6pmVD6spdNEjRZv7TNFS59ErSIuSEeOPAm781HSEnU7O2E+sqvsbBR4ZQA8vbivbR334XIBm"
    "M30AV9K+TjWdPSpw81G0ga1Bi5bs/SM11CJj0D2bhLIH+3i/2wUKeVur7Xs/y3kBGK4GUNha"
    "HWQfqUk4QCa6w2m0J4GTysqNRQy8sVlJUkc7aMAKTK2ryuupJcKuctBv7qux8iGvXWYh/P4A"
    "C0txg3AXB+3VE7J3UdFYLeiwQIDAQAB"
)


def test_chrome_id_from_key_is_stable():
    assert chrome_id_from_key(KEY) == CHROMIUM_EXTENSION_ID


def test_chrome_id_uses_only_letters_a_to_p():
    ident = chrome_id_from_key(KEY)
    assert len(ident) == 32
    assert all("a" <= char <= "p" for char in ident)


def test_manifest_key_matches_the_baked_id():
    manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    assert chrome_id_from_key(manifest["key"]) == CHROMIUM_EXTENSION_ID


def test_repo_folder_is_directly_loadable():
    # Chrome and Edge refuse a folder whose manifest is not named manifest.json.
    assert (EXT / "manifest.json").is_file()


def test_copy_tree_copies_then_updates_changed_files(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "a.js").write_text("one", encoding="utf-8")
    (source / "sub").mkdir()
    dest = tmp_path / "dest"

    copy_tree(str(source), str(dest))
    assert (dest / "a.js").read_text(encoding="utf-8") == "one"

    (source / "a.js").write_text("two", encoding="utf-8")
    copy_tree(str(source), str(dest))
    assert (dest / "a.js").read_text(encoding="utf-8") == "two"


def test_copy_tree_can_skip_names(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "keep.js").write_text("x", encoding="utf-8")
    (source / "skip.json").write_text("{}", encoding="utf-8")
    dest = tmp_path / "dest"

    copy_tree(str(source), str(dest), skip=("skip.json",))
    assert (dest / "keep.js").is_file()
    assert not (dest / "skip.json").exists()


def test_ensure_installed_writes_a_loadable_folder_for_each_browser(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    paths = ensure_installed()

    chromium = Path(paths["chromium"])
    firefox = Path(paths["firefox"])
    chrome_manifest = json.loads((chromium / "manifest.json").read_text(encoding="utf-8"))
    firefox_manifest = json.loads((firefox / "manifest.json").read_text(encoding="utf-8"))

    assert chrome_manifest["background"]["service_worker"] == "background.js"
    assert "browser_specific_settings" in firefox_manifest
    assert chrome_manifest["key"] == KEY
    assert (chromium / "background.js").is_file()
    assert (firefox / "popup.html").is_file()
    assert not (chromium / "manifest.firefox.json").exists()


@pytest.mark.parametrize("name", ["chromium", "firefox"])
def test_each_installed_folder_uses_the_plain_manifest_name(tmp_path, monkeypatch, name):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    folder = Path(ensure_installed()[name])
    assert [p.name for p in folder.glob("manifest*.json")] == ["manifest.json"]


def test_copy_tree_removes_a_skipped_name_left_behind(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "keep.js").write_text("x", encoding="utf-8")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "skip.json").write_text("{}", encoding="utf-8")

    copy_tree(str(source), str(dest), skip=("skip.json",))
    assert not (dest / "skip.json").exists()


def test_copy_tree_keeps_subfolders(tmp_path):
    source = tmp_path / "src"
    (source / "icons").mkdir(parents=True)
    (source / "icons" / "16.png").write_bytes(b"x")
    dest = tmp_path / "dest"

    copy_tree(str(source), str(dest))
    assert (dest / "icons" / "16.png").read_bytes() == b"x"


def test_installed_folder_carries_the_icons(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path))
    chromium = Path(ensure_installed()["chromium"])
    assert (chromium / "icons" / "128.png").is_file()


def test_build_package_writes_the_variant_manifest(tmp_path):
    from core.extension import build_package

    dest = tmp_path / "pkg"
    build_package(str(dest), "firefox")
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert "browser_specific_settings" in manifest
    assert (dest / "background.js").is_file()
    assert not (dest / "manifest.firefox.json").exists()


def test_firefox_xpi_url_points_at_the_release_asset():
    from core.extension import firefox_xpi_url

    assert firefox_xpi_url("1.2.3") == (
        "https://github.com/petra-dot/socialclip-downloader/releases/download/"
        "v1.2.3/socialclip-firefox.xpi"
    )


def test_fetch_firefox_xpi_writes_the_signed_file(tmp_path):
    import io

    from core.extension import fetch_firefox_xpi

    def fake_opener(url):
        assert url.endswith("socialclip-firefox.xpi")
        return io.BytesIO(b"PK\x03\x04signed")

    path = fetch_firefox_xpi("1.2.3", dest_dir=str(tmp_path), opener=fake_opener)
    assert Path(path).read_bytes() == b"PK\x03\x04signed"


def test_fetch_firefox_xpi_rejects_a_non_archive(tmp_path):
    import io

    from core.extension import fetch_firefox_xpi

    with __import__("pytest").raises(ValueError):
        fetch_firefox_xpi(
            "1.2.3", dest_dir=str(tmp_path), opener=lambda url: io.BytesIO(b"<html>")
        )


def test_build_package_stamps_the_app_version(tmp_path):
    from core.version import __version__

    from core.extension import build_package

    dest = tmp_path / "pkg"
    build_package(str(dest), "chromium")
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == __version__


def test_build_package_removes_the_legacy_manifest_name(tmp_path):
    from core.extension import build_package

    dest = tmp_path / "pkg"
    dest.mkdir()
    (dest / "manifest.chromium.json").write_text("{}", encoding="utf-8")
    build_package(str(dest), "chromium")
    assert not (dest / "manifest.chromium.json").exists()
