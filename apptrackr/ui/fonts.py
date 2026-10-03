"""Bundled typefaces: Instrument Sans for the interface, Martian Mono for engraved labels.

Both are SIL Open Font License fonts shipped in assets/fonts (see the OFL-*.txt files).
"""

from __future__ import annotations

import logging
from functools import lru_cache

from PySide6.QtGui import QFont, QFontDatabase

from .. import paths

log = logging.getLogger(__name__)

SANS = "Instrument Sans"
MONO = "Martian Mono"
_FALLBACK_SANS = ("Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", "Ubuntu")
_FALLBACK_MONO = ("Cascadia Mono", "Consolas", "JetBrains Mono", "DejaVu Sans Mono")


@lru_cache(maxsize=1)
def load() -> tuple[str, str]:
    """Register the bundled fonts once; returns the (sans, mono) families in use."""
    for path in sorted((paths.assets_dir() / "fonts").glob("*.ttf")):
        if QFontDatabase.addApplicationFont(str(path)) < 0:
            log.warning("Could not load font %s", path.name)
    families = set(QFontDatabase.families())
    sans = SANS if SANS in families else next((f for f in _FALLBACK_SANS if f in families), "")
    mono = MONO if MONO in families else next((f for f in _FALLBACK_MONO if f in families), "monospace")
    return sans, mono


def sans(px: int = 13, weight: int = 400, tabular: bool = False) -> QFont:
    font = QFont(load()[0])
    font.setPixelSize(px)
    font.setWeight(QFont.Weight(weight))
    if tabular:
        font.setFeature(QFont.Tag("tnum"), 1)
    return font


def mono(px: int = 10, weight: int = 500, tracking: float = 8.0) -> QFont:
    """Engraved-label face: small, tracked out by *tracking* percent."""
    font = QFont(load()[1])
    font.setPixelSize(px)
    font.setWeight(QFont.Weight(weight))
    if tracking:
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100 + tracking)
    return font
