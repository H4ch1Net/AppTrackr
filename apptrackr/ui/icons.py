"""Tinted SVG icons. Icon artwork from Lucide (ISC license, see assets/icons/LICENSE)."""

from __future__ import annotations

from functools import cache, lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .. import paths


@cache
def _source(name: str) -> str:
    return (paths.assets_dir() / "icons" / f"{name}.svg").read_text(encoding="utf-8")


def _dpr() -> float:
    app = QGuiApplication.instance()
    screen = app.primaryScreen() if app else None
    return screen.devicePixelRatio() if screen else 1.0


def _render(svg: str, size: int, height: int | None = None) -> QPixmap:
    dpr = _dpr()
    pm = QPixmap(int(size * dpr), int((height or size) * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, pm.width(), pm.height()))
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def stroke_for(size: int) -> float:
    """Hairline strokes: thinner relative to the 24-unit grid as icons get larger."""
    return 1.75 if size <= 16 else (1.6 if size <= 22 else 1.4)


@lru_cache(maxsize=512)
def pixmap(name: str, color: str, size: int = 16, filled: bool = False) -> QPixmap:
    svg = _source(name).replace("currentColor", color).replace('stroke-width="2"', f'stroke-width="{stroke_for(size)}"')
    if filled:
        svg = svg.replace('fill="none"', f'fill="{color}"', 1)
    return _render(svg, size)


@lru_cache(maxsize=64)
def illustration(name: str, ink: str, accent: str, faint: str, size: int = 120) -> QPixmap:
    """Hairline line-art from assets/illustrations, tinted with ink, accent and faint colours."""
    svg = (paths.assets_dir() / "illustrations" / f"{name}.svg").read_text(encoding="utf-8")
    svg = svg.replace("INK", ink).replace("ACCENT", accent).replace("FAINT", faint)
    return _render(svg, size, height=int(size * 0.8))


def icon(name: str, color: str, size: int = 16, checked_color: str | None = None) -> QIcon:
    """QIcon with an optional different tint for the checked state."""
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(pixmap(name, checked_color or color, size), QIcon.Mode.Normal, QIcon.State.On)
    return ic


@lru_cache(maxsize=16)
def logo_pixmap(size: int = 32) -> QPixmap:
    name = "logo-small.svg" if size <= 32 else "logo.svg"  # the small mark drops minor ticks
    return _render((paths.assets_dir() / name).read_text(encoding="utf-8"), size)


def logo_icon() -> QIcon:
    ic = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(logo_pixmap(size))
    return ic
