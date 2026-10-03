"""Motion system: duration and easing tokens plus small animation helpers.

Tokens follow Fluent 2 (durations in ms, cubic-bezier curves). Every helper
respects reduced motion: when animations are off the end state is applied
immediately, so callers never need a separate code path.

Usage guide:
- enter / appear      DECELERATE, FAST-NORMAL
- exit / dismiss      ACCELERATE, FASTER-FAST
- move / resize       EASY_EASE, NORMAL-GENTLE
- data change         EASY_EASE, SLOW (staggered for series)
"""

from __future__ import annotations

import sys
from typing import Callable

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QPointF,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

# Durations (ms)
ULTRA_FAST = 50
FASTER = 100
FAST = 150
NORMAL = 200
GENTLE = 250
SLOW = 300
SLOWER = 400
ULTRA_SLOW = 500


def _bezier(x1: float, y1: float, x2: float, y2: float) -> QEasingCurve:
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(QPointF(x1, y1), QPointF(x2, y2), QPointF(1, 1))
    return curve


DECELERATE = _bezier(0.1, 0.9, 0.2, 1.0)
ACCELERATE = _bezier(0.9, 0.1, 1.0, 0.2)
EASY_EASE = _bezier(0.33, 0.0, 0.67, 1.0)
LINEAR = QEasingCurve(QEasingCurve.Type.Linear)

_override: bool | None = None
_cached: bool | None = None
# Multiplies every duration and delay. Only the demo recorder changes it, to slow
# motion down so frame capture can keep up; the GIF is then played back faster.
time_scale = 1.0


# ---------------------------------------------------------------------------
# Reduced motion
# ---------------------------------------------------------------------------


def system_allows_animation() -> bool:
    """Windows 'Animation effects' (SPI_GETCLIENTAREAANIMATION); True elsewhere."""
    if not sys.platform.startswith("win"):
        return True
    try:
        import ctypes

        value = ctypes.c_int(1)
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(value), 0):
            return bool(value.value)
    except Exception:
        pass
    return True


def enabled() -> bool:
    """Whether animations should play: in-app setting, else the OS preference."""
    global _cached
    if _override is not None:
        return _override
    if _cached is None:
        from ..data import db

        stored = db.get_setting("animations", "")
        _cached = stored == "1" if stored in ("0", "1") else system_allows_animation()
    return _cached


def set_enabled(value: bool | None) -> None:
    """Persist the user's choice (None returns to following the OS)."""
    global _cached
    from ..data import db

    db.set_setting("animations", "" if value is None else value)
    _cached = None


def force(value: bool | None) -> None:
    """Override for tests and the screenshot script; None clears the override."""
    global _override
    _override = value


# ---------------------------------------------------------------------------
# Tweens
# ---------------------------------------------------------------------------


def tween(
    owner: QWidget,
    start,
    end,
    duration: int,
    on_value: Callable,
    easing: QEasingCurve = EASY_EASE,
    on_done: Callable | None = None,
    delay: int = 0,
    key: str | None = None,
) -> QVariantAnimation | None:
    """Animate a value from *start* to *end*, calling *on_value* each frame.

    With *key*, a running tween with the same key on *owner* is stopped first,
    so repeated calls retarget instead of stacking.
    """
    if key:
        current = running(owner, key)
        if current is not None:
            current.stop()
    if not enabled() or duration <= 0 or start == end:
        on_value(end)
        if on_done:
            on_done()
        return None

    duration = int(duration * time_scale)
    delay = int(delay * time_scale)
    anim = QVariantAnimation(owner)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setDuration(duration)
    anim.setEasingCurve(easing)
    anim.valueChanged.connect(on_value)
    if on_done:
        anim.finished.connect(on_done)
    if key:
        setattr(owner, f"_tween_{key}", anim)
    on_value(start)  # apply the first frame now; QVariantAnimation emits on the next tick
    if delay > 0:
        QTimer.singleShot(delay, owner, lambda: anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped))
    else:
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def running(owner: QWidget, key: str) -> QVariantAnimation | None:
    """The keyed tween on *owner* if it is still running, else None."""
    anim = getattr(owner, f"_tween_{key}", None)
    if anim is None:
        return None
    try:
        return anim if anim.state() == QAbstractAnimation.State.Running else None
    except RuntimeError:  # already deleted after finishing
        setattr(owner, f"_tween_{key}", None)
        return None


def fade(
    widget: QWidget,
    start: float,
    end: float,
    duration: int = FAST,
    easing: QEasingCurve = DECELERATE,
    on_done: Callable | None = None,
    delay: int = 0,
) -> None:
    """Fade a widget's opacity. The effect is removed when it ends fully opaque."""
    if not enabled():
        if on_done:
            on_done()
        return
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOpacity(start)

    def finish():
        try:
            if end >= 1.0 and widget.graphicsEffect() is effect:
                widget.setGraphicsEffect(None)
        except RuntimeError:
            return
        if on_done:
            on_done()

    tween(widget, start, end, duration, lambda v: _set_opacity(effect, v), easing, finish, delay, key="fade")


def _set_opacity(effect: QGraphicsOpacityEffect, value: float) -> None:
    try:
        effect.setOpacity(value)
    except RuntimeError:
        pass


def stagger_in(widgets: list[QWidget], step: int = 22, duration: int = FAST, limit: int = 12) -> None:
    """Fade a list of freshly added widgets in one after another."""
    if not enabled():
        return
    for i, widget in enumerate(widgets[:limit]):
        fade(widget, 0.0, 1.0, duration, DECELERATE, delay=i * step)


def collapse(widget: QWidget, on_done: Callable, duration: int = NORMAL) -> None:
    """Fade a widget out while shrinking its height to zero, then call *on_done*."""
    if not enabled():
        on_done()
        return
    widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    height = widget.height()
    fade(widget, 1.0, 0.0, FAST, ACCELERATE)
    tween(widget, height, 0, duration, lambda v: _set_max_height(widget, v), EASY_EASE, on_done, key="collapse")


def _set_max_height(widget: QWidget, value: float) -> None:
    try:
        widget.setMaximumHeight(int(value))
    except RuntimeError:
        pass


class _Flash(QWidget):
    """Transparent overlay that glows the parent's outline and fades away."""

    def __init__(self, parent: QWidget, color: QColor, radius: float):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._color = color
        self._radius = radius
        self._strength = 1.0
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()

    def set_strength(self, value: float) -> None:
        self._strength = value
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill = QColor(self._color)
        fill.setAlphaF(0.14 * self._strength)
        edge = QColor(self._color)
        edge.setAlphaF(0.9 * self._strength)
        p.setPen(QPen(edge, 2))
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), self._radius, self._radius)


def flash(widget: QWidget, color: str | None = None, radius: float = 12, duration: int = ULTRA_SLOW * 2) -> None:
    """Briefly highlight a widget to confirm an action (a build, a claim)."""
    if not enabled():
        return
    from . import theme

    overlay = _Flash(widget, QColor(color or theme.current().accent), radius)
    tween(overlay, 1.0, 0.0, duration, overlay.set_strength, DECELERATE, overlay.deleteLater)


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


class PulseDot(QWidget):
    """Small dot with a breathing halo, used to signal live tracking."""

    def __init__(self, size: int = 10, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self._active = False
        self._color = QColor("#10d9a3")
        self.setFixedSize(size * 2, size * 2)
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(int(1600 * time_scale))
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._set_phase)

    def set_state(self, active: bool, color: str) -> None:
        """Called on every UI tick; also picks up changes to the animation setting."""
        self._color = QColor(color)
        self._active = active
        should_run = active and enabled()
        is_running = self._anim.state() == QAbstractAnimation.State.Running
        if should_run and not is_running:
            self._anim.start()
        elif not should_run and is_running:
            self._anim.stop()
            self._phase = 0.0
        self.update()

    def _set_phase(self, value: float) -> None:
        self._phase = value
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = self.rect().center()
        r = self.width() / 4
        if self._active and self._anim.state() == QAbstractAnimation.State.Running:
            halo = QColor(self._color)
            halo.setAlphaF(0.45 * (1 - self._phase))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            hr = r * (1 + self._phase)
            p.drawEllipse(QPointF(c), hr, hr)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(QPointF(c), r, r)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t
