"""Custom-painted charts: bar chart, month heatmap and stacked share bar."""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import date, timedelta

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from .. import fmt, fonts, motion, theme


def _font(widget: QWidget, px: int, bold: bool = False) -> QFont:
    f = QFont(widget.font())
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def _nice_step(max_ms: float) -> int:
    """Gridline spacing in ms giving 2-4 lines."""
    minute, hour = 60_000, 3_600_000
    for step in (
        5 * minute,
        10 * minute,
        15 * minute,
        30 * minute,
        hour,
        2 * hour,
        3 * hour,
        4 * hour,
        6 * hour,
        12 * hour,
    ):
        if max_ms / step <= 4:
            return step
    return 24 * hour


def _column(x: float, baseline: float, width: float, height: float, radius: float = 3.0) -> QPainterPath:
    """Bar with rounded data-end and a square baseline."""
    r = min(radius, width / 2, height)
    top = baseline - height
    path = QPainterPath()
    path.moveTo(x, baseline)
    path.lineTo(x, top + r)
    path.quadTo(x, top, x + r, top)
    path.lineTo(x + width - r, top)
    path.quadTo(x + width, top, x + width, top + r)
    path.lineTo(x + width, baseline)
    path.closeSubpath()
    return path


@dataclass
class Bar:
    label: str  # axis label ('' to hide)
    value: float
    tooltip: str = ""


class BarChart(QWidget):
    """Vertical bars with gridlines, hover tooltips and an optional limit line."""

    bar_clicked = Signal(int)

    def __init__(self, height: int = 170, parent=None):
        super().__init__(parent)
        self._bars: list[Bar] = []
        self._highlight: int | None = None
        self._hover: int | None = None
        self._limit: float | None = None
        self._empty_text = "No activity yet"
        # Animation state: bars ease from _from to _to; _progress runs 0..1 over the series.
        self._from: list[float] = []
        self._to: list[float] = []
        self._progress = 1.0
        self._growing = False
        self._pending = False
        self.setMinimumHeight(height)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(400, self.minimumHeight())

    # Motion ------------------------------------------------------------------

    def _stagger(self) -> float:
        return min(18.0, 320.0 / max(1, len(self._to)))

    def _total_ms(self) -> int:
        return int(motion.SLOWER + self._stagger() * max(0, len(self._to) - 1))

    def _shown(self, i: int) -> float:
        if self._progress >= 1.0 or i >= len(self._from):
            return self._to[i] if i < len(self._to) else 0.0
        local = (self._progress * self._total_ms() - i * self._stagger()) / motion.SLOWER
        local = min(1.0, max(0.0, local))
        curve = motion.DECELERATE if self._growing else motion.EASY_EASE
        return motion.lerp(self._from[i], self._to[i], curve.valueForProgress(local))

    def _set_progress(self, value: float) -> None:
        self._progress = value
        self.update()

    def _start(self) -> None:
        self._progress = 0.0
        motion.tween(self, 0.0, 1.0, self._total_ms(), self._set_progress, motion.LINEAR, key="bars")

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending:
            self._pending = False
            self._start()

    def set_data(
        self,
        bars: list[Bar],
        highlight: int | None = None,
        limit: float | None = None,
        empty_text: str = "No activity yet",
    ) -> None:
        target = [float(b.value) for b in bars]
        current = [self._shown(i) for i in range(len(self._to))]
        self._growing = len(current) != len(target) or not any(current)
        self._from = [0.0] * len(target) if self._growing else current
        self._to = target
        self._bars = bars
        self._highlight = highlight
        self._limit = limit
        self._empty_text = empty_text
        if all(abs(a - b) < 1 for a, b in zip(self._from, self._to, strict=True)):
            self._progress = 1.0
        elif self.isVisible():
            self._start()
        else:
            self._progress = 0.0
            self._pending = True
        self.update()

    def _geometry(self):
        left, right, top, bottom = 46, 4, 18, 30
        plot = QRectF(left, top, max(10, self.width() - left - right), max(10, self.height() - top - bottom))
        n = max(1, len(self._bars))
        slot = plot.width() / n
        bar_w = max(2.0, min(20.0, slot * 0.56))
        return plot, slot, bar_w

    def _index_at(self, x: float) -> int | None:
        if not self._bars:
            return None
        plot, slot, _ = self._geometry()
        if x < plot.left() or x > plot.right():
            return None
        return min(len(self._bars) - 1, int((x - plot.left()) // slot))

    def mouseMoveEvent(self, event):
        idx = self._index_at(event.position().x())
        if idx != self._hover:
            self._hover = idx
            self.update()
        if idx is not None and self._bars[idx].tooltip:
            QToolTip.showText(event.globalPosition().toPoint(), self._bars[idx].tooltip, self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, _event):
        self._hover = None
        self.update()

    def mouseReleaseEvent(self, event):
        idx = self._index_at(event.position().x())
        if idx is not None:
            self.bar_clicked.emit(idx)

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot, slot, bar_w = self._geometry()
        peak = max([b.value for b in self._bars] + [self._limit or 0, 1])

        if not any(b.value for b in self._bars):
            p.setPen(QColor(t.text_muted))
            p.setFont(fonts.sans(12))
            p.drawText(plot, Qt.AlignmentFlag.AlignCenter, self._empty_text)

        # Gridlines: solid hairlines, labels engraved in mono.
        step = _nice_step(peak)
        top_value = max(step, ((peak + step - 1) // step) * step)
        p.setFont(fonts.mono(9, 400, 4))
        v = 0
        while v <= top_value:
            y = round(plot.bottom() - plot.height() * v / top_value) + 0.5
            p.setPen(QPen(QColor(t.border_strong if v == 0 else t.border), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(t.text_muted))
            p.drawText(
                QRectF(0, y - 8, plot.left() - 10, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                fmt.axis(v),
            )
            v += step

        # Tick ruler under the baseline: a minor tick per slot, a major tick per label.
        base = round(plot.bottom()) + 0.5
        for i, bar in enumerate(self._bars):
            cx = plot.left() + slot * i + slot / 2
            major = bool(bar.label)
            p.setPen(QPen(QColor(t.text_muted if major else t.border_strong), 1))
            p.drawLine(QPointF(cx, base + 2), QPointF(cx, base + (7 if major else 4)))

        ink = QColor(t.ink)
        for i, bar in enumerate(self._bars):
            x = plot.left() + slot * i + (slot - bar_w) / 2
            h = plot.height() * self._shown(i) / top_value
            highlighted = i == self._highlight
            color = QColor(t.accent) if highlighted or self._highlight is None else QColor(ink)
            if self._limit and bar.value > self._limit:
                color = QColor(t.danger)
            if i == self._hover:
                color = QColor(t.text_dim) if color == ink else color.lighter(115) if t.dark else color.darker(110)
            if h > 0.5:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(color)
                p.drawPath(_column(x, plot.bottom(), bar_w, max(h, 2.0)))
            if highlighted and bar.value > 0 and h > 0.5:
                p.setPen(QColor(t.text))
                p.setFont(fonts.sans(11, 600, tabular=True))
                p.drawText(
                    QRectF(x - 30, plot.bottom() - h - 17, bar_w + 60, 14),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                    fmt.duration(bar.value, short=True),
                )
            if bar.label:
                p.setPen(QColor(t.text if highlighted else t.text_muted))
                p.setFont(fonts.mono(9, 500 if highlighted else 400, 4))
                p.drawText(QRectF(x - 20, base + 9, bar_w + 40, 14), Qt.AlignmentFlag.AlignHCenter, bar.label)

        if self._limit:
            y = round(plot.bottom() - plot.height() * self._limit / top_value) + 0.5
            p.setPen(QPen(QColor(t.danger), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setFont(fonts.mono(9, 500, 6))
            p.drawText(
                QRectF(plot.left(), y - 15, plot.width() - 2, 13),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                f"LIMIT {fmt.duration(self._limit, short=True).upper()}",
            )
        p.end()


class MonthHeatmap(QWidget):
    """Calendar month with cells shaded by focused time. Keyboard and mouse navigable."""

    day_selected = Signal(str)

    COLS = 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self._month = date.today().replace(day=1)
        self._totals: dict[str, int] = {}
        self._selected: date | None = date.today()
        self._hover: date | None = None
        self._wave = 1.0  # 0..1 entrance progress after a month change
        self._ring: QRectF | None = None  # animated selection ring while gliding
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(320, 260)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setAccessibleName("Usage calendar")

    WAVE_STEP = 9  # ms between consecutive days

    def set_month(self, month: date, totals: dict[str, int]) -> None:
        changed = month.replace(day=1) != self._month
        self._month = month.replace(day=1)
        self._totals = totals
        if changed and self.isVisible():
            days = calendar.monthrange(self._month.year, self._month.month)[1]
            motion.tween(
                self, 0.0, 1.0, motion.NORMAL + self.WAVE_STEP * days, self._set_wave, motion.LINEAR, key="wave"
            )
        self.update()

    def _set_wave(self, value: float) -> None:
        self._wave = value
        self.update()

    def _cell_wave(self, day: int) -> float:
        """Entrance progress (0..1) for one cell during the month-change wave."""
        if self._wave >= 1.0:
            return 1.0
        days = calendar.monthrange(self._month.year, self._month.month)[1]
        elapsed = self._wave * (motion.NORMAL + self.WAVE_STEP * days) - (day - 1) * self.WAVE_STEP
        return motion.DECELERATE.valueForProgress(min(1.0, max(0.0, elapsed / motion.NORMAL)))

    def set_selected(self, day: date | None) -> None:
        self._glide_to(day)

    def _glide_to(self, day: date | None) -> None:
        old = self._selected
        self._selected = day
        same_month = day and old and day.replace(day=1) == old.replace(day=1) == self._month
        if same_month and day != old and self.isVisible():
            start, end = self._ring or self._cell_rect(old), self._cell_rect(day)
            motion.tween(
                self, start, end, motion.NORMAL, self._set_ring, motion.EASY_EASE, on_done=self._end_ring, key="ring"
            )
        else:
            self._ring = None
        self.update()

    def _set_ring(self, rect: QRectF) -> None:
        self._ring = QRectF(rect)
        self.update()

    def _end_ring(self) -> None:
        self._ring = None
        self.update()

    def _weeks(self) -> int:
        first_col = self._month.weekday()
        days = calendar.monthrange(self._month.year, self._month.month)[1]
        return (first_col + days + 6) // 7

    def _layout(self):
        header = 24
        gap = 6
        weeks = self._weeks()
        cell_w = (self.width() - gap * (self.COLS - 1)) / self.COLS
        cell_h = min(cell_w * 0.82, (self.height() - header - gap * (weeks - 1)) / weeks)
        return header, gap, cell_w, max(24.0, cell_h)

    def _cell_rect(self, d: date) -> QRectF:
        header, gap, cw, ch = self._layout()
        index = self._month.weekday() + d.day - 1
        row, col = divmod(index, self.COLS)
        return QRectF(col * (cw + gap), header + row * (ch + gap), cw, ch)

    def _day_at(self, pos: QPointF) -> date | None:
        days = calendar.monthrange(self._month.year, self._month.month)[1]
        for n in range(1, days + 1):
            d = self._month.replace(day=n)
            if self._cell_rect(d).contains(pos):
                return d
        return None

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        cell_w = (width - 6 * (self.COLS - 1)) / self.COLS
        return int(24 + self._weeks() * (cell_w * 0.82 + 6))

    def sizeHint(self) -> QSize:
        return QSize(460, self.heightForWidth(460))

    def mouseMoveEvent(self, event):
        d = self._day_at(event.position())
        if d != self._hover:
            self._hover = d
            self.update()
        if d:
            ms = self._totals.get(d.isoformat(), 0)
            tip = f"{fmt.long_date(d)}\n{fmt.duration(ms) if ms else 'No activity'}"
            QToolTip.showText(event.globalPosition().toPoint(), tip, self)

    def leaveEvent(self, _event):
        self._hover = None
        self.update()

    def mouseReleaseEvent(self, event):
        d = self._day_at(event.position())
        if d and d <= date.today():
            self._glide_to(d)
            self.day_selected.emit(d.isoformat())

    def keyPressEvent(self, event):
        steps = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1, Qt.Key.Key_Up: -7, Qt.Key.Key_Down: 7}
        if event.key() in steps:
            base = self._selected or date.today()
            new = base + timedelta(days=steps[event.key()])
            if new <= date.today():
                if new.replace(day=1) == self._month:
                    self._glide_to(new)
                else:
                    self._selected = new
                self.day_selected.emit(new.isoformat())
            return
        super().keyPressEvent(event)

    @staticmethod
    def level(ms: int, peak: int) -> int:
        """Quantize a day into 0 (empty) or 1..4 so steps read like LED segments."""
        if ms <= 0:
            return 0
        return min(4, 1 + int(4 * ms / max(peak, 1) - 1e-9))

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        header, gap, cw, ch = self._layout()

        p.setFont(fonts.mono(9, 500, 8))
        p.setPen(QColor(t.text_muted))
        for i, name in enumerate(("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")):
            p.drawText(
                QRectF(i * (cw + gap) + 2, 0, cw, header - 8),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                name,
            )

        values = [v for k, v in self._totals.items() if k.startswith(self._month.strftime("%Y-%m"))]
        peak = max(values) if values else 1
        today = date.today()
        days = calendar.monthrange(self._month.year, self._month.month)[1]
        big = ch >= 46 and cw >= 54
        radius = 3.0

        for n in range(1, days + 1):
            d = self._month.replace(day=n)
            r = self._cell_rect(d)
            enter = self._cell_wave(n)
            if enter <= 0.0:
                continue
            p.setOpacity(enter)
            if enter < 1.0:
                shrink = (1 - enter) * 0.08
                r = r.adjusted(r.width() * shrink, r.height() * shrink, -r.width() * shrink, -r.height() * shrink)
            ms = self._totals.get(d.isoformat(), 0)
            future = d > today
            level = self.level(ms, peak)
            p.setPen(Qt.PenStyle.NoPen)
            if future:
                p.setPen(QPen(QColor(t.border), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
            else:
                p.setBrush(QColor(t.heat(max(level, 1) if d == today and ms else level, today=d == today)))
                p.drawRoundedRect(r, radius, radius)

            if d == self._hover and not future:
                p.setPen(QPen(QColor(t.text_dim), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
            if d == today:
                # Today: a notch in the corner, like an index mark on a dial.
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(t.text))
                notch = QPainterPath()
                notch.moveTo(r.right() - 9, r.top())
                notch.lineTo(r.right() - radius, r.top())
                notch.quadTo(r.right(), r.top(), r.right(), r.top() + radius)
                notch.lineTo(r.right(), r.top() + 9)
                notch.closeSubpath()
                p.drawPath(notch)

            strong = level >= 3
            if d == today and ms:
                text_color = QColor(t.on_accent if level >= 3 else t.text)
            elif strong:
                text_color = QColor(t.window)
            else:
                text_color = QColor(t.text_muted if future or not ms else t.text)
            p.setPen(text_color)
            p.setFont(fonts.mono(10 if big else 9, 500 if d == today else 400, 0))
            if big:
                p.drawText(r.adjusted(7, 5, -6, -5), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, f"{n:02d}")
                if ms:
                    p.setFont(fonts.sans(11, 600, tabular=True))
                    p.drawText(
                        r.adjusted(7, 5, -6, -5),
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                        fmt.duration(ms, short=True),
                    )
            else:
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, str(n))
        p.setOpacity(1.0)

        ring = self._ring
        if ring is None and self._selected and self._selected.replace(day=1) == self._month:
            ring = self._cell_rect(self._selected)
        if ring is not None:
            p.setPen(QPen(QColor(t.text if self.hasFocus() else t.accent), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(ring.adjusted(-2, -2, 2, 2), radius + 2, radius + 2)
        p.end()


class ShareBar(QWidget):
    """Single stacked bar showing each segment's share of the total."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: list[tuple[str, float, str]] = []
        self._from: dict[str, float] = {}
        self._to: dict[str, float] = {}
        self._t = 1.0
        self._pending = False
        self.setFixedHeight(8)
        self.setMouseTracking(True)

    def set_segments(self, segments: list[tuple[str, float, str]]) -> None:
        self._from = {name: self._share(name) for name in self._to}
        self._segments = [s for s in segments if s[1] > 0]
        total = sum(v for _, v, _ in self._segments) or 1
        self._to = {name: v / total for name, v, _ in self._segments}
        if self._from == self._to:
            return
        if self.isVisible():
            self._start()
        else:
            self._t, self._pending = 0.0, True
        self.update()

    def _share(self, name: str) -> float:
        return motion.lerp(self._from.get(name, 0.0), self._to.get(name, 0.0), self._t)

    def _start(self) -> None:
        motion.tween(self, 0.0, 1.0, motion.SLOWER, self._set_t, motion.EASY_EASE, key="share")

    def _set_t(self, value: float) -> None:
        self._t = value
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending:
            self._pending = False
            self._start()

    def _segment_at(self, x: float):
        total = sum(v for _, v, _ in self._segments) or 1
        pos = 0.0
        for seg in self._segments:
            w = self.width() * seg[1] / total
            if pos <= x < pos + w:
                return seg, seg[1] / total
            pos += w
        return None, 0

    def mouseMoveEvent(self, event):
        seg, share = self._segment_at(event.position().x())
        if seg:
            QToolTip.showText(event.globalPosition().toPoint(), f"{seg[0]}: {fmt.duration(seg[1])} ({share:.0%})", self)

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        p.setPen(Qt.PenStyle.NoPen)
        if not self._segments:
            p.setBrush(QColor(t.track))
            p.drawRoundedRect(QRectF(0, 0, self.width(), h), 2, 2)
            return
        names = [n for n, _, _ in self._segments] + [n for n in self._from if n not in self._to]
        colors = {n: c for n, _, c in self._segments}
        shares = [(n, self._share(n)) for n in names]
        shares = [(n, v) for n, v in shares if v > 0.002]
        total = sum(v for _, v in shares) or 1.0
        gap = 2.0  # surface gap between segments
        filled = self.width() * min(1.0, total)
        usable = max(1.0, filled - gap * max(0, len(shares) - 1))
        x = 0.0
        for name, share in shares:
            w = usable * share / total
            p.setBrush(QColor(colors.get(name, t.text_muted)))
            p.drawRoundedRect(QRectF(x, 0, max(1.0, w), h), 2, 2)
            x += w + gap
        if x < self.width() - gap:
            p.setBrush(QColor(t.track))
            p.drawRoundedRect(QRectF(x, 0, self.width() - x, h), 2, 2)
        p.end()


class HeatLegend(QWidget):
    """ "LESS ■■■■■ MORE" key for the calendar's quantized steps."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(14)
        self.setMinimumWidth(220)

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(fonts.mono(9, 500, 8))
        p.setPen(QColor(t.text_muted))
        x = 0.0
        p.drawText(QRectF(x, 0, 40, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "LESS")
        x = 38.0
        p.setPen(Qt.PenStyle.NoPen)
        for level in range(5):
            p.setBrush(QColor(t.heat(level)))
            p.drawRoundedRect(QRectF(x, 2, 10, 10), 2, 2)
            x += 14
        p.setPen(QColor(t.text_muted))
        p.drawText(QRectF(x + 4, 0, 40, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "MORE")
        x += 54
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.accent))
        p.drawRoundedRect(QRectF(x, 2, 10, 10), 2, 2)
        p.setPen(QColor(t.text_muted))
        p.drawText(QRectF(x + 16, 0, 50, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "TODAY")


class SessionDial(QWidget):
    """Chronograph for the live session: 60 engraved ticks, a minute arc and a seconds hand."""

    def __init__(self, size: int = 156, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._active = False
        self._ms = 0
        self._caption = ""
        self._hand = 0.0  # degrees, eased between seconds
        self._last_second = -1
        self.setAccessibleName("Session timer")

    def set_state(self, active: bool, session_ms: int, caption: str) -> None:
        self._active, self._ms, self._caption = active, session_ms, caption
        second = (session_ms // 1000) % 60
        if active and second != self._last_second:
            target = second * 6.0
            start = self._hand if target >= self._hand else self._hand - 360
            motion.tween(self, start, target, motion.FAST, self._set_hand, motion.EASY_EASE, key="hand")
            self._last_second = second
        elif not active:
            self._last_second = -1
        self.setToolTip(fmt.clock(session_ms) if active else caption)
        self.update()

    def _set_hand(self, value: float) -> None:
        self._hand = value % 360
        self.update()

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        outer = self.width() / 2 - 2

        # Engraved minute ticks.
        for i in range(60):
            angle = math.radians(i * 6 - 90)
            major = i % 5 == 0
            r1 = outer - (8 if major else 4)
            color = QColor(t.text_muted if major else t.border_strong)
            if not self._active:
                color.setAlphaF(0.6)
            p.setPen(QPen(color, 1.5 if major else 1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(
                QPointF(c.x() + r1 * math.cos(angle), c.y() + r1 * math.sin(angle)),
                QPointF(c.x() + outer * math.cos(angle), c.y() + outer * math.sin(angle)),
            )

        # Minute arc: progress through the current hour of the session.
        ring = QRectF(c.x() - outer + 14, c.y() - outer + 14, 2 * (outer - 14), 2 * (outer - 14))
        p.setPen(QPen(QColor(t.track), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawEllipse(ring)
        if self._active:
            minutes = (self._ms % 3_600_000) / 3_600_000
            p.setPen(QPen(QColor(t.accent), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawArc(ring, 90 * 16, int(-minutes * 360 * 16))

            # Seconds pointer: rides the outer scale so it never crosses the readout.
            angle = math.radians(self._hand - 90)
            inner, tip = outer - 20, outer + 1
            p.setPen(QPen(QColor(t.accent), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(
                QPointF(c.x() + inner * math.cos(angle), c.y() + inner * math.sin(angle)),
                QPointF(c.x() + tip * math.cos(angle), c.y() + tip * math.sin(angle)),
            )

        # Readout.
        p.setPen(QColor(t.text if self._active else t.text_muted))
        p.setFont(fonts.sans(26 if self._ms < 3_600_000 else 22, 600, tabular=True))
        text = fmt.clock(self._ms) if self._active else "–:––"
        p.drawText(QRectF(0, c.y() - 22, self.width(), 30), Qt.AlignmentFlag.AlignCenter, text)
        p.setFont(fonts.mono(8, 500, 12))
        p.setPen(QColor(t.text_muted))
        p.drawText(QRectF(0, c.y() + 10, self.width(), 14), Qt.AlignmentFlag.AlignCenter, self._caption.upper())
