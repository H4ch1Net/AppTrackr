"""Custom-painted charts: bar chart, month heatmap and stacked share bar."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from .. import fmt, theme


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
        self.setMinimumHeight(height)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(400, self.minimumHeight())

    def set_data(
        self,
        bars: list[Bar],
        highlight: int | None = None,
        limit: float | None = None,
        empty_text: str = "No activity yet",
    ) -> None:
        self._bars = bars
        self._highlight = highlight
        self._limit = limit
        self._empty_text = empty_text
        self.update()

    def _geometry(self):
        left, right, top, bottom = 44, 6, 8, 22
        plot = QRectF(left, top, max(10, self.width() - left - right), max(10, self.height() - top - bottom))
        n = max(1, len(self._bars))
        slot = plot.width() / n
        bar_w = max(2.0, min(28.0, slot * 0.62))
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
            p.setFont(_font(self, 12))
            p.drawText(plot, Qt.AlignmentFlag.AlignCenter, self._empty_text)

        step = _nice_step(peak)
        top_value = max(step, ((peak + step - 1) // step) * step)
        p.setFont(_font(self, 10))
        grid_pen = QPen(QColor(t.border), 1, Qt.PenStyle.DashLine)
        v = 0
        while v <= top_value:
            y = plot.bottom() - plot.height() * v / top_value
            p.setPen(grid_pen if v else QPen(QColor(t.border_strong), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(t.text_muted))
            p.drawText(
                QRectF(0, y - 8, plot.left() - 8, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                fmt.duration(v, short=True) if v else "0",
            )
            v += step

        accent = QColor(t.accent)
        for i, bar in enumerate(self._bars):
            x = plot.left() + slot * i + (slot - bar_w) / 2
            h = plot.height() * bar.value / top_value
            color = QColor(accent)
            if self._highlight is not None and i != self._highlight:
                color.setAlphaF(0.55)
            if self._limit and bar.value > self._limit:
                color = QColor(t.danger)
            if i == self._hover:
                color = color.lighter(120) if t.dark else color.darker(110)
            if h > 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(color)
                radius = min(4.0, bar_w / 2)
                p.drawRoundedRect(QRectF(x, plot.bottom() - max(h, 2), bar_w, max(h, 2)), radius, radius)
            if bar.label:
                p.setPen(QColor(t.text if i == self._highlight else t.text_muted))
                p.setFont(_font(self, 10, bold=i == self._highlight))
                p.drawText(QRectF(x - 20, plot.bottom() + 4, bar_w + 40, 16), Qt.AlignmentFlag.AlignHCenter, bar.label)

        if self._limit:
            y = plot.bottom() - plot.height() * self._limit / top_value
            p.setPen(QPen(QColor(t.danger), 1.5, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
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
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(320, 260)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setAccessibleName("Usage calendar")

    def set_month(self, month: date, totals: dict[str, int]) -> None:
        self._month = month.replace(day=1)
        self._totals = totals
        self.update()

    def set_selected(self, day: date | None) -> None:
        self._selected = day
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
            self._selected = d
            self.update()
            self.day_selected.emit(d.isoformat())

    def keyPressEvent(self, event):
        steps = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1, Qt.Key.Key_Up: -7, Qt.Key.Key_Down: 7}
        if event.key() in steps:
            base = self._selected or date.today()
            new = base + timedelta(days=steps[event.key()])
            if new <= date.today():
                self._selected = new
                if new.replace(day=1) != self._month:
                    self._month = new.replace(day=1)
                self.update()
                self.day_selected.emit(new.isoformat())
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        header, gap, cw, ch = self._layout()

        p.setFont(_font(self, 11, bold=True))
        p.setPen(QColor(t.text_muted))
        for i, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            p.drawText(QRectF(i * (cw + gap), 0, cw, header - 6), Qt.AlignmentFlag.AlignCenter, name)

        values = [v for k, v in self._totals.items() if k.startswith(self._month.strftime("%Y-%m"))]
        peak = max(values) if values else 1
        today = date.today()
        days = calendar.monthrange(self._month.year, self._month.month)[1]
        accent = QColor(t.accent)
        big = ch >= 46 and cw >= 54

        for n in range(1, days + 1):
            d = self._month.replace(day=n)
            r = self._cell_rect(d)
            ms = self._totals.get(d.isoformat(), 0)
            future = d > today
            if ms > 0:
                fill = QColor(accent)
                fill.setAlphaF(0.18 + 0.82 * (ms / peak) ** 0.8)
            else:
                fill = QColor(t.track if not future else t.surface_alt)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(r, 8, 8)

            if d == self._hover and not future:
                p.setPen(QPen(QColor(t.text_muted), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
            if d == today:
                p.setPen(QPen(QColor(t.text), 1.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 7, 7)
            if d == self._selected:
                p.setPen(QPen(QColor(t.accent if not self.hasFocus() else t.text), 2.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(1.5, 1.5, -1.5, -1.5), 7, 7)

            strong = ms > 0 and ms / peak > 0.55
            text_color = QColor(t.on_accent) if strong else QColor(t.text_muted if future else t.text)
            p.setPen(text_color)
            p.setFont(_font(self, 12 if big else 11, bold=d == today))
            if big:
                p.drawText(r.adjusted(8, 6, -6, -6), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, str(n))
                if ms:
                    p.setFont(_font(self, 10))
                    p.drawText(
                        r.adjusted(8, 6, -6, -6),
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                        fmt.duration(ms, short=True),
                    )
            else:
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, str(n))
        p.end()


class ShareBar(QWidget):
    """Single stacked bar showing each segment's share of the total."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: list[tuple[str, float, str]] = []
        self.setFixedHeight(12)
        self.setMouseTracking(True)

    def set_segments(self, segments: list[tuple[str, float, str]]) -> None:
        self._segments = [s for s in segments if s[1] > 0]
        self.update()

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
        p.setBrush(QColor(t.track))
        p.drawRoundedRect(QRectF(0, 0, self.width(), h), h / 2, h / 2)
        total = sum(v for _, v, _ in self._segments)
        if not total:
            return
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, self.width(), h), h / 2, h / 2)
        p.setClipPath(clip)
        x = 0.0
        for _name, value, color in self._segments:
            w = self.width() * value / total
            p.setBrush(QColor(color))
            p.drawRect(QRectF(x, 0, w + 0.5, h))
            x += w
        p.end()


CATEGORY_COLORS = {
    "Work": "#4f8cff",
    "Study": "#a274ff",
    "Development": "#10c79a",
    "Communication": "#f5b82e",
    "Games": "#f2545b",
    "Social": "#f0609e",
    "Entertainment": "#ff8a3d",
    "Tools": "#8a94a6",
    None: "#5b6474",
}


def category_color(category: str | None) -> str:
    return CATEGORY_COLORS.get(category, CATEGORY_COLORS[None])
