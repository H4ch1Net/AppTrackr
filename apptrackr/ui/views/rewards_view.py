"""Rewards view – unclaimed rewards + rule editor."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QComboBox, QSpinBox, QGraphicsDropShadowEffect,
)
from PySide6.QtGui import QColor

from .. import theme
from ..widgets.components import NeonCard, StatValue
from ...rewards import engine as reward_engine
from ...rewards import rules as reward_rules
from ...data import queries


class RewardCard(QFrame):
    """A single unclaimed reward with glow + claim button."""

    claimed = Signal(int)

    def __init__(self, event: dict, parent=None):
        super().__init__(parent)
        self._event_id = event["event_id"]
        self.setStyleSheet(f"""
            QFrame {{
                background: {theme.BG_CARD};
                border: 1px solid {theme.PURPLE_DIM};
                border-radius: 10px;
                padding: 12px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(theme.PURPLE))
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)

        layout = QHBoxLayout(self)
        layout.setSpacing(12)

        # App name
        app_name = event.get("display_name") or event.get("exe_name", "?")
        name_lbl = QLabel(f"🎁  {app_name}")
        name_lbl.setStyleSheet(f"font-weight: 600; color: {theme.TEXT}; background: transparent;")
        layout.addWidget(name_lbl)

        # Reward details
        reward = json.loads(event["granted_json"]) if isinstance(event["granted_json"], str) else event["granted_json"]
        parts = []
        for k, v in reward.items():
            parts.append(f"+{v} {k}")
        detail = QLabel("  ".join(parts))
        detail.setStyleSheet(f"color: {theme.get_accent()}; font-weight: 600; background: transparent;")
        layout.addWidget(detail, stretch=1)

        # Claim button
        claim = QPushButton("✨ Claim")
        claim.setObjectName("primary")
        claim.clicked.connect(lambda: self.claimed.emit(self._event_id))
        layout.addWidget(claim)


class RewardsView(QWidget):
    """Rewards tab – claim pending rewards, view profile, manage rules."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Rewards")
        header.setObjectName("heading")
        layout.addWidget(header)

        # Profile stats
        stats_row = QHBoxLayout()
        self._xp_stat = StatValue("0", "XP", theme.get_accent())
        self._level_stat = StatValue("1", "Level", theme.PURPLE)
        self._streak_stat = StatValue("0", "Streak", theme.YELLOW)
        self._credits_stat = StatValue("0", "Credits", theme.PINK)

        for w in (self._xp_stat, self._level_stat, self._streak_stat, self._credits_stat):
            card = NeonCard(glow_color=theme.BG_CARD)
            card.content_layout().addWidget(w)
            stats_row.addWidget(card)
        layout.addLayout(stats_row)

        # Claim all
        btn_row = QHBoxLayout()
        self._claim_all_btn = QPushButton("✨ Claim All Rewards")
        self._claim_all_btn.setObjectName("primary")
        self._claim_all_btn.clicked.connect(self._claim_all)
        btn_row.addWidget(self._claim_all_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Unclaimed rewards
        unclaimed_label = QLabel("Pending Rewards")
        unclaimed_label.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {theme.TEXT}; background: transparent;")
        layout.addWidget(unclaimed_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._rewards_container = QWidget()
        self._rewards_container.setStyleSheet("background: transparent;")
        self._rewards_layout = QVBoxLayout(self._rewards_container)
        self._rewards_layout.setContentsMargins(0, 0, 0, 0)
        self._rewards_layout.setSpacing(8)
        self._rewards_layout.addStretch()
        scroll.setWidget(self._rewards_container)
        layout.addWidget(scroll, stretch=1)

    def refresh(self):
        # Profile
        profile = reward_engine.get_profile()
        self._xp_stat.set_value(str(profile.get("xp", 0)))
        self._level_stat.set_value(str(profile.get("level", 1)))
        self._streak_stat.set_value(str(profile.get("streak_days", 0)))
        self._credits_stat.set_value(str(profile.get("credits", 0)))

        # Evaluate new rewards first
        reward_engine.evaluate()

        # Unclaimed
        unclaimed = reward_engine.unclaimed_rewards()

        while self._rewards_layout.count() > 1:
            item = self._rewards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not unclaimed:
            lbl = QLabel("No pending rewards — keep tracking!")
            lbl.setStyleSheet(f"color: {theme.TEXT_MUTED}; padding: 20px; background: transparent;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._rewards_layout.insertWidget(0, lbl)
            return

        for i, evt in enumerate(unclaimed):
            card = RewardCard(evt)
            card.claimed.connect(self._on_claim)
            self._rewards_layout.insertWidget(i, card)

    def _on_claim(self, event_id: int):
        reward_engine.claim_reward(event_id)
        self.refresh()

    def _claim_all(self):
        reward_engine.claim_all()
        self.refresh()
