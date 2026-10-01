import json

from core.manifest import SCHEMA_VERSION, DownloadResult, error_result, result_from_info


def test_success_dict_has_schema_version_and_contract_keys():
    result = DownloadResult(
        status="ok", url="https://youtu.be/x", platform="youtube",
        title="T", path="D:/a.mp4", extension="mp4", height=1080,
        bytes=100, duration_seconds=10, error_category=None, message=None,
    )
    data = result.to_dict()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["status"] == "ok"
    assert data["path"] == "D:/a.mp4"
    assert data["error_category"] is None
    json.dumps(data)


def test_result_from_info_coerces_float_duration():
    info = {"id": "x", "title": "T", "height": 720, "duration": 12.5, "ext": "mp4"}
    result = result_from_info(info, path="D:/a.mp4", url="https://youtu.be/x")
    assert result.status == "ok"
    assert result.duration_seconds == 12
    assert result.height == 720
    assert result.platform == "youtube"


def test_result_from_info_tolerates_missing_fields():
    result = result_from_info({}, path="", url="https://example.com/x")
    assert result.status == "ok"
    assert result.duration_seconds == 0
    assert result.height == 0
    assert result.platform == ""


def test_error_result_shape():
    result = error_result("blocked", "YouTube blocked the request.", "https://youtu.be/x")
    data = result.to_dict()
    assert data["status"] == "error"
    assert data["path"] is None
    assert data["error_category"] == "blocked"
