"""Apps list view – sort by most/least used, most opened, most clicked."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QScrollArea, QTabBar, QPushButton,
)

from .. import theme
from ..widgets.components import AppRow
from ...data import queries


class AppsView(QWidget):
    """Apps list with sort tabs, search, and filter."""

    app_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_tab = 0
        self._search_text = ""
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Apps")
        header.setObjectName("heading")
        layout.addWidget(header)

        # Tabs
        tab_row = QHBoxLayout()
        self._tabs = QTabBar()
        self._tabs.addTab("Most Used")
        self._tabs.addTab("Least Used")
        self._tabs.addTab("Most Opened")
        self._tabs.addTab("Most Clicked")
        self._tabs.addTab("Favorites")
        self._tabs.currentChanged.connect(self._on_tab_change)
        tab_row.addWidget(self._tabs)
        tab_row.addStretch()
        layout.addLayout(tab_row)

        # Search + period
        filter_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search apps...")
        self._search.textChanged.connect(self._on_search)
        filter_row.addWidget(self._search, stretch=1)

        self._period = QComboBox()
        self._period.addItems(["7 Days", "30 Days", "90 Days", "All Time"])
        self._period.currentIndexChanged.connect(lambda _: self.refresh())
        filter_row.addWidget(self._period)
        layout.addLayout(filter_row)

        # Apps list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_container)
        layout.addWidget(scroll, stretch=1)

    def refresh(self):
        days_map = {0: 7, 1: 30, 2: 90, 3: 3650}
        days = days_map.get(self._period.currentIndex(), 7)

        tab = self._tabs.currentIndex()
        if tab == 0:
            apps = queries.most_used(days=days)
        elif tab == 1:
            apps = queries.least_used(days=days)
        elif tab == 2:
            apps = queries.most_opened(days=days)
        elif tab == 3:
            apps = queries.most_clicked(days=days)
        elif tab == 4:
            all_apps = queries.most_used(days=days, limit=200)
            apps = [a for a in all_apps if a.get("is_favorite")]
        else:
            apps = []

        # Filter by search
        if self._search_text:
            q = self._search_text.lower()
            apps = [a for a in apps if q in (a.get("display_name") or a["exe_name"]).lower()]

        self._rebuild_list(apps)

    def _rebuild_list(self, apps: list[dict]):
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not apps:
            lbl = QLabel("No apps found")
            lbl.setStyleSheet(f"color: {theme.TEXT_MUTED}; padding: 20px; background: transparent;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._list_layout.insertWidget(0, lbl)
            return

        max_ms = max(a.get("focused_ms", 1) for a in apps) or 1
        for i, app in enumerate(apps):
            row = AppRow(
                app_id=app["app_id"],
                name=app.get("display_name") or app["exe_name"],
                value_ms=app.get("focused_ms", 0),
                max_ms=max_ms,
                is_favorite=bool(app.get("is_favorite")),
            )
            row.clicked.connect(self.app_selected.emit)
            self._list_layout.insertWidget(i, row)

    def _on_tab_change(self, idx):
        self._current_tab = idx
        self.refresh()

    def _on_search(self, text):
        self._search_text = text
        self.refresh()
