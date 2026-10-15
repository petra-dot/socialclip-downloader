import datetime

from utils.ytdlp import (
    RUNTIMES, find_js_runtime, is_stale, js_runtimes, version_age_days,
)


def test_find_js_runtime_prefers_deno_then_node():
    node_only = {"node": r"C:\nodejs\node.exe"}
    assert find_js_runtime(which=node_only.get) == ("node", r"C:\nodejs\node.exe")

    both = {"deno": r"C:\deno\deno.exe", "node": r"C:\nodejs\node.exe"}
    assert find_js_runtime(which=both.get)[0] == "deno"


def test_find_js_runtime_when_none_installed():
    assert find_js_runtime(which=lambda name: None) == ("", "")


def test_find_js_runtime_survives_a_failing_lookup():
    def boom(name):
        raise OSError("path is broken")

    assert find_js_runtime(which=boom) == ("", "")


def test_js_runtimes_option_shape():
    assert js_runtimes(which=lambda name: None) == {}
    got = js_runtimes(
        which=lambda name: "C:/x/node.exe" if name == "node" else None
    )
    assert got == {"node": {"path": "C:/x/node.exe"}}


def test_version_age_days_parses_a_date_stamp():
    today = datetime.date(2026, 10, 16)
    assert version_age_days("2026.07.04", today=today) == 104
    assert version_age_days("2026.10.16", today=today) == 0


def test_version_age_days_rejects_non_dates():
    today = datetime.date(2026, 10, 16)
    assert version_age_days("", today=today) is None
    assert version_age_days("2026.07", today=today) is None
    assert version_age_days("nightly", today=today) is None
    assert version_age_days("2026.13.40", today=today) is None


def test_is_stale_threshold():
    today = datetime.date(2026, 10, 16)
    assert is_stale("2026.07.04", today=today) is True
    assert is_stale("2026.10.01", today=today) is False
    assert is_stale("not-a-date", today=today) is False


def test_runtimes_order_and_membership():
    assert RUNTIMES[0] == "deno"
    assert "node" in RUNTIMES
