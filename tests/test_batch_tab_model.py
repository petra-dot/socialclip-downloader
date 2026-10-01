import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui.batch_tab import parse_url_lines  # noqa: E402


def test_parse_url_lines_trims_dedupes_and_skips_blanks():
    text = "https://a.com/1\n\n  https://b.com/2  \nhttps://a.com/1\n"
    assert parse_url_lines(text) == ["https://a.com/1", "https://b.com/2"]
