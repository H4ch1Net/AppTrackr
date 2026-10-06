"""Village: the harvest your focus produced, production rates, buildings and the market."""

from __future__ import annotations

import time
from datetime import date

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QProgressBar, QVBoxLayout, QWidget

from ...game import economy
from ...game import state as game_state
from ...rewards import engine as rewards
from .. import fmt, fonts, icons, motion, theme
from ..signals import bus
from ..widgets.components import (
    PAGE_MARGIN,
    Card,
    MetricGrid,
    Page,
    PageHeader,
    StatTile,
    animate_progress,
    button,
    clear_layout,
    eyebrow,
    icon_label,
    label,
    set_role,
)

BUILDING_ICONS = {
    "lumberyard": "tree-pine",
    "quarry": "mountain",
    "farm": "wheat",
    "mine": "cog",
    "workshop": "hammer",
    "storage": "warehouse",
    "house": "house",
    "lab": "flask-conical",
    "tavern": "beer",
    "monument": "landmark",
}
RESOURCE_ICONS = {"wood": "tree-pine", "stone": "mountain", "metal": "cog", "food": "wheat", "blueprints": "scroll"}


class BlueprintTile(QWidget):
    """Building glyph on a drafting grid, like a plan on blueprint paper.

    The glyph takes the accent only when the building can be built right now.
    """

    def __init__(self, icon: str, state: str = "idle", size: int = 40, parent=None):
        super().__init__(parent)
        self._icon, self._state = icon, state  # "locked", "idle" or "ready"
        self.setFixedSize(size, size)

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(t.border_strong), 1))
        p.setBrush(QColor(t.surface_alt))
        p.drawRoundedRect(r, 4, 4)
        p.setPen(QPen(QColor(t.border), 1))
        step = self.width() / 5
        for i in range(1, 5):
            p.drawLine(QPointF(i * step, 2), QPointF(i * step, self.height() - 2))
            p.drawLine(QPointF(2, i * step), QPointF(self.width() - 2, i * step))
        color = {"locked": t.text_muted, "ready": t.accent_text}.get(self._state, t.text_dim)
        pm = icons.pixmap(self._icon, color, 22)
        p.drawPixmap(int((self.width() - 22) / 2), int((self.height() - 22) / 2), pm)


class LevelPips(QWidget):
    """Row of segments showing a building's level out of its maximum."""

    def __init__(self, level: int, maximum: int, previous: int | None = None, parent=None):
        super().__init__(parent)
        self._target, self._max = level, maximum
        self._level = float(level if previous is None else previous)
        self.setFixedHeight(6)
        self.setMinimumWidth(40)
        self.setToolTip(f"Level {level} of {maximum}")

    def showEvent(self, event):
        super().showEvent(event)
        if self._level != self._target:
            motion.tween(
                self, self._level, float(self._target), motion.SLOWER, self._set_level, motion.DECELERATE, key="pips"
            )

    def _set_level(self, value: float) -> None:
        self._level = value
        self.update()

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        if self._max > 12:  # long ladders read better as one bar
            p.setBrush(QColor(t.track))
            p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 3, 3)
            p.setBrush(QColor(t.text_dim))
            p.drawRoundedRect(QRectF(0, 0, self.width() * min(1.0, self._level / self._max), self.height()), 3, 3)
            return
        gap = 4
        w = (self.width() - gap * (self._max - 1)) / self._max
        for i in range(self._max):
            x = i * (w + gap)
            p.setBrush(QColor(t.track))
            p.drawRoundedRect(QRectF(x, 0, w, self.height()), 3, 3)
            fill = min(1.0, max(0.0, self._level - i))  # partially filled while animating
            if fill > 0:
                p.setBrush(QColor(t.text_dim))
                p.drawRoundedRect(QRectF(x, 0, w * fill, self.height()), 3, 3)


class VillageView(Page):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx

        self.header = PageHeader(
            "Village", "Your village works while you focus. Collect what it made and build it up.", kicker="Progress"
        )
        self.collect_btn = button("Collect", kind="primary", icon="sparkles", on_click=self._collect)
        self.header.actions.addWidget(self.collect_btn)
        self.add(self.header)

        self.t_level = StatTile("Player level", framed=False)
        self.t_villagers = StatTile("Villagers", framed=False)
        self.t_credits = StatTile("Credits", framed=False)
        self.t_bonus = StatTile("Production bonus", framed=False)
        self.add(MetricGrid([self.t_level, self.t_villagers, self.t_credits, self.t_bonus], columns=4))

        top = self.stack_when_narrow(QHBoxLayout())
        top.setSpacing(16)
        self.harvest_card = Card("Harvest", "–", index=1)
        self.harvest_grid = QGridLayout()
        self.harvest_grid.setHorizontalSpacing(18)
        self.harvest_grid.setVerticalSpacing(8)
        self.harvest_card.body.addLayout(self.harvest_grid)
        self.harvest_note = label("", "caption", wrap=True)
        self.harvest_card.body.addWidget(self.harvest_note)
        self.harvest_card.body.addStretch(1)
        top.addWidget(self.harvest_card, 3)
        self.production = Card("Production", "Per hour of focus at ×1. Flow multiplies it up to ×3.", index=2)
        self.prod_grid = QGridLayout()
        self.prod_grid.setHorizontalSpacing(12)
        self.prod_grid.setVerticalSpacing(6)
        self.production.body.addLayout(self.prod_grid)
        self.production.body.addStretch(1)
        top.addWidget(self.production, 2)
        self.add(top)

        row = self.stack_when_narrow(QHBoxLayout())
        row.setSpacing(16)
        self.inventory = Card("Inventory", index=3)
        self.inv_grid = QGridLayout()
        self.inv_grid.setHorizontalSpacing(12)
        self.inv_grid.setVerticalSpacing(10)
        self.inventory.body.addLayout(self.inv_grid)
        self.inventory.body.addStretch(1)
        row.addWidget(self.inventory, 3)

        self.market = Card("Market", "Trade credits for resources", index=4)
        self.market_grid = QGridLayout()
        self.market_grid.setSpacing(8)
        self.market.body.addLayout(self.market_grid)
        row.addWidget(self.market, 2)
        self.add(row)

        self.add(eyebrow("Buildings", 5))
        self.buildings = QGridLayout()
        self.buildings.setSpacing(16)
        self.add(self.buildings)
        self.layout_.addStretch(1)

        self._amounts: dict[str, int] = {}
        self._levels: dict[str, int] = {}
        self._cards: dict[str, Card] = {}
        self._columns = 0
        self._just_built: str | None = None
        self._ticks = 0
        bus.rewards_changed.connect(lambda: self.isVisible() and self.refresh())

    def refresh(self) -> None:
        village = game_state.get_village()
        profile = rewards.get_profile()
        bonuses = game_state.get_bonuses()
        cap = bonuses["resource_cap"]

        into, need = economy.level_progress(profile["xp"])
        self.t_level.set_number(profile["level"], _count, f"{need - into} XP to next level")
        self.t_villagers.set_number(village.get("villagers", 0), _count, "One per house level")
        self.t_credits.set_number(profile["credits"], lambda v: fmt.count(int(round(v))), "From levels and chests")
        extras = [f"+{bonuses['xp_bonus_pct']}% XP" if bonuses["xp_bonus_pct"] else ""]
        extras.append(f"flow grace {int(bonuses['grace_sec'] // 60)} min")
        self.t_bonus.set(f"+{bonuses['production_pct']}%", ", ".join(e for e in extras if e))
        self._fill_harvest(village)
        self._fill_production(village)

        clear_layout(self.inv_grid)
        inv = village["inventory"]
        for i, res in enumerate(economy.RESOURCES):
            r, c = i, 0
            cell = QVBoxLayout()
            cell.setContentsMargins(0, 0, 0, 0)
            cell.setSpacing(4)
            top = QHBoxLayout()
            top.setSpacing(6)
            top.addWidget(icon_label(RESOURCE_ICONS[res], "text_dim", 15))
            top.addWidget(label(res.title()))
            top.addStretch(1)
            amount = inv.get(res, 0)
            top.addWidget(label(f"{amount} / {cap}", "warning" if amount >= cap else "muted"))
            cell.addLayout(top)
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setMaximum(cap)
            animate_progress(bar, self._amounts.get(res, 0), min(cap, amount))
            self._amounts[res] = min(cap, amount)
            if amount >= cap:
                bar.setProperty("tone", "gold")
            cell.addWidget(bar)
            host = QWidget()
            host.setLayout(cell)
            self.inv_grid.addWidget(host, r, c)

        clear_layout(self.market_grid)
        for i, (res, (amount, price)) in enumerate(economy.MARKET.items()):
            self.market_grid.addWidget(icon_label(RESOURCE_ICONS[res], "text_dim", 15), i, 0)
            self.market_grid.addWidget(label(fmt.amount(amount, res)), i, 1)
            btn = button(f"{price} credits", on_click=lambda r=res: self._buy(r))
            btn.setEnabled(profile["credits"] >= price and inv.get(res, 0) < cap)
            if inv.get(res, 0) >= cap:
                btn.setToolTip("Storage full")
            self.market_grid.addWidget(btn, i, 2)
        self.market_grid.setColumnStretch(1, 1)

        clear_layout(self.buildings)
        self._cards = {}
        for name in game_state.BUILDINGS:
            self._cards[name] = self._building_card(name, village, profile["level"])
        self._columns = 0
        self._place_buildings()
        self._levels = {name: game_state.building_level(village, name) for name in game_state.BUILDINGS}
        if self._just_built in self._cards:
            card = self._cards[self._just_built]

            def celebrate() -> None:  # after layout, so the card has its final geometry
                motion.flash(card)
                motion.burst(card.findChild(BlueprintTile), radius=30)

            QTimer.singleShot(0, card, celebrate)
        self._just_built = None

    def tick(self) -> None:
        self._ticks += 1
        if self._ticks % 5 == 0:  # the harvest grows while you focus
            self._fill_harvest(game_state.get_village())

    def _fill_harvest(self, village: dict) -> None:
        crop = game_state.harvest(village=village)
        clear_layout(self.harvest_grid)
        rates = game_state.production_rates(village)
        items = [(res, crop["resources"].get(res, 0)) for res in economy.RESOURCES if res in rates]
        items = [item for item in items if item[1]] or items[:3]  # skip what has not made a whole unit yet
        items.append(("xp", crop["xp"]))
        for i, (res, amount) in enumerate(items):
            cell = QHBoxLayout()
            cell.setSpacing(8)
            cell.addWidget(icon_label(RESOURCE_ICONS.get(res, "sparkles"), "text_dim", 16))
            value = label(f"+{fmt.count(amount)}")
            value.setFont(fonts.sans(17, 600, tabular=True))
            cell.addWidget(value)
            cell.addWidget(label(fmt.amount(amount, res).split(" ", 1)[1], "caption"))
            cell.addStretch(1)
            host = QWidget()
            host.setLayout(cell)
            self.harvest_grid.addWidget(host, i // 3, i % 3)
        since = (
            fmt.time_of_day(crop["since"])
            if crop["since"] > time.time() - 86400
            else fmt.short_date(date.fromtimestamp(crop["since"]).isoformat())
        )
        if crop["focus_ms"]:
            self.harvest_card.set_caption(
                f"{fmt.duration(crop['focus_ms'], short=True)} of focus since {since}, "
                f"{fmt.count(int(crop['points']))} focus points"
            )
        else:
            self.harvest_card.set_caption(f"No focus since {since}. Work in a focus app and your village gets busy.")
        if crop["full"]:
            self.harvest_note.setText(
                "Storage is full for " + ", ".join(crop["full"]) + ". Collect, spend or build storage to keep the rest."
            )
        else:
            self.harvest_note.setText("")
        ready = any(crop["resources"].values()) or crop["xp"] > 0
        self.collect_btn.setEnabled(ready)
        self._harvest_ready = ready

    def _fill_production(self, village: dict) -> None:
        clear_layout(self.prod_grid)
        rates = game_state.production_rates(village)
        for i, res in enumerate(economy.RESOURCES):
            if res not in rates:
                continue
            per_hour = rates[res] * 60
            self.prod_grid.addWidget(icon_label(RESOURCE_ICONS[res], "text_dim", 15), i, 0)
            self.prod_grid.addWidget(label(res.title()), i, 1)
            text = f"{per_hour:,.0f}" if per_hour >= 10 else f"{per_hour:.1f}"
            value = label(text)
            value.setFont(fonts.sans(13, 600, tabular=True))
            self.prod_grid.addWidget(value, i, 2, Qt.AlignmentFlag.AlignRight)
        xp_hour = 60 * economy.XP_PER_POINT * (1 + game_state.get_bonuses(village)["xp_bonus_pct"] / 100)
        row = len(economy.RESOURCES)
        self.prod_grid.addWidget(icon_label("sparkles", "text_dim", 15), row, 0)
        self.prod_grid.addWidget(label("XP"), row, 1)
        value = label(f"{xp_hour:.0f}")
        value.setFont(fonts.sans(13, 600, tabular=True))
        self.prod_grid.addWidget(value, row, 2, Qt.AlignmentFlag.AlignRight)
        self.prod_grid.setColumnStretch(1, 1)

    def _collect(self) -> None:
        applied = game_state.collect()
        gained = {k: v for k, v in applied.items() if k in economy.RESOURCES or k in ("xp", "credits")}
        motion.burst(self.collect_btn, radius=40, ticks=16)
        if applied.get("level_up"):
            msg = f"Level {applied['level_up']} reached! "
        else:
            msg = ""
        self.ctx.toast(msg + ("Collected " + fmt.reward(gained, ", ") if gained else "Nothing to collect yet"))
        bus.rewards_changed.emit()
        if not self.isVisible():
            self.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_buildings()

    def _place_buildings(self) -> None:
        """Lay building cards out in as many columns (up to 3) as fit the page."""
        cards = list(self._cards.values())
        if not cards:
            return
        spacing = self.buildings.horizontalSpacing()
        widest = max(c.minimumSizeHint().width() for c in cards)
        room = self.viewport().width() - 2 * PAGE_MARGIN
        columns = max(1, min(3, (room + spacing) // (widest + spacing)))
        if columns == self._columns:
            return
        self._columns = columns
        for card in cards:
            self.buildings.removeWidget(card)
        for i, card in enumerate(cards):
            self.buildings.addWidget(card, i // columns, i % columns)
        for c in range(3):
            self.buildings.setColumnStretch(c, 1 if c < columns else 0)

    def _building_card(self, name: str, village: dict, player_level: int) -> Card:
        spec = game_state.BUILDINGS[name]
        level = game_state.building_level(village, name)
        locked = player_level < spec["unlock_level"]
        maxed = level >= spec["max_level"]
        ok, reason = game_state.can_build(name)
        card = Card(padding=16, spacing=8)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(BlueprintTile(BUILDING_ICONS[name], "locked" if locked else ("ready" if ok else "idle")))
        title = label(name.title(), "heading")
        top.addWidget(title, 1)
        pill = label(
            "Locked" if locked else ("Max" if maxed else f"Lv {level}/{spec['max_level']}"),
            "pill",
        )
        top.addWidget(pill)
        card.body.addLayout(top)

        card.body.addWidget(LevelPips(level, spec["max_level"], self._levels.get(name)))

        card.body.addWidget(label(spec["desc"], "dim", wrap=True))
        effect = _effect(name, level, maxed, village)
        if effect:
            card.body.addWidget(label(effect, "caption", wrap=True))

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
        if ok:
            self._just_built = name
        bus.rewards_changed.emit()  # refreshes this page while it is visible
        if not self.isVisible():
            self.refresh()

    def _buy(self, resource: str) -> None:
        ok, msg = game_state.buy(resource)
        self.ctx.toast(msg, "success" if ok else "danger")
        bus.rewards_changed.emit()
        if not self.isVisible():
            self.refresh()


def _count(n: float) -> str:
    return str(int(round(n)))


def _effect(name: str, level: int, maxed: bool, village: dict) -> str:
    """What the building does now, and at the next level."""

    def at(lvl: int) -> dict:
        trial = {**village, "buildings": {**village.get("buildings", {}), name: {"level": lvl}}}
        if name == "house":
            trial["villagers"] = village.get("villagers", 0) + (lvl - level)
        return trial

    def show(lvl: int) -> str:
        v = at(lvl)
        for res, (building, _rate, _free) in economy.PRODUCTION.items():
            if building == name:
                per_hour = game_state.production_rates(v).get(res, 0) * 60
                return f"{per_hour:,.0f} {res}/h" if per_hour >= 10 else f"{per_hour:.1f} {res}/h"
        bonuses = game_state.get_bonuses(v)
        return {
            "storage": f"holds {fmt.count(game_state.resource_cap(v))}",
            "house": f"+{bonuses['production_pct']}% production",
            "workshop": f"+{bonuses['xp_bonus_pct']}% XP",
            "tavern": f"{int(bonuses['grace_sec'] // 60)} min grace",
            "monument": f"+{economy.MONUMENT_PCT}% production and a crown",
        }.get(name, "")

    now = show(level)
    if name == "monument":
        return "Standing" if level else f"Adds {now}"
    if maxed or not now:
        return f"Now {now}" if now else ""
    return f"Now {now}, next {show(level + 1)}"
