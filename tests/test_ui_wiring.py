"""Guards against a recurring bug class: Qt classes imported from the wrong
module. QPixmap, QIcon, and QKeySequence all live in QtGui, not QtWidgets or
QtCore, and the mistake only surfaces at construction time.
"""

import pathlib

from PyQt5 import QtCore, QtGui, QtWidgets

from ui.style import THEMES, THEME_LABELS

UI_DIR = pathlib.Path(__file__).resolve().parent.parent / "ui"

# (wrong reference, the module that actually owns it)
WRONG_REFS = (
    "QtWidgets.QPixmap",
    "QtWidgets.QIcon",
    "QtWidgets.QKeySequence",
    "QtCore.QPixmap",
    "QtCore.QIcon",
    "QtCore.QKeySequence",
)


def test_wrong_module_references_absent_from_ui():
    offenders = []
    for path in UI_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for ref in WRONG_REFS:
            if ref in text:
                offenders.append("%s: %s" % (path.name, ref))
    assert not offenders, offenders


def test_the_qt_classes_are_where_we_claim():
    assert hasattr(QtGui, "QPixmap")
    assert hasattr(QtGui, "QIcon")
    assert hasattr(QtGui, "QKeySequence")
    assert not hasattr(QtWidgets, "QPixmap")
    assert not hasattr(QtWidgets, "QKeySequence")
    assert not hasattr(QtCore, "QKeySequence")


def test_theme_modes_are_the_three_expected():
    assert THEMES == ("system", "light", "dark")


def test_every_theme_mode_has_a_label():
    assert set(THEME_LABELS) == set(THEMES)
    assert THEME_LABELS["system"] == "Default"


def test_dark_theme_applies_the_palette_under_fusion():
    # Windows' native style ignores most of a custom QPalette, which made the
    # dark theme light-on-light. The dark branch must switch to Fusion first.
    src = (UI_DIR / "style.py").read_text(encoding="utf-8")
    assert 'setStyle("Fusion")' in src


def test_all_themes_use_fusion():
    from ui import style
    src = (UI_DIR / "style.py").read_text(encoding="utf-8")
    assert 'setStyle("Fusion")' in src
    # The native-style restore must be gone, or shapes change between themes.
    assert "setStyle(_native_style)" not in src


def test_tab_bar_style_uses_the_accent():
    from ui import style
    style._current_mode = style.THEME_LIGHT
    assert style.token("accent") in style.tab_bar_style()
    style._current_mode = style.THEME_SYSTEM


def test_convert_worker_announces_output_path():
    from workers.convert_worker import ConvertFileWorker

    assert hasattr(ConvertFileWorker, "output_signal")
    assert hasattr(ConvertFileWorker, "finished_signal")


def test_update_workers_expose_their_signals():
    from workers.update_worker import UpdateCheckWorker, UpdateDownloadWorker

    assert hasattr(UpdateCheckWorker, "done_signal")
    assert hasattr(UpdateCheckWorker, "error_signal")
    assert hasattr(UpdateDownloadWorker, "progress_signal")
    assert hasattr(UpdateDownloadWorker, "done_signal")
    assert hasattr(UpdateDownloadWorker, "error_signal")


def test_expand_worker_exposes_its_signals():
    from workers.expand_worker import ExpandWorker

    assert hasattr(ExpandWorker, "done_signal")
    assert hasattr(ExpandWorker, "error_signal")


def test_doctor_lines_include_every_component():
    from core.maintenance import Component
    from ui.dialogs import doctor_lines

    components = [
        Component("yt-dlp", "yt-dlp", "stale", version="2020.01.01",
                  detail="2000 days old", action="update"),
        Component("ffmpeg", "ffmpeg", "ok", version="ffmpeg version 6.1"),
        Component("js-runtime", "JavaScript runtime", "missing",
                  detail="YouTube needs deno or node", action="install"),
    ]
    text = "\n".join(doctor_lines({"schema_version": "1.2"}, components))
    assert "yt-dlp" in text
    assert "stale" in text
    assert "JavaScript runtime" in text
    assert "missing" in text
    assert "ffmpeg version 6.1" in text


class _RunningWorker:
    """Stand-in for a QThread that is still running."""

    def __init__(self):
        self.started = False

    def isRunning(self):
        return True

    def start(self):
        self.started = True


class _Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)


class _CapturingWorker:
    def __init__(self, *_args):
        self.done_signal = _Signal()
        self.error_signal = _Signal()
        self.progress_signal = _Signal()
        self.started = False

    def isRunning(self):
        return False

    def start(self):
        self.started = True


class _RecordingSettings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


def _bare_window():
    # Bypass __init__ so no widget, dialog, or worker is created.
    from ui.main_window import MainWindow

    window = MainWindow.__new__(MainWindow)
    window.settings = _RecordingSettings()
    window._maintenance_worker = None
    window._repair_worker = None
    logs = []
    window.log = logs.append
    return window, logs


def test_check_components_leaves_a_running_worker_alone():
    window, logs = _bare_window()
    existing = _RunningWorker()
    window._maintenance_worker = existing
    window._check_components(force=True)
    assert window._maintenance_worker is existing
    assert existing.started is False
    assert logs


def test_repair_components_leaves_a_running_worker_alone():
    window, logs = _bare_window()
    existing = _RunningWorker()
    window._repair_worker = existing
    window._repair_components(["yt-dlp"])
    assert window._repair_worker is existing
    assert existing.started is False
    assert logs


def test_on_components_checked_leaves_a_running_repair_alone():
    from core.maintenance import Component

    window, logs = _bare_window()
    existing = _RunningWorker()
    window._repair_worker = existing
    window._on_components_checked(
        [Component("yt-dlp", "yt-dlp", "missing", action="install")]
    )
    assert window._repair_worker is existing
    assert existing.started is False
    assert logs


def test_check_components_wires_the_error_signal(monkeypatch):
    from ui import main_window

    worker = _CapturingWorker()
    monkeypatch.setattr(main_window, "MaintenanceCheckWorker", lambda: worker)
    window, _logs = _bare_window()
    window._check_components(force=True)
    assert window._maintenance_worker is worker
    assert worker.error_signal.slots == [window._on_check_error]


def test_check_error_logs_without_stamping_the_cache():
    window, logs = _bare_window()
    window._on_check_error("boom")
    assert any("boom" in line for line in logs)
    assert "maintenance/last_check" not in window.settings.values


def test_within_a_day_treats_bad_stamps_as_stale():
    import datetime

    from ui.main_window import _within_a_day

    assert _within_a_day("") is False
    assert _within_a_day("not a date") is False
    # A tz-aware stamp makes `now() - when` raise TypeError; treat it as stale
    # so a fresh check runs instead of raising out of the daily-cache guard.
    aware = datetime.datetime.now(datetime.timezone.utc).isoformat()
    assert _within_a_day(aware) is False


def _component(key, state, action="none", label=None, version="", detail=""):
    from core.maintenance import Component

    return Component(
        key, label or key, state,
        version=version, detail=detail, action=action,
    )


def test_health_summary_all_ok_is_working():
    from ui.dialogs import health_summary

    comps = [_component("yt-dlp", "ok"), _component("ffmpeg", "ok")]
    assert health_summary(comps) == ("Everything is working", "ok")


def test_health_summary_empty_is_working():
    from ui.dialogs import health_summary

    assert health_summary([]) == ("Everything is working", "ok")
    assert health_summary(None) == ("Everything is working", "ok")


def test_health_summary_one_stale_is_warn():
    from ui.dialogs import health_summary

    headline, tone = health_summary([_component("yt-dlp", "stale")])
    assert "1 thing" in headline
    assert "things" not in headline
    assert tone == "warn"


def test_health_summary_two_needing_is_plural_warn():
    from ui.dialogs import health_summary

    comps = [_component("yt-dlp", "stale"), _component("deno", "missing")]
    headline, tone = health_summary(comps)
    assert "2 things" in headline
    assert tone == "warn"


def test_health_summary_broken_is_bad():
    from ui.dialogs import health_summary

    comps = [_component("yt-dlp", "missing"), _component("data-dir", "broken")]
    _headline, tone = health_summary(comps)
    assert tone == "bad"
    assert health_summary([_component("data-dir", "broken")])[1] == "bad"


def test_state_chip_known_states():
    from ui.dialogs import state_chip

    assert state_chip("ok") == ("OK", "ok")
    assert state_chip("missing") == ("MISSING", "bad")
    assert state_chip("stale") == ("STALE", "warn")
    assert state_chip("broken") == ("BROKEN", "bad")
    assert state_chip("unknown") == ("UNKNOWN", "unknown")


def test_state_chip_is_case_insensitive_for_known_states():
    from ui.dialogs import state_chip

    assert state_chip("OK") == ("OK", "ok")


def test_state_chip_shows_an_unexpected_state():
    from ui.dialogs import state_chip

    assert state_chip("weird") == ("WEIRD", "unknown")


def test_state_chip_shows_none():
    from ui.dialogs import state_chip

    assert state_chip(None) == ("?", "unknown")
