import pytest

from ui import style


def _in(mode):
    style._current_mode = mode


def test_every_token_exists_in_both_themes():
    _in(style.THEME_LIGHT)
    light = set(style._LIGHT)
    _in(style.THEME_DARK)
    dark = set(style._DARK)
    assert light == dark
    for key in light:
        _in(style.THEME_LIGHT)
        assert style.token(key)
        _in(style.THEME_DARK)
        assert style.token(key)
    _in(style.THEME_SYSTEM)


def test_state_color_aliases_token():
    _in(style.THEME_LIGHT)
    assert style.state_color("ok") == style.token("ok")
    _in(style.THEME_SYSTEM)


@pytest.mark.parametrize("mode", [style.THEME_LIGHT, style.THEME_DARK])
def test_readable_text_meets_contrast(mode):
    _in(mode)
    assert style.contrast_ratio(style.token("text"), style.token("window")) >= 4.5
    assert style.contrast_ratio(style.token("text_secondary"),
                                style.token("base")) >= 4.5
    # Disabled/placeholder text: the pair the dark theme used to fail.
    assert style.contrast_ratio(style.token("text_muted"),
                                style.token("window")) >= 4.5
    for kind in ("ok", "error", "busy", "warn", "muted"):
        assert style.contrast_ratio(style.token(kind), style.token("base")) >= 4.5
    assert style.contrast_ratio(style.token("on_accent"),
                                style.token("accent")) >= 4.5
    _in(style.THEME_SYSTEM)


def test_scales_are_complete():
    assert set(style.SPACING) == {"xs", "sm", "md", "lg", "xl", "xxl"}
    assert set(style.RADIUS) == {"control", "panel", "chip"}
    assert style.space("md") == style.SPACING["md"]
