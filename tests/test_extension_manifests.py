import json
from pathlib import Path

EXT = Path(__file__).resolve().parent.parent / "extension"


def test_firefox_manifest_has_an_addon_id_and_no_service_worker():
    manifest = json.loads((EXT / "manifest.firefox.json").read_text(encoding="utf-8"))
    assert manifest["browser_specific_settings"]["gecko"]["id"] == "socialclip@petra-dot"
    assert "service_worker" not in manifest["background"]
    assert manifest["background"]["scripts"] == ["background.js"]


def test_chromium_manifest_uses_a_service_worker():
    manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["background"]["service_worker"] == "background.js"
    assert "browser_specific_settings" not in manifest


def test_both_manifests_ask_for_native_messaging():
    for name in ("manifest.json", "manifest.firefox.json"):
        manifest = json.loads((EXT / name).read_text(encoding="utf-8"))
        assert "nativeMessaging" in manifest["permissions"]
        assert manifest["action"]["default_popup"] == "popup.html"
