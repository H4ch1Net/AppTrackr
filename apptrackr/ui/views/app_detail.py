"""App detail view – trends, history histogram, goals."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QCheckBox,
)

from .. import theme
from ..widgets.components import NeonCard, StatValue, GradientBar
from ...data import queries


class BarChartWidget(QWidget):
    """Simple bar chart for daily history."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[tuple[str, int]] = []  # (day, ms)
        self.setMinimumHeight(160)
        self.setStyleSheet("background: transparent;")

    def set_data(self, data: list[tuple[str, int]]):
        self._data = data
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margin_bottom = 24
        chart_h = h - margin_bottom
        n = len(self._data)
        bar_w = max(min((w - 20) // max(n, 1), 24), 4)
        gap = max(bar_w // 4, 1)
        max_val = max(v for _, v in self._data) if self._data else 1

        x = 10
        for day_str, ms in self._data:
            bar_h = max(int((ms / max(max_val, 1)) * (chart_h - 10)), 0)
            # Gradient bar
            c = QColor(theme.get_accent())
            c.setAlphaF(0.3 + 0.7 * min(ms / max(max_val, 1), 1.0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(x, chart_h - bar_h, bar_w, bar_h, 2, 2)

            # Day label (show every few)
            if n <= 14 or self._data.index((day_str, ms)) % (n // 7 or 1) == 0:
                p.setPen(QColor(theme.TEXT_MUTED))
                from PySide6.QtGui import QFont
                p.setFont(QFont("Segoe UI", 7))
                day_short = day_str[5:]  # MM-DD
                p.drawText(x, h - 4, day_short)

            x += bar_w + gap
        p.end()


class AppDetailView(QWidget):
    """Detailed view for a single app."""

    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._app_id: int | None = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Back button + title
        top_row = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(self.back_clicked.emit)
        top_row.addWidget(back_btn)

        self._title = QLabel("App Details")
        self._title.setObjectName("heading")
        top_row.addWidget(self._title, stretch=1)

        self._fav_btn = QPushButton("☆ Favorite")
        self._fav_btn.clicked.connect(self._toggle_fav)
        top_row.addWidget(self._fav_btn)
        layout.addLayout(top_row)

        # Stats cards
        stats_row = QHBoxLayout()
        self._total_7d = StatValue("0m", "7-Day Total", theme.get_accent())
        self._total_30d = StatValue("0m", "30-Day Total", theme.PURPLE)
        self._opens_stat = StatValue("0", "Opens (7d)", theme.BLUE)
        self._clicks_stat = StatValue("0", "Clicks (7d)", theme.PINK)

        for w in (self._total_7d, self._total_30d, self._opens_stat, self._clicks_stat):
            card = NeonCard(glow_color=theme.BG_CARD)
            card.content_layout().addWidget(w)
            stats_row.addWidget(card)
        layout.addLayout(stats_row)

        # Chart
        chart_card = NeonCard(glow_color=theme.BG_CARD, title="DAILY USAGE (30 DAYS)")
        self._chart = BarChartWidget()
        chart_card.content_layout().addWidget(self._chart)
        layout.addWidget(chart_card)

        # Category
        cat_row = QHBoxLayout()
        cat_label = QLabel("Category:")
        cat_label.setStyleSheet(f"color: {theme.TEXT_DIM}; background: transparent;")
        cat_row.addWidget(cat_label)
        from PySide6.QtWidgets import QComboBox
        self._category = QComboBox()
        self._category.addItems(["None", "Work", "Study", "Games", "Social", "Entertainment", "Tools"])
        self._category.currentTextChanged.connect(self._on_category_change)
        cat_row.addWidget(self._category)
        cat_row.addStretch()
        layout.addLayout(cat_row)

        # Rewards toggle
        rewards_card = NeonCard(glow_color=theme.BG_CARD, title="REWARDS")
        rewards_layout = rewards_card.content_layout()
        
        self._rewards_check = QCheckBox("Enable rewards for this app")
        self._rewards_check.setStyleSheet(f"color: {theme.TEXT}; font-size: 13px;")
        self._rewards_check.stateChanged.connect(self._on_rewards_toggle)
        rewards_layout.addWidget(self._rewards_check)
        
        rewards_info = QLabel("When enabled, time spent in this app will generate XP and resources.")
        rewards_info.setWordWrap(True)
        rewards_info.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px; background: transparent;")
        rewards_layout.addWidget(rewards_info)
        
        layout.addWidget(rewards_card)

        layout.addStretch()

    def load_app(self, app_id: int):
        self._app_id = app_id
        app = queries.get_app(app_id)
        if not app:
            return

        self._title.setText(app.get("display_name") or app["exe_name"])

        # Favorite button
        is_fav = bool(app.get("is_favorite"))
        self._fav_btn.setText("★ Favorited" if is_fav else "☆ Favorite")
        self._fav_btn.setStyleSheet(
            f"color: {theme.YELLOW};" if is_fav else ""
        )

        # Category
        cat = app.get("category") or "None"
        idx = self._category.findText(cat)
        if idx >= 0:
            self._category.blockSignals(True)
            self._category.setCurrentIndex(idx)
            self._category.blockSignals(False)
        
        # Rewards enabled
        from ...rewards import rules as reward_rules
        reward_rules.ensure_app_rules(app_id)
        enabled = reward_rules.app_rewards_enabled(app_id)
        self._rewards_check.blockSignals(True)
        self._rewards_check.setChecked(enabled)
        self._rewards_check.blockSignals(False)

        # Stats
        hist_30 = queries.app_daily_history(app_id, days=30)
        hist_7 = [h for h in hist_30 if h["day"] >= (date.today() - timedelta(days=7)).isoformat()]

        total_7 = sum(h.get("focused_ms", 0) for h in hist_7)
        total_30 = sum(h.get("focused_ms", 0) for h in hist_30)
        opens_7 = sum(h.get("opens_count", 0) for h in hist_7)
        clicks_7 = sum(h.get("clicks_count", 0) for h in hist_7)

        self._total_7d.set_value(theme.format_ms(total_7))
        self._total_30d.set_value(theme.format_ms(total_30))
        self._opens_stat.set_value(str(opens_7))
        self._clicks_stat.set_value(str(clicks_7))

        # Chart
        chart_data = [(h["day"], h.get("focused_ms", 0)) for h in hist_30]
        self._chart.set_data(chart_data)

    def _toggle_fav(self):
        if self._app_id is None:
            return
        app = queries.get_app(self._app_id)
        if not app:
            return
        new_fav = not bool(app.get("is_favorite"))
        queries.set_favorite(self._app_id, new_fav)
        self.load_app(self._app_id)

    def _on_category_change(self, text):
        if self._app_id is None:
            return
        queries.set_category(self._app_id, text if text != "None" else None)
    
    def _on_rewards_toggle(self, state):
        if self._app_id is None:
            return
        from ...rewards import rules as reward_rules
        reward_rules.enable_app_rewards(self._app_id, bool(state))
