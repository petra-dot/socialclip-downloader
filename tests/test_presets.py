from core.presets import (
    BUILTIN_PRESETS,
    Preset,
    PresetStore,
    default_presets_path,
    preset_from_dict,
    preset_to_dict,
)


def test_default_presets_path_honours_override(tmp_path, monkeypatch):
    override = tmp_path / "custom" / "presets.json"
    monkeypatch.setenv("SOCIALCLIP_PRESETS", str(override))
    assert default_presets_path() == str(override)


def test_default_presets_path_follows_data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("SOCIALCLIP_PRESETS", raising=False)
    monkeypatch.setenv("SOCIALCLIP_DATA", str(tmp_path / "data"))
    assert default_presets_path() == str(tmp_path / "data" / "presets.json")


def test_builtin_presets_present():
    names = [p.name for p in BUILTIN_PRESETS]
    assert names == [
        "Editor-safe 1080p", "Editor-safe 720p", "Audio only (MP3)",
        "Original quality", "Archive master",
    ]
    assert all(p.builtin for p in BUILTIN_PRESETS)


def test_preset_round_trip():
    preset = Preset(name="Mine", output="MP3", resolution="720", convert=False,
                    add_channel=True, add_timestamp=True, save_dir="D:/x",
                    cookies="c.txt")
    data = preset_to_dict(preset)
    assert "builtin" not in data
    again = preset_from_dict(data)
    assert again.name == "Mine" and again.output == "MP3" and again.convert is False
    assert again.add_channel is True and again.save_dir == "D:/x"


def test_preset_from_dict_needs_a_name():
    assert preset_from_dict({}) is None
    assert preset_from_dict({"output": "MP4"}) is None


def test_store_add_get_round_trip(tmp_path):
    store = PresetStore(str(tmp_path / "presets.json"))
    assert store.add(Preset(name="Mine", save_dir="D:/x")) is True
    store.save()
    again = PresetStore(str(tmp_path / "presets.json"))
    again.load()
    assert [p.name for p in again.user()] == ["Mine"]
    assert again.get("Mine").save_dir == "D:/x"


def test_store_get_unknown_is_none(tmp_path):
    store = PresetStore(str(tmp_path / "presets.json"))
    assert store.get("nope") is None


def test_store_all_is_builtins_then_user(tmp_path):
    store = PresetStore(str(tmp_path / "presets.json"))
    store.add(Preset(name="Mine"))
    assert [p.name for p in store.all()][:5] == [p.name for p in BUILTIN_PRESETS]
    assert store.all()[-1].name == "Mine"


def test_store_add_refuses_builtin_name(tmp_path):
    store = PresetStore(str(tmp_path / "presets.json"))
    assert store.add(Preset(name="Editor-safe 1080p")) is False


def test_store_add_replaces_same_name(tmp_path):
    store = PresetStore(str(tmp_path / "presets.json"))
    store.add(Preset(name="Mine", save_dir="A"))
    store.add(Preset(name="Mine", save_dir="B"))
    assert len(store.user()) == 1
    assert store.get("Mine").save_dir == "B"


def test_store_remove_and_rename_user_only(tmp_path):
    store = PresetStore(str(tmp_path / "presets.json"))
    store.add(Preset(name="Mine"))
    assert store.rename("Mine", "Yours") is True
    assert store.get("Yours") is not None
    assert store.rename("Editor-safe 1080p", "X") is False
    assert store.remove("Yours") is True
    assert store.remove("Editor-safe 1080p") is False
    assert store.user() == []


def test_store_load_ignores_bad_file(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text("{ not json")
    store = PresetStore(str(path))
    store.load()
    assert store.user() == []


def test_store_load_skips_non_dict_entries(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text('{"version": 1, "presets": [42]}')
    store = PresetStore(str(path))
    store.load()
    assert store.user() == []


def test_rename_rejects_a_duplicate_name(tmp_path):
    from core.presets import Preset, PresetStore
    store = PresetStore(str(tmp_path / "presets.json"))
    store.presets = [Preset(name="A"), Preset(name="B")]
    assert store.rename("A", "B") is False
    assert [p.name for p in store.presets] == ["A", "B"]
    assert store.rename("A", "C") is True
    assert [p.name for p in store.presets] == ["C", "B"]
