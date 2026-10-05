"""Every palette and accent combination keeps its contrast promises."""

import pytest

pytest.importorskip("PySide6.QtGui")

from apptrackr.ui import theme  # noqa: E402

COMBOS = [(p, a) for p in theme.PALETTES for a in theme.ACCENTS]


@pytest.mark.parametrize("palette,accent", COMBOS)
def test_contrast(palette, accent):
    t = theme.build(palette, accent)
    c = theme.contrast
    for bg in (t.window, t.surface, t.sidebar, t.surface_alt):
        assert c(t.text_muted, bg) >= 4.5, ("muted", bg)
        assert c(t.text_dim, bg) >= 4.5, ("dim", bg)
    assert c(t.accent, t.surface) >= 3.0  # bars, indicators and rings
    assert c(t.accent, t.window) >= 3.0
    assert c(t.accent_text, t.window) >= 4.5
    assert c(t.accent_text, t.surface) >= 4.5
    assert c(t.on_accent, t.accent) >= 4.5  # primary button labels
    assert c(t.ink, t.surface) >= 3.0  # history bars


def test_palettes_split_by_mode():
    assert all(t.dark for t in theme.DARK_PALETTES.values())
    assert not any(t.dark for t in theme.LIGHT_PALETTES.values())
    assert theme.DEFAULT_DARK in theme.DARK_PALETTES and theme.DEFAULT_LIGHT in theme.LIGHT_PALETTES


def test_configure_picks_palette_per_mode():
    try:
        assert theme.configure("dark", "Blue", dark_palette="Midnight", light_palette="Sage").name == "Midnight"
        assert theme.configure("light").name == "Sage"
        assert theme.configure("system", system_dark=True).name == "Midnight"
        assert theme.configure("system", system_dark=False).name == "Sage"
        # A palette of the wrong kind is ignored rather than shown in the wrong mode.
        assert theme.configure("dark", dark_palette="Paper").name == "Midnight"
    finally:
        theme.configure(
            "dark", theme.DEFAULT_ACCENT, dark_palette=theme.DEFAULT_DARK, light_palette=theme.DEFAULT_LIGHT
        )
