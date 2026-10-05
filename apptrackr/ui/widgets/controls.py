"""Painted form controls: check box and a ruler-style slider with fixed stops.

Both follow the instrument panel rules: monochrome ink when on, accent only
for keyboard focus, and short eased motion that confirms each change.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QAbstractSlider, QSizePolicy

from .. import fonts, motion, theme


def _blend(a: str, b: str, t: float) -> QColor:
    return QColor(theme._mix(a, b, max(0.0, min(1.0, t))))


def _partial(points: list[QPointF], amount: float) -> QPainterPath:
    """Polyline through *points*, trimmed to *amount* (0..1) of its length."""
    lengths = [math.hypot(b.x() - a.x(), b.y() - a.y()) for a, b in zip(points, points[1:], strict=False)]
    remaining = sum(lengths) * max(0.0, min(1.0, amount))
    path = QPainterPath(points[0])
    for i, seg in enumerate(lengths):
        if remaining <= 0:
            break
        a, b = points[i], points[i + 1]
        f = min(1.0, remaining / seg) if seg else 1.0
        path.lineTo(a + (b - a) * f)
        remaining -= seg
    return path


class CheckBox(QAbstractButton):
    """Check box whose box fills and then draws its check mark."""

    BOX = 16

    def __init__(self, text: str = "", checked: bool = False, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFont(fonts.sans(13))
        super().setChecked(checked)
        self._p = 1.0 if checked else 0.0
        self._hover = 0.0
        self._press = 0.0
        self.toggled.connect(self._animate)
        self.pressed.connect(lambda: self._tween_press(1.0))
        self.released.connect(lambda: self._tween_press(0.0))

    def sizeHint(self) -> QSize:
        width = self.BOX + (8 + self.fontMetrics().horizontalAdvance(self.text()) if self.text() else 0)
        return QSize(width + 2, max(self.BOX, self.fontMetrics().height()) + 4)

    def set_silently(self, checked: bool) -> None:
        self.blockSignals(True)
        self.setChecked(checked)
        self.blockSignals(False)
        self._p = 1.0 if checked else 0.0
        self.update()

    def _animate(self, checked: bool) -> None:
        # Checking draws in (slower, decelerating); unchecking clears quickly.
        if checked:
            motion.tween(self, self._p, 1.0, motion.SLOW, self._set_p, motion.DECELERATE, key="check")
        else:
            motion.tween(self, self._p, 0.0, motion.FAST, self._set_p, motion.ACCELERATE, key="check")

    def _set_p(self, v: float) -> None:
        self._p = v
        self.update()

    def _tween_press(self, target: float) -> None:
        motion.tween(self, self._press, target, motion.FASTER, self._set_press, motion.EASY_EASE, key="press")

    def _set_press(self, v: float) -> None:
        self._press = v
        self.update()

    def _set_hover(self, v: float) -> None:
        self._hover = v
        self.update()

    def enterEvent(self, event):
        motion.tween(self, self._hover, 1.0, motion.FAST, self._set_hover, motion.DECELERATE, key="hover")
        super().enterEvent(event)

    def leaveEvent(self, event):
        motion.tween(self, self._hover, 0.0, motion.NORMAL, self._set_hover, motion.EASY_EASE, key="hover")
        super().leaveEvent(event)

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        enabled = self.isEnabled()
        cy = self.height() / 2
        scale = 1 - 0.1 * self._press
        size = self.BOX * scale
        box = QRectF(1 + (self.BOX - size) / 2, cy - size / 2, size, size)
        fill = min(1.0, self._p / 0.55)  # box fills over the first half, the check draws after
        draw = max(0.0, (self._p - 0.35) / 0.65)
        edge = _blend(t.border_strong, t.text_muted, self._hover)
        edge = _blend(edge.name(), t.text, fill)
        if not enabled:
            edge.setAlphaF(0.45)
        p.setPen(QPen(edge, 1.25))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(box.adjusted(0.6, 0.6, -0.6, -0.6), 3, 3)
        if fill > 0:
            ink = QColor(t.text if enabled else t.text_muted)
            ink.setAlphaF(fill)
            inset = (1 - fill) * size * 0.3
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ink)
            p.drawRoundedRect(box.adjusted(inset, inset, -inset, -inset), 3, 3)
        if draw > 0:
            x, y, s = box.left(), box.top(), size
            pts = [
                QPointF(x + s * 0.24, y + s * 0.52),
                QPointF(x + s * 0.43, y + s * 0.70),
                QPointF(x + s * 0.77, y + s * 0.32),
            ]
            pen = QPen(QColor(t.window), 1.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPath(_partial(pts, draw))
        if self.hasFocus():
            p.setPen(QPen(QColor(t.accent), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(box.adjusted(-2.5, -2.5, 2.5, 2.5), 4.5, 4.5)
        if self.text():
            p.setPen(QColor(t.text if enabled else t.text_muted))
            p.setFont(self.font())
            rect = QRectF(self.BOX + 9, 0, self.width() - self.BOX - 9, self.height())
            p.drawText(rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), self.text())


class TickSlider(QAbstractSlider):
    """A ruler with fixed stops and a fader cap that glides between them.

    Stops are (label, value) pairs. ``committed`` fires with the stop's value once
    a change is final: on release after dragging, or immediately for keys and clicks.
    """

    committed = Signal(object)

    TRACK_Y = 12
    KNOB_W, KNOB_H = 12, 20
    PAD = 14

    def __init__(self, stops: list[tuple[str, object]], parent=None):
        super().__init__(parent)
        self.setOrientation(Qt.Orientation.Horizontal)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setPageStep(1)
        self._stops: list[tuple[str, object]] = []
        self._pos = 0.0  # knob position in stop units, eased
        self._hover = 0.0
        self._grab = 0.0
        self._lit: list[float] = []  # per-stop highlight of the label under the knob
        self._drag_x: float | None = None
        self._committed = None
        self.set_stops(stops)
        self.valueChanged.connect(self._on_value)
        self.sliderReleased.connect(self._on_release)

    # -- data ---------------------------------------------------------------

    def set_stops(self, stops: list[tuple[str, object]]) -> None:
        self._stops = list(stops)
        self.blockSignals(True)
        self.setRange(0, max(0, len(self._stops) - 1))
        self.blockSignals(False)
        self._lit = [1.0 if i == self.value() else 0.0 for i in range(len(self._stops))]
        self._pos = float(self.value())
        self.setAccessibleDescription(", ".join(label for label, _ in self._stops))
        self.updateGeometry()
        self.update()

    def stops(self) -> list[tuple[str, object]]:
        return list(self._stops)

    def stop_value(self):
        return self._stops[self.value()][1] if self._stops else None

    def index_of(self, value) -> int:
        return next((i for i, (_, v) in enumerate(self._stops) if v == value), -1)

    def set_stop_value(self, value) -> None:
        """Select the stop holding *value* without emitting or animating."""
        i = self.index_of(value)
        if i < 0:
            return
        self.blockSignals(True)
        self.setValue(i)
        self.blockSignals(False)
        self._committed = value
        self._pos = float(i)
        self._lit = [1.0 if j == i else 0.0 for j in range(len(self._stops))]
        self.update()

    # -- geometry -----------------------------------------------------------

    def sizeHint(self) -> QSize:
        f = fonts.mono(9, 500, 4)
        widest = max((QFontMetrics(f).horizontalAdvance(label.upper()) for label, _ in self._stops), default=20)
        return QSize(max(240, (widest + 12) * len(self._stops)), 44)

    def minimumSizeHint(self) -> QSize:
        return QSize(200, 44)

    def _x(self, pos: float) -> float:
        span = max(1, len(self._stops) - 1)
        return self.PAD + (self.width() - 2 * self.PAD) * pos / span

    def _pos_at(self, x: float) -> float:
        span = max(1, len(self._stops) - 1)
        width = max(1.0, self.width() - 2 * self.PAD)
        return max(0.0, min(float(span), (x - self.PAD) / width * span))

    # -- motion -------------------------------------------------------------

    def _on_value(self, index: int) -> None:
        if self._drag_x is None:
            motion.tween(self, self._pos, float(index), motion.GENTLE, self._set_pos, motion.DECELERATE, key="pos")
        for i in range(len(self._stops)):
            target = 1.0 if i == index else 0.0
            if self._lit[i] != target:
                motion.tween(
                    self,
                    self._lit[i],
                    target,
                    motion.FAST,
                    lambda v, i=i: self._set_lit(i, v),
                    motion.EASY_EASE,
                    key=f"lit{i}",
                )
        if not self.isSliderDown():
            self._commit()

    def _on_release(self) -> None:
        self._drag_x = None
        motion.tween(self, self._pos, float(self.value()), motion.NORMAL, self._set_pos, motion.DECELERATE, key="pos")
        self._commit()

    def _commit(self) -> None:
        value = self.stop_value()
        if value != self._committed:
            self._committed = value
            self.committed.emit(value)

    def _set_pos(self, v: float) -> None:
        self._pos = v
        self.update()

    def _set_lit(self, i: int, v: float) -> None:
        if i < len(self._lit):
            self._lit[i] = v
            self.update()

    def _set_hover(self, v: float) -> None:
        self._hover = v
        self.update()

    def _set_grab(self, v: float) -> None:
        self._grab = v
        self.update()

    # -- input --------------------------------------------------------------

    def enterEvent(self, event):
        motion.tween(self, self._hover, 1.0, motion.FAST, self._set_hover, motion.DECELERATE, key="hover")
        super().enterEvent(event)

    def leaveEvent(self, event):
        motion.tween(self, self._hover, 0.0, motion.NORMAL, self._set_hover, motion.EASY_EASE, key="hover")
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._stops:
            return super().mousePressEvent(event)
        x = event.position().x()
        on_knob = abs(x - self._x(self._pos)) <= self.KNOB_W
        if on_knob:
            self._drag_x = x
            self.setSliderDown(True)
            motion.tween(self, self._grab, 1.0, motion.FASTER, self._set_grab, motion.DECELERATE, key="grab")
        else:
            self.setValue(round(self._pos_at(x)))  # click jumps: the knob glides there
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_x is None:
            return super().mouseMoveEvent(event)
        self._drag_x = event.position().x()
        self._pos = self._pos_at(self._drag_x)
        self.setValue(round(self._pos))
        self.update()

    def mouseReleaseEvent(self, event):
        if self._drag_x is not None:
            motion.tween(self, self._grab, 0.0, motion.FAST, self._set_grab, motion.EASY_EASE, key="grab")
            self.setSliderDown(False)
        event.accept()

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()  # let the page scroll instead of changing the value

    # -- paint --------------------------------------------------------------

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        enabled = self.isEnabled()
        ink = t.text if enabled else t.text_muted
        y = self.TRACK_Y
        left, right = self._x(0), self._x(max(0, len(self._stops) - 1))
        knob_x = self._x(self._pos)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.border_strong))
        p.drawRoundedRect(QRectF(left - 3, y - 2, right - left + 6, 4), 2, 2)
        p.setBrush(QColor(ink))
        p.drawRoundedRect(QRectF(left - 3, y - 2, knob_x - left + 3, 4), 2, 2)
        label_font = fonts.mono(9, 500, 4)
        p.setFont(label_font)
        metrics = p.fontMetrics()
        for i, (label, _value) in enumerate(self._stops):
            x = self._x(i)
            passed = i <= self._pos + 0.001
            tick = QColor(ink if passed else t.border_strong)
            p.setPen(QPen(tick, 1))
            p.drawLine(QPointF(x, y + 5), QPointF(x, y + 9 + 2 * self._lit[i]))
            text = label.upper()
            color = _blend(t.text_muted, ink, self._lit[i])
            p.setPen(color)
            w = metrics.horizontalAdvance(text)
            tx = min(max(x - w / 2, 0), self.width() - w)
            p.drawText(QPointF(tx, y + 24), text)
        # Fader cap: grows a little on hover and when grabbed.
        grow = 1.0 * self._hover + 1.5 * self._grab
        kw, kh = self.KNOB_W + grow, self.KNOB_H + grow
        knob = QRectF(knob_x - kw / 2, y - kh / 2, kw, kh)
        p.setPen(QPen(QColor(t.border_strong if enabled else t.border), 1))
        p.setBrush(QColor(t.surface_alt))
        p.drawRoundedRect(knob, 3, 3)
        p.setPen(QPen(QColor(ink), 1.5))
        p.drawLine(QPointF(knob_x, knob.top() + 5), QPointF(knob_x, knob.bottom() - 5))
        if self.hasFocus():
            p.setPen(QPen(QColor(t.accent), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(knob.adjusted(-2.5, -2.5, 2.5, 2.5), 4.5, 4.5)
