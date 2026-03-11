"""Neon Village view – buildings, inventory, upgrades."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QGridLayout, QGraphicsDropShadowEffect,
)

from .. import theme
from ..widgets.components import NeonCard, StatValue
from ...game import state as game_state
from ...rewards import engine as reward_engine


class BuildingCard(QFrame):
    """Card for a single village building."""

    def __init__(self, name: str, spec: dict, current_level: int, parent=None):
        super().__init__(parent)
        self._name = name
        unlocked = current_level > 0

        border_color = theme.get_accent() if unlocked else theme.BORDER
        self.setStyleSheet(f"""
            QFrame {{
                background: {theme.BG_CARD};
                border: 1px solid {border_color};
                border-radius: 10px;
                padding: 12px;
                min-width: 180px;
            }}
        """)
        if unlocked:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(16)
            shadow.setColor(QColor(theme.get_accent()))
            shadow.setOffset(0, 0)
            self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Building icon + name
        icons = {"workshop": "🔨", "storage": "📦", "house": "🏠", "lab": "🔬", "tavern": "🍺", "monument": "🏛️"}
        icon = icons.get(name, "🏗️")
        title = QLabel(f"{icon}  {name.title()}")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {theme.TEXT}; background: transparent;")
        layout.addWidget(title)

        # Level
        level_lbl = QLabel(f"Level {current_level} / {spec['max_level']}")
        level_lbl.setStyleSheet(f"color: {theme.get_accent()}; font-weight: 600; background: transparent;")
        layout.addWidget(level_lbl)

        # Description
        desc = QLabel(spec["desc"])
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px; background: transparent;")
        layout.addWidget(desc)

        # Unlock level req
        req = QLabel(f"Unlock: Player Lvl {spec['unlock_level']}")
        req.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 10px; background: transparent;")
        layout.addWidget(req)

        # Build / upgrade button
        can, reason = game_state.can_build(name)
        self._build_btn = QPushButton("Build" if current_level == 0 else "Upgrade")
        self._build_btn.setObjectName("primary")
        self._build_btn.setEnabled(can)
        self._build_btn.setToolTip(reason if not can else "")
        self._build_btn.clicked.connect(self._do_build)
        layout.addWidget(self._build_btn)

    def _do_build(self):
        ok, msg = game_state.build_or_upgrade(self._name)
        if ok:
            # Refresh parent
            p = self.parent()
            while p and not isinstance(p, VillageView):
                p = p.parent()
            if p:
                p.refresh()


class VillageView(QWidget):
    """Neon Village – build, upgrade, manage your village."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("🏙️  Neon Village")
        header.setObjectName("heading")
        layout.addWidget(header)

        # Player info
        info_row = QHBoxLayout()
        self._level_stat = StatValue("1", "Village Level", theme.PURPLE)
        self._villagers_stat = StatValue("0", "Villagers", theme.BLUE)
        self._xp_stat = StatValue("0", "XP", theme.get_accent())

        for w in (self._level_stat, self._villagers_stat, self._xp_stat):
            card = NeonCard(glow_color=theme.BG_CARD)
            card.content_layout().addWidget(w)
            info_row.addWidget(card)
        layout.addLayout(info_row)

        # Inventory
        inv_card = NeonCard(glow_color=theme.BG_CARD, title="INVENTORY")
        self._inv_layout = QHBoxLayout()
        inv_card.content_layout().addLayout(self._inv_layout)
        layout.addWidget(inv_card)

        # Buildings grid
        buildings_label = QLabel("Buildings")
        buildings_label.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {theme.TEXT}; background: transparent;")
        layout.addWidget(buildings_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._buildings_container = QWidget()
        self._buildings_container.setStyleSheet("background: transparent;")
        self._buildings_grid = QGridLayout(self._buildings_container)
        self._buildings_grid.setSpacing(12)
        scroll.setWidget(self._buildings_container)
        layout.addWidget(scroll, stretch=1)

    def refresh(self):
        village = game_state.get_village()
        profile = reward_engine.get_profile()

        # Stats
        self._level_stat.set_value(str(profile.get("level", 1)))
        self._villagers_stat.set_value(str(village.get("villagers", 0)))
        self._xp_stat.set_value(str(profile.get("xp", 0)))

        # Inventory
        while self._inv_layout.count():
            item = self._inv_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        inv = village.get("inventory", {})
        icons = {"wood": "🪵", "stone": "🪨", "metal": "⚙️", "food": "🍖", "blueprints": "📜"}
        for res, icon in icons.items():
            val = inv.get(res, 0)
            item = QLabel(f"{icon} {res.title()}: {val}")
            item.setStyleSheet(f"color: {theme.TEXT}; font-weight: 600; padding: 4px 12px; background: transparent;")
            self._inv_layout.addWidget(item)
        self._inv_layout.addStretch()

        # Buildings
        while self._buildings_grid.count():
            item = self._buildings_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        buildings = village.get("buildings", {})
        col = 0
        row = 0
        for name, spec in game_state.BUILDINGS.items():
            current_level = buildings.get(name, {}).get("level", 0)
            card = BuildingCard(name, spec, current_level)
            self._buildings_grid.addWidget(card, row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1
