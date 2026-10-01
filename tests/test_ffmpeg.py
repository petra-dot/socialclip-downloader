import os

import utils.ffmpeg as ffmpeg_mod
from utils.ffmpeg import find_ffmpeg


def test_finds_ffmpeg_on_path():
    assert find_ffmpeg(
        env={}, which=lambda name: "/x/ffmpeg", exists=lambda p: False, candidate_dirs=[]
    ) == "/x/ffmpeg"


def test_env_override_wins_over_path():
    assert find_ffmpeg(
        env={"SOCIALCLIP_FFMPEG": "/custom/ffmpeg"},
        which=lambda name: "/x/ffmpeg",
        exists=lambda p: p == "/custom/ffmpeg",
        candidate_dirs=[],
    ) == "/custom/ffmpeg"


def test_ignores_env_override_when_path_missing():
    assert find_ffmpeg(
        env={"SOCIALCLIP_FFMPEG": "/gone/ffmpeg"},
        which=lambda name: "/x/ffmpeg",
        exists=lambda p: False,
        candidate_dirs=[],
    ) == "/x/ffmpeg"


def test_falls_back_to_candidate_dir():
    target = os.path.join("/opt/homebrew/bin", "ffmpeg")
    assert find_ffmpeg(
        env={},
        which=lambda name: None,
        exists=lambda p: p == target,
        candidate_dirs=["/opt/homebrew/bin"],
    ) == target


def test_returns_empty_when_missing_everywhere():
    assert find_ffmpeg(
        env={}, which=lambda name: None, exists=lambda p: False, candidate_dirs=["/nope"]
    ) == ""


def test_bundled_ffmpeg_wins_when_present(tmp_path):
    bundled = tmp_path / "ffmpeg"
    bundled.write_text("")
    assert find_ffmpeg(
        env={},
        which=lambda name: "/x/ffmpeg",
        exists=lambda p: os.path.abspath(p) == os.path.abspath(str(bundled)),
        candidate_dirs=[],
        bundle_dir=str(tmp_path),
    ) == str(bundled)


def test_ffmpeg_path_falls_back_to_bare_name(monkeypatch):
    monkeypatch.setattr(ffmpeg_mod, "find_ffmpeg", lambda **kwargs: "")
    ffmpeg_mod.reset_cache()
    assert ffmpeg_mod.ffmpeg_path() == "ffmpeg"
    ffmpeg_mod.reset_cache()


def test_ffprobe_path_resolves_next_to_ffmpeg(tmp_path, monkeypatch):
    ff = tmp_path / "ffmpeg"
    fp = tmp_path / "ffprobe"
    ff.write_text("")
    fp.write_text("")
    monkeypatch.setattr(ffmpeg_mod, "ffmpeg_path", lambda: str(ff))
    assert ffmpeg_mod.ffprobe_path() == str(fp)


def test_ffprobe_path_falls_back_to_bare_name(monkeypatch):
    monkeypatch.setattr(ffmpeg_mod, "ffmpeg_path", lambda: "ffmpeg")
    assert ffmpeg_mod.ffprobe_path() == "ffprobe"
