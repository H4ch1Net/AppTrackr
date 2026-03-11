"""Calendar heatmap view."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QScrollArea, QPushButton, QFrame, QSizePolicy,
)

from .. import theme
from ...data import queries
from ..widgets.components import NeonCard, AppRow


class HeatmapCell(QWidget):
    """Single day cell in the calendar heatmap."""

    clicked = Signal(str)  # emits day string YYYY-MM-DD

    def __init__(self, day_str: str, total_ms: int, max_ms: int, parent=None):
        super().__init__(parent)
        self._day = day_str
        self._total_ms = total_ms
        self._max_ms = max_ms
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{day_str}\n{theme.format_ms(total_ms)}")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._total_ms == 0:
            color = QColor(theme.BG_CARD)
        else:
            intensity = min(self._total_ms / max(self._max_ms, 1), 1.0)
            c = QColor(theme.get_accent())
            c.setAlphaF(0.15 + intensity * 0.85)
            color = c
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(1, 1, 26, 26, 4, 4)

        # Day number
        if self._day:
            day_num = int(self._day.split("-")[2])
            p.setPen(QColor(theme.TEXT if self._total_ms > 0 else theme.TEXT_MUTED))
            p.setFont(QFont("Segoe UI", 8))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(day_num))
        p.end()

    def mousePressEvent(self, event):
        self.clicked.emit(self._day)


class CalendarView(QWidget):
    """Calendar heatmap + day drilldown."""

    app_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_month = date.today().replace(day=1)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QLabel("Calendar")
        header.setObjectName("heading")
        layout.addWidget(header)

        # Month nav
        nav_row = QHBoxLayout()
        self._prev_btn = QPushButton("◀")
        self._prev_btn.setFixedSize(36, 36)
        self._prev_btn.clicked.connect(self._prev_month)
        nav_row.addWidget(self._prev_btn)

        self._month_label = QLabel()
        self._month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._month_label.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {theme.TEXT}; background: transparent;")
        nav_row.addWidget(self._month_label, stretch=1)

        self._next_btn = QPushButton("▶")
        self._next_btn.setFixedSize(36, 36)
        self._next_btn.clicked.connect(self._next_month)
        nav_row.addWidget(self._next_btn)
        layout.addLayout(nav_row)

        # Heatmap grid
        self._grid_container = NeonCard(glow_color=theme.BG_CARD)
        self._grid_layout = QGridLayout()
        self._grid_layout.setSpacing(4)
        self._grid_container.content_layout().addLayout(self._grid_layout)
        layout.addWidget(self._grid_container)

        # Day drilldown
        self._drill_label = QLabel("Click a day to see details")
        self._drill_label.setObjectName("subheading")
        layout.addWidget(self._drill_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._drill_container = QWidget()
        self._drill_container.setStyleSheet("background: transparent;")
        self._drill_layout = QVBoxLayout(self._drill_container)
        self._drill_layout.setContentsMargins(0, 0, 0, 0)
        self._drill_layout.setSpacing(6)
        self._drill_layout.addStretch()
        scroll.setWidget(self._drill_container)
        layout.addWidget(scroll, stretch=1)

    def refresh(self):
        self._month_label.setText(self._current_month.strftime("%B %Y"))

        # Clear grid
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Day-of-week headers
        for i, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 10px; background: transparent;")
            self._grid_layout.addWidget(lbl, 0, i)

        # Get month range
        year = self._current_month.year
        month = self._current_month.month
        _, days_in_month = calendar.monthrange(year, month)
        start_day = self._current_month.isoformat()
        end_day = date(year, month, days_in_month).isoformat()

        # Fetch data
        daily = {d["day"]: d["total_ms"] for d in queries.daily_totals_range(start_day, end_day)}
        max_ms = max(daily.values()) if daily else 1

        # Build cells
        first_weekday = self._current_month.weekday()  # 0=Monday
        for day_num in range(1, days_in_month + 1):
            d = date(year, month, day_num)
            day_str = d.isoformat()
            total_ms = daily.get(day_str, 0)
            cell = HeatmapCell(day_str, total_ms, max_ms)
            cell.clicked.connect(self._show_day)
            row = 1 + (first_weekday + day_num - 1) // 7
            col = (first_weekday + day_num - 1) % 7
            self._grid_layout.addWidget(cell, row, col)

    def _show_day(self, day_str: str):
        self._drill_label.setText(f"Apps on {day_str}")

        # Clear
        while self._drill_layout.count() > 1:
            item = self._drill_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        apps = queries.day_breakdown(day_str)
        if not apps:
            lbl = QLabel("No data for this day")
            lbl.setStyleSheet(f"color: {theme.TEXT_MUTED}; background: transparent;")
            self._drill_layout.insertWidget(0, lbl)
            return

        max_ms = max(a.get("focused_ms", 1) for a in apps)
        for i, app in enumerate(apps):
            row = AppRow(
                app_id=app["app_id"],
                name=app.get("display_name") or app["exe_name"],
                value_ms=app.get("focused_ms", 0),
                max_ms=max_ms,
                is_favorite=False,
            )
            row.clicked.connect(self.app_selected.emit)
            self._drill_layout.insertWidget(i, row)

    def _prev_month(self):
        if self._current_month.month == 1:
            self._current_month = self._current_month.replace(year=self._current_month.year - 1, month=12)
        else:
            self._current_month = self._current_month.replace(month=self._current_month.month - 1)
        self.refresh()

    def _next_month(self):
        if self._current_month.month == 12:
            self._current_month = self._current_month.replace(year=self._current_month.year + 1, month=1)
        else:
            self._current_month = self._current_month.replace(month=self._current_month.month + 1)
        self.refresh()
