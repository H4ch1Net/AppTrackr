"""Neon Village: inventory, market and buildings that boost future rewards."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QProgressBar, QVBoxLayout, QWidget

from ...game import economy
from ...game import state as game_state
from ...rewards import engine as rewards
from .. import fmt, theme
from ..signals import bus
from ..widgets.components import (
    Card,
    Page,
    PageHeader,
    StatTile,
    button,
    clear_layout,
    icon_label,
    label,
    set_role,
)

BUILDING_ICONS = {
    "workshop": "hammer",
    "storage": "warehouse",
    "house": "house",
    "lab": "flask-conical",
    "tavern": "beer",
    "monument": "landmark",
}
RESOURCE_ICONS = {"wood": "tree-pine", "stone": "mountain", "metal": "cog", "food": "wheat", "blueprints": "scroll"}


class LevelPips(QWidget):
    """Row of segments showing a building's level out of its maximum."""

    def __init__(self, level: int, maximum: int, parent=None):
        super().__init__(parent)
        self._level, self._max = level, maximum
        self.setFixedHeight(6)
        self.setMinimumWidth(40)
        self.setToolTip(f"Level {level} of {maximum}")

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        gap = 4
        w = (self.width() - gap * (self._max - 1)) / self._max
        for i in range(self._max):
            p.setBrush(QColor(t.accent if i < self._level else t.track))
            p.drawRoundedRect(QRectF(i * (w + gap), 0, w, self.height()), 3, 3)


class VillageView(Page):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx

        self.header = PageHeader("Neon Village", "Spend resources from rewards on buildings that boost future rewards.")
        self.add(self.header)

        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        self.t_level = StatTile("Player level", "zap")
        self.t_villagers = StatTile("Villagers", "house")
        self.t_credits = StatTile("Credits", "coins", tone="gold")
        self.t_bonus = StatTile("Active bonuses", "sparkles")
        for t in (self.t_level, self.t_villagers, self.t_credits, self.t_bonus):
            tiles.addWidget(t)
        self.add(tiles)

        row = QHBoxLayout()
        row.setSpacing(14)
        self.inventory = Card("Inventory")
        self.inv_grid = QGridLayout()
        self.inv_grid.setHorizontalSpacing(12)
        self.inv_grid.setVerticalSpacing(10)
        self.inventory.body.addLayout(self.inv_grid)
        self.inventory.body.addStretch(1)
        row.addWidget(self.inventory, 3)

        self.market = Card("Market", "Trade credits for resources")
        self.market_grid = QGridLayout()
        self.market_grid.setSpacing(8)
        self.market.body.addLayout(self.market_grid)
        row.addWidget(self.market, 2)
        self.add(row)

        self.add(label("Buildings", "heading"))
        self.buildings = QGridLayout()
        self.buildings.setSpacing(14)
        self.add(self.buildings)
        self.layout_.addStretch(1)

        bus.rewards_changed.connect(lambda: self.isVisible() and self.refresh())

    def refresh(self) -> None:
        village = game_state.get_village()
        profile = rewards.get_profile()
        bonuses = game_state.get_bonuses()
        cap = bonuses["resource_cap"]

        into, need = economy.level_progress(profile["xp"])
        self.t_level.set(str(profile["level"]), f"{need - into} XP to next level")
        self.t_villagers.set(str(village.get("villagers", 0)), "One per house level")
        self.t_credits.set(fmt.count(profile["credits"]), "Earned by leveling up")
        active = [
            f"+{bonuses['xp_bonus_pct']}% XP" if bonuses["xp_bonus_pct"] else "",
            f"+{bonuses['resource_bonus_pct']}% resources" if bonuses["resource_bonus_pct"] else "",
            f"+{bonuses['streak_bonus_pct']}% streak" if bonuses["streak_bonus_pct"] else "",
        ]
        active = [a for a in active if a]
        self.t_bonus.set(str(len(active)), ", ".join(active) or "Build to unlock bonuses")

        clear_layout(self.inv_grid)
        inv = village["inventory"]
        for i, res in enumerate(economy.RESOURCES):
            r, c = divmod(i, 2)
            cell = QVBoxLayout()
            cell.setContentsMargins(0, 0, 0, 0)
            cell.setSpacing(4)
            top = QHBoxLayout()
            top.setSpacing(6)
            top.addWidget(icon_label(RESOURCE_ICONS[res], "accent", 15))
            top.addWidget(label(res.title()))
            top.addStretch(1)
            amount = inv.get(res, 0)
            top.addWidget(label(f"{amount} / {cap}", "warning" if amount >= cap else "muted"))
            cell.addLayout(top)
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setMaximum(cap)
            bar.setValue(min(cap, amount))
            if amount >= cap:
                bar.setProperty("tone", "gold")
            cell.addWidget(bar)
            host = QWidget()
            host.setLayout(cell)
            self.inv_grid.addWidget(host, r, c)

        clear_layout(self.market_grid)
        for i, (res, (amount, price)) in enumerate(economy.MARKET.items()):
            self.market_grid.addWidget(icon_label(RESOURCE_ICONS[res], "text_dim", 15), i, 0)
            self.market_grid.addWidget(label(f"{amount} {res}"), i, 1)
            btn = button(f"{price} credits", on_click=lambda r=res: self._buy(r))
            btn.setEnabled(profile["credits"] >= price and inv.get(res, 0) < cap)
            if inv.get(res, 0) >= cap:
                btn.setToolTip("Storage full")
            self.market_grid.addWidget(btn, i, 2)
        self.market_grid.setColumnStretch(1, 1)

        clear_layout(self.buildings)
        for i, name in enumerate(game_state.BUILDINGS):
            self.buildings.addWidget(self._building_card(name, village, profile["level"]), i // 3, i % 3)
        for c in range(3):
            self.buildings.setColumnStretch(c, 1)

    def _building_card(self, name: str, village: dict, player_level: int) -> Card:
        spec = game_state.BUILDINGS[name]
        level = game_state.building_level(village, name)
        locked = player_level < spec["unlock_level"]
        maxed = level >= spec["max_level"]
        card = Card(padding=16, spacing=8)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(icon_label(BUILDING_ICONS[name], "text_muted" if locked else "accent", 22))
        title = label(name.title(), "heading")
        top.addWidget(title, 1)
        pill = label(
            "Locked" if locked else ("Max" if maxed else f"Lv {level}/{spec['max_level']}"),
            "pill" if locked or not level else "pillAccent",
        )
        top.addWidget(pill)
        card.body.addLayout(top)

        card.body.addWidget(LevelPips(level, spec["max_level"]))

        card.body.addWidget(label(spec["desc"], "dim", wrap=True))

        if locked:
            status = f"Unlocks at player level {spec['unlock_level']}"
            card.body.addWidget(label(status, "caption"))
        elif not maxed:
            cost = game_state.build_cost(name, level)
            inv = village["inventory"]
            parts = []
            for res, need in cost.items():
                color = "" if inv.get(res, 0) >= need else f" style='color:{theme.current().danger}'"
                parts.append(f"<span{color}>{need} {res}</span>")
            card.body.addWidget(label("Cost: " + ", ".join(parts), "caption", wrap=True))
        card.body.addStretch(1)

        ok, reason = game_state.can_build(name)
        btn = button(
            "Build" if level == 0 else ("Upgrade" if not maxed else "Fully upgraded"),
            icon="hammer" if ok else None,
            on_click=lambda: self._build(name),
        )
        btn.setEnabled(ok)
        if not ok and not maxed:
            btn.setToolTip(reason)
        card.body.addWidget(btn)
        if locked:
            set_role(title, "muted")
        return card

    def _build(self, name: str) -> None:
        ok, msg = game_state.build_or_upgrade(name)
        self.ctx.toast(msg, "success" if ok else "danger")
        bus.rewards_changed.emit()
        self.refresh()

    def _buy(self, resource: str) -> None:
        ok, msg = game_state.buy(resource)
        self.ctx.toast(msg, "success" if ok else "danger")
        self.refresh()
