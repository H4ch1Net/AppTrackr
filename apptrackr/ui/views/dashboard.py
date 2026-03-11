"""Dashboard view – Now Tracking + today stats + top apps."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton, QFrame,
)

from .. import theme
from ..widgets.components import NeonCard, StatValue, AppRow
from ...data import queries


class DashboardView(QWidget):
    """Main dashboard with live tracking info and today's stats."""

    app_selected = Signal(int)

    def __init__(self, tracker, parent=None):
        super().__init__(parent)
        self._tracker = tracker
        self._build_ui()

        # Auto-refresh every 1 second
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(1000)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # -- Header --
        header = QLabel("Dashboard")
        header.setObjectName("heading")
        layout.addWidget(header)

        # -- Now Tracking card --
        now_card = NeonCard(glow_color=theme.get_accent(), title="NOW TRACKING")
        now_layout = now_card.content_layout()

        self._now_app = QLabel("—")
        self._now_app.setStyleSheet(
            f"font-size: 22px; font-weight: 700; color: {theme.TEXT}; background: transparent;"
        )
        now_layout.addWidget(self._now_app)

        self._now_timer = QLabel("0s")
        self._now_timer.setStyleSheet(
            f"font-size: 36px; font-weight: 700; color: {theme.get_accent()}; background: transparent;"
        )
        now_layout.addWidget(self._now_timer)

        # Pause button
        btn_row = QHBoxLayout()
        self._pause_btn = QPushButton("⏸  Pause Tracking")
        self._pause_btn.setObjectName("primary")
        self._pause_btn.clicked.connect(self._toggle_pause)
        btn_row.addWidget(self._pause_btn)
        btn_row.addStretch()
        now_layout.addLayout(btn_row)

        layout.addWidget(now_card)

        # -- Stats row --
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)

        self._today_total = StatValue("0m", "Today Total", theme.get_accent())
        self._week_total = StatValue("0m", "This Week", theme.PURPLE)
        self._apps_count = StatValue("0", "Apps Today", theme.BLUE)
        self._streak = StatValue("0", "Streak Days", theme.YELLOW)

        for w in (self._today_total, self._week_total, self._apps_count, self._streak):
            card = NeonCard(glow_color=theme.BG_CARD)
            card.content_layout().addWidget(w)
            stats_row.addWidget(card)

        layout.addLayout(stats_row)

        # -- Top Apps today --
        top_label = QLabel("Top Apps Today")
        top_label.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {theme.TEXT}; background: transparent;"
        )
        layout.addWidget(top_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._apps_container = QWidget()
        self._apps_container.setStyleSheet("background: transparent;")
        self._apps_layout = QVBoxLayout(self._apps_container)
        self._apps_layout.setContentsMargins(0, 0, 0, 0)
        self._apps_layout.setSpacing(6)
        self._apps_layout.addStretch()
        scroll.setWidget(self._apps_container)
        layout.addWidget(scroll, stretch=1)

    def refresh(self):
        # Now tracking
        exe = self._tracker.current_exe
        if exe and not self._tracker.paused:
            app_id = self._tracker.current_app_id
            app = queries.get_app(app_id) if app_id else None
            label = (app.get("display_name") if app else "") or ""
            if label.strip().lower() == exe.lower() or not label.strip():
                label = queries.normalize_app_name(exe)
            self._now_app.setText(label)
            self._now_timer.setText(theme.format_ms(self._tracker.session_elapsed_ms))
            self._pause_btn.setText("⏸  Pause Tracking")
        elif self._tracker.paused:
            self._now_app.setText("Paused")
            self._now_timer.setText("—")
            self._pause_btn.setText("▶  Resume Tracking")
        else:
            self._now_app.setText("—")
            self._now_timer.setText("0s")

        # Today total
        today_ms = queries.today_total_ms()
        self._today_total.set_value(theme.format_ms(today_ms))

        # Week total
        week_apps = queries.weekly_totals(limit=100)
        week_ms = sum(a.get("focused_ms", 0) for a in week_apps)
        self._week_total.set_value(theme.format_ms(week_ms))

        # Apps count
        top = queries.dashboard_top_apps_today(limit=50)
        self._apps_count.set_value(str(len(top)))

        # Streak
        from ...rewards import engine as reward_engine
        profile = reward_engine.get_profile()
        self._streak.set_value(str(profile.get("streak_days", 0)))

        # Top apps list
        self._rebuild_app_list(top)

    def _rebuild_app_list(self, apps: list[dict]):
        # Clear existing
        while self._apps_layout.count() > 1:
            item = self._apps_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not apps:
            empty = QLabel("No apps tracked yet today")
            empty.setStyleSheet(f"color: {theme.TEXT_MUTED}; padding: 20px; background: transparent;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._apps_layout.insertWidget(0, empty)
            return

        max_ms = max(a.get("focused_ms", 1) for a in apps)
        for i, app in enumerate(apps[:10]):
            raw_name = (app.get("display_name") or "").strip()
            if not raw_name or raw_name.lower() == (app.get("exe_name") or "").lower():
                shown_name = queries.normalize_app_name(app.get("exe_name", ""))
            else:
                shown_name = raw_name
            row = AppRow(
                app_id=app["app_id"],
                name=shown_name,
                value_ms=app.get("focused_ms", 0),
                max_ms=max_ms,
                is_favorite=bool(app.get("is_favorite")),
                icon_path=app.get("icon_path"),
            )
            row.clicked.connect(self.app_selected.emit)
            self._apps_layout.insertWidget(i, row)

    def _toggle_pause(self):
        if self._tracker.paused:
            self._tracker.resume()
        else:
            self._tracker.pause()
        self.refresh()
