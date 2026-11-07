from core.native import HOST_NAME
from core.native_install import host_manifest, manifest_path, wrapper_script


def test_chromium_manifest_allows_the_extension_origin():
    m = host_manifest("C:/app.exe", "abc123")
    assert m["name"] == HOST_NAME
    assert m["type"] == "stdio"
    assert m["path"] == "C:/app.exe"
    assert m["allowed_origins"] == ["chrome-extension://abc123/"]
    assert "allowed_extensions" not in m


def test_firefox_manifest_uses_the_addon_id_and_no_origins():
    m = host_manifest("/app", "socialclip@petra-dot", firefox=True)
    assert m["allowed_extensions"] == ["socialclip@petra-dot"]
    assert "allowed_origins" not in m


def test_wrapper_carries_the_host_flag():
    path, content = wrapper_script("C:/repo/socialclip_downloader.py", data="C:/data")
    assert "--native-host" in content
    assert path.endswith((".cmd", ".sh"))


def test_manifest_paths_differ_for_the_two_browsers():
    assert manifest_path(False, "C:/d") != manifest_path(True, "C:/d")
