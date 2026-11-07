import json
from pathlib import Path

from core.extension import CHROMIUM_EXTENSION_ID, chrome_id_from_key, copy_tree

EXT = Path(__file__).resolve().parent.parent / "extension"

# The key the shipped manifest carries. Pinned here so a refactor cannot
# silently change the id every registered host points at.
KEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArx5Z3HNouM+Lbec9iojW/J+BIFZC"
    "ks574T2ewXiDshuesSllEEGUaMW5DCtIubtoI/fcCD1q6od+fp5tO5VT47suTKL/ReSvKifOD"
    "6pmVD6spdNEjRZv7TNFS59ErSIuSEeOPAm781HSEnU7O2E+sqvsbBR4ZQA8vbivbR334XIBm"
    "M30AV9K+TjWdPSpw81G0ga1Bi5bs/SM11CJj0D2bhLIH+3i/2wUKeVur7Xs/y3kBGK4GUNha"
    "HWQfqUk4QCa6w2m0J4GTysqNRQy8sVlJUkc7aMAKTK2ryuupJcKuctBv7qux8iGvXWYh/P4A"
    "C0txg3AXB+3VE7J3UdFYLeiwQIDAQAB"
)


def test_chrome_id_from_key_is_stable():
    assert chrome_id_from_key(KEY) == CHROMIUM_EXTENSION_ID


def test_chrome_id_uses_only_letters_a_to_p():
    ident = chrome_id_from_key(KEY)
    assert len(ident) == 32
    assert all("a" <= char <= "p" for char in ident)


def test_manifest_key_matches_the_baked_id():
    manifest = json.loads((EXT / "manifest.chromium.json").read_text(encoding="utf-8"))
    assert chrome_id_from_key(manifest["key"]) == CHROMIUM_EXTENSION_ID


def test_copy_tree_copies_then_updates_changed_files(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "a.js").write_text("one", encoding="utf-8")
    (source / "sub").mkdir()
    dest = tmp_path / "dest"

    copy_tree(str(source), str(dest))
    assert (dest / "a.js").read_text(encoding="utf-8") == "one"

    (source / "a.js").write_text("two", encoding="utf-8")
    copy_tree(str(source), str(dest))
    assert (dest / "a.js").read_text(encoding="utf-8") == "two"
