"""Odometer-style text: characters that change roll vertically into place.

Used for readouts that tick (today's total, the session clock, levels and
credits). Unchanged leading and trailing characters stay put; changed
digits roll right to left with a slight stagger, like a mechanical counter.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import QLabel

from .. import motion

STAGGER = 0.14  # fraction of the roll between neighbouring characters
MAX_STAGGER = 0.4


def direction(old: str, new: str) -> int:
    """+1 when *new* reads as a larger number than *old* (rolls up), else -1."""

    def key(text: str) -> tuple:
        numbers = [int(n) for n in re.findall(r"\d+", text.replace(",", ""))]
        return (len(numbers), numbers)

    return 1 if key(new) >= key(old) else -1


def paint_roll(
    p: QPainter,
    rect: QRectF,
    align: Qt.AlignmentFlag,
    old: str,
    new: str,
    progress: float,
    font: QFont,
    color: QColor,
    rising: int = 1,
) -> None:
    """Draw *new* inside *rect*, rolling the characters that differ from *old*."""
    fm = QFontMetricsF(font)

    def left_edge(text: str) -> float:
        width = fm.horizontalAdvance(text)
        if align & Qt.AlignmentFlag.AlignRight:
            return rect.right() - width
        if align & Qt.AlignmentFlag.AlignHCenter:
            return rect.center().x() - width / 2
        return rect.left()

    baseline = rect.center().y() + (fm.ascent() - fm.descent()) / 2
    travel = fm.height() * 0.8
    p.save()
    p.setFont(font)
    p.setClipRect(rect.adjusted(-2, 0, 2, 0))

    def draw(text: str, x: float, dy: float, alpha: float) -> None:
        if not text or alpha <= 0.01:
            return
        c = QColor(color)
        c.setAlphaF(color.alphaF() * max(0.0, min(1.0, alpha)))
        p.setPen(c)
        p.drawText(QPointF(x, baseline + dy), text)

    def roll(o: str, xo: float, n: str, xn: float, local: float) -> None:
        eased = motion.DECELERATE.valueForProgress(max(0.0, min(1.0, local)))
        draw(o, xo, -rising * travel * eased, 1 - eased)
        draw(n, xn, rising * travel * (1 - eased), eased)

    if len(old) != len(new):
        # Different lengths ("59m" -> "1h 0m"): the whole readout turns over at once.
        roll(old, left_edge(old), new, left_edge(new), progress)
        p.restore()
        return
    # Same length: unchanged characters hold still, changed ones roll right to left.
    x0 = left_edge(new)
    changed = [i for i, (o, n) in enumerate(zip(old, new, strict=True)) if o != n]
    step = min(STAGGER, MAX_STAGGER / (len(changed) - 1)) if len(changed) > 1 else 0.0
    span = 1.0 - step * max(0, len(changed) - 1)
    x = x0
    for i, (o, n) in enumerate(zip(old, new, strict=True)):
        if o == n:
            draw(n, x, 0, 1)
        else:
            rank = len(changed) - 1 - changed.index(i)  # rightmost starts first
            roll(o, x, n, x, (progress - rank * step) / span)
        x += fm.horizontalAdvance(n)
    p.restore()


class RollingLabel(QLabel):
    """QLabel whose roll_to() rolls changed characters; setText() stays instant."""

    DURATION = motion.SLOW + 120

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._old = ""
        self._p = 1.0
        self._rising = 1

    def roll_to(self, text: str) -> None:
        old = self.text()
        if text == old:
            return
        if not motion.enabled() or not self.isVisible() or not old or old in ("–", "-"):
            motion.tween(self, 1.0, 1.0, 0, self._set_p, key="roll")  # cancels a roll in flight
            self.setText(text)
            return
        self._old, self._rising = old, direction(old, text)
        self.setText(text)
        self._p = 0.0
        motion.tween(self, 0.0, 1.0, self.DURATION, self._set_p, motion.LINEAR, key="roll")

    def _set_p(self, value: float) -> None:
        self._p = value
        self.update()

    def paintEvent(self, event):
        if self._p >= 1.0 or not self._old:
            return super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        color = self.palette().color(self.foregroundRole())
        paint_roll(
            p,
            QRectF(self.contentsRect()),
            self.alignment(),
            self._old,
            self.text(),
            self._p,
            self.font(),
            color,
            self._rising,
        )
