import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui.batch_tab import parse_url_lines  # noqa: E402


def test_parse_url_lines_trims_dedupes_and_skips_blanks():
    text = "https://a.com/1\n\n  https://b.com/2  \nhttps://a.com/1\n"
    assert parse_url_lines(text) == ["https://a.com/1", "https://b.com/2"]


def test_add_jobs_reflects_last_accepted_url_not_the_last_raw_line(monkeypatch):
    from ui import batch_tab
    from ui.batch_tab import QueueTab

    monkeypatch.setattr(batch_tab, "is_supported_url", lambda url: True)
    monkeypatch.setattr(batch_tab, "classify_url", lambda url: "single")

    added = []

    class _Store:
        def save(self):
            pass

    class _Queue:
        store = _Store()

        def add_many(self, urls, options=None):
            added.extend(urls)

    class _Box:
        def __init__(self, value=""):
            self._value = value

        def text(self):
            return self._value

        def setText(self, value):
            self._value = value

    tab = QueueTab.__new__(QueueTab)
    tab.queue = _Queue()
    tab.batch_cookies_input = _Box("youtube_cookies.txt")
    tab._job_options = lambda: {}
    tab.refresh_table = lambda: None
    tab.batch_log = lambda msg: None
    tab.show_hint = lambda msg: None
    # Real method persists to QSettings; stub it so the test never writes there.
    tab._on_batch_cookies_changed = lambda: None
    tab._expand_queue = []
    tab._expand_next = lambda: None

    # A trailing junk line must not clear the box: the accepted URL decides it.
    tab._add_jobs(["https://youtu.be/x", "not a url"])

    assert added == ["https://youtu.be/x"]
    assert tab.batch_cookies_input.text() == "youtube_cookies.txt"
