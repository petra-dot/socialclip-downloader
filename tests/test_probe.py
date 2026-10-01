from core.probe import probe_media

FFPROBE_JSON = """
{"streams":[
  {"codec_type":"video","codec_name":"h264","height":1080},
  {"codec_type":"audio","codec_name":"aac"}
],"format":{"format_name":"mov,mp4,m4a,3gp,3g2,mj2"}}
"""


class _Proc:
    returncode = 0

    def __init__(self, out):
        self.stdout = out


def test_probe_parses_video_and_audio():
    info = probe_media("x.mp4", runner=lambda cmd: _Proc(FFPROBE_JSON))
    assert info["vcodec"] == "h264"
    assert info["acodec"] == "aac"
    assert info["height"] == 1080
    assert "mp4" in info["container"]


def test_probe_audio_only_has_empty_vcodec():
    payload = '{"streams":[{"codec_type":"audio","codec_name":"mp3"}],"format":{"format_name":"mp3"}}'
    info = probe_media("x.mp3", runner=lambda cmd: _Proc(payload))
    assert info["vcodec"] == ""
    assert info["acodec"] == "mp3"
    assert info["height"] == 0


def test_probe_failure_never_raises():
    def boom(cmd):
        raise OSError("no ffprobe")

    info = probe_media("x.mp4", runner=boom)
    assert info == {"vcodec": "", "acodec": "", "height": 0, "container": ""}


def test_probe_bad_json_never_raises():
    info = probe_media("x.mp4", runner=lambda cmd: _Proc("{not json"))
    assert info["vcodec"] == ""
