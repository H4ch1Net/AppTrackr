"""Floating timer: a small always-on-top clock for the app in front.

It never takes focus, so the app being timed stays the foreground app. Drag it
anywhere (the spot is remembered), double-click it to open AppTrackr, or
right-click to hide it.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QMenu, QWidget

from .. import APP_NAME
from ..data import db
from ..game import economy
from . import fmt, fonts, motion, theme

OPACITY = 0.94
MARGIN = 24


class FloatingTimer(QWidget):
    open_requested = Signal()
    hide_requested = Signal()

    W, H = 224, 52

    def __init__(self, parent=None):
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        super().__init__(parent, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setWindowTitle(f"{APP_NAME} timer")
        self.setToolTip("Drag to move. Double-click to open AppTrackr.")
        self._name = ""
        self._session_ms = 0
        self._detail = ""
        self._progress: float | None = None  # toward the next flow tier, focus apps only
        self._focus = False
        self._drag: QPoint | None = None
        self._leaving = False
        self._placed = False
        self._multiplier: float | None = None
        self._glow = 0.0  # accent ring after reaching a new flow tier

    # -- state ---------------------------------------------------------------

    def set_state(self, name: str, session_ms: int, today_ms: int, flow=None) -> None:
        """Show *name* and how long it has been in front. *flow* is a game.focus.Flow for focus apps."""
        self._name = name
        self._session_ms = session_ms
        self._focus = flow is not None and flow.active
        if self._focus:
            if self._multiplier is not None and flow.multiplier > self._multiplier:
                motion.tween(self, 1.0, 0.0, 1600, self._set_glow, motion.DECELERATE, key="glow")
            self._multiplier = flow.multiplier
            self._detail = f"×{flow.multiplier:g}  {flow.tier.upper()}"
            self._progress = _tier_progress(flow.run_ms) if flow.next_tier else 1.0
        else:
            self._multiplier = None
            self._detail = f"TODAY {fmt.duration(today_ms, short=True).upper()}"
            self._progress = None
        self.update()

    def _set_glow(self, value: float) -> None:
        self._glow = value
        self.update()

    def appear(self) -> None:
        if not self._placed:
            self.place()
        if self.isVisible() and not self._leaving:
            return
        self._leaving = False
        start = self.windowOpacity() if self.isVisible() else 0.0
        self.setWindowOpacity(start)
        self.show()
        motion.tween(self, start, OPACITY, motion.GENTLE, self.setWindowOpacity, motion.DECELERATE, key="fade")

    def disappear(self) -> None:
        if not self.isVisible() or self._leaving:
            return
        self._leaving = True

        def done():
            if self._leaving:
                self.hide()
                self._leaving = False

        motion.tween(
            self, self.windowOpacity(), 0.0, motion.FAST, self.setWindowOpacity, motion.ACCELERATE, done, key="fade"
        )

    # -- position ------------------------------------------------------------

    def place(self) -> None:
        """Move to the remembered spot, or the top-right corner of the main screen."""
        self._placed = True
        saved = db.get_setting("overlay_pos") or ""
        try:
            x, y = (int(v) for v in saved.split(","))
            point = QPoint(x, y)
        except ValueError:
            point = None
        if point is not None and QGuiApplication.screenAt(point + QPoint(self.W // 2, self.H // 2)):
            self.move(point)
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.right() - self.W - MARGIN, geo.top() + MARGIN)

    def save_position(self) -> None:
        db.set_setting("overlay_pos", f"{self.x()},{self.y()}")

    # -- input ---------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event):
        if self._drag is not None:
            self._drag = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.save_position()

    def mouseDoubleClickEvent(self, event):
        self.open_requested.emit()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction(f"Open {APP_NAME}", self.open_requested.emit)
        menu.addAction("Hide floating timer", self.hide_requested.emit)
        menu.exec(event.globalPos())

    # -- paint ---------------------------------------------------------------

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(0.5, 0.5, self.W - 1, self.H - 1)
        path = QPainterPath()
        path.addRoundedRect(box, 12, 12)
        p.fillPath(path, QColor(t.surface))
        p.setPen(QPen(QColor(t.border_strong), 1))
        p.drawPath(path)
        if self._glow > 0:
            ring = QColor(t.accent)
            ring.setAlphaF(self._glow)
            p.setPen(QPen(ring, 2))
            p.drawPath(path)

        # Status dot: accent while a focus app is building flow.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.accent if self._focus else t.text_muted))
        p.drawEllipse(QPointF(16, 20), 3.5, 3.5)

        clock = fmt.clock(self._session_ms)
        p.setFont(fonts.sans(16, 600, tabular=True))
        clock_w = p.fontMetrics().horizontalAdvance(clock)
        p.setPen(QColor(t.text))
        p.drawText(QPointF(self.W - 14 - clock_w, 26), clock)

        p.setFont(fonts.sans(12, 600))
        name = p.fontMetrics().elidedText(self._name, Qt.TextElideMode.ElideRight, self.W - 28 - 14 - clock_w - 10)
        p.drawText(QPointF(28, 25), name)

        p.setFont(fonts.mono(9, 500, 4))
        p.setPen(QColor(t.accent_text if self._focus else t.text_muted))
        p.drawText(QPointF(28, 41), self._detail)

        if self._progress is not None:
            x0, x1, y = self.W - 14 - 64, self.W - 14, 38
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.track))
            p.drawRoundedRect(QRectF(x0, y - 1.5, x1 - x0, 3), 1.5, 1.5)
            if self._progress > 0:
                p.setBrush(QColor(t.accent))
                p.drawRoundedRect(QRectF(x0, y - 1.5, max(3.0, (x1 - x0) * self._progress), 3), 1.5, 1.5)


def _tier_progress(run_ms: int) -> float:
    minutes = run_ms / 60000
    index = economy.tier_index(minutes)
    tiers = economy.FLOW_TIERS
    if index + 1 >= len(tiers):
        return 1.0
    start, end = tiers[index][0], tiers[index + 1][0]
    return max(0.0, min(1.0, (minutes - start) / (end - start)))
