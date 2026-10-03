"""Rewards: level progress, pending rewards, earning apps and how milestones work."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QProgressBar, QVBoxLayout, QWidget

from ...data import queries
from ...game import economy
from ...game import state as game_state
from ...rewards import engine as rewards
from ...rewards import rules
from .. import fmt
from ..signals import bus
from ..widgets.components import (
    AppAvatar,
    Card,
    EmptyState,
    Page,
    PageHeader,
    button,
    clear_layout,
    icon_label,
    label,
)

METRIC_TEXT = {"focused_ms": "focused", "opens_count": "launches", "clicks_count": "clicks"}


class RewardsView(Page):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx

        self.header = PageHeader("Rewards", "Time in the apps you choose earns XP and resources for your village.")
        self.claim_all = button("Claim all", kind="primary", icon="sparkles", on_click=self._claim_all)
        self.header.actions.addWidget(self.claim_all)
        self.add(self.header)

        self.profile = Card(padding=20)
        top = QHBoxLayout()
        top.setSpacing(12)
        self.crown = icon_label("crown", "gold", 22)
        top.addWidget(self.crown)
        self.level = label("", "value")
        top.addWidget(self.level)
        top.addStretch(1)
        self.stats = QHBoxLayout()
        self.stats.setSpacing(22)
        self.stat_values = {}
        for key, caption, icon, tone in (
            ("xp", "Total XP", "zap", "accent"),
            ("credits", "Credits", "coins", "gold"),
            ("streak", "Streak", "flame", "gold"),
        ):
            box = QHBoxLayout()
            box.setSpacing(8)
            box.addWidget(icon_label(icon, tone, 18))
            col = QVBoxLayout()
            col.setSpacing(0)
            value = label("–")
            value.setStyleSheet("font-weight: 700; font-size: 16px;")
            col.addWidget(value)
            col.addWidget(label(caption, "caption"))
            box.addLayout(col)
            self.stats.addLayout(box)
            self.stat_values[key] = value
        top.addLayout(self.stats)
        self.profile.body.addLayout(top)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.profile.body.addWidget(self.progress)
        self.progress_text = label("", "caption")
        self.profile.body.addWidget(self.progress_text)
        self.add(self.profile)

        cols = QHBoxLayout()
        cols.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(14)
        self.pending = Card("Pending rewards")
        self.pending_list = QVBoxLayout()
        self.pending_list.setSpacing(2)
        self.pending.body.addLayout(self.pending_list)
        left.addWidget(self.pending)

        self.earning = Card("Earning apps", "Progress toward each app's next milestone today")
        self.earning_list = QVBoxLayout()
        self.earning_list.setSpacing(4)
        self.earning.body.addLayout(self.earning_list)
        add_row = QHBoxLayout()
        self.add_combo = QComboBox()
        self.add_combo.setAccessibleName("App to add")
        self.add_combo.setMinimumWidth(200)
        add_row.addWidget(self.add_combo, 1)
        self.add_btn = button("Add app", icon="plus", on_click=self._add_app)
        add_row.addWidget(self.add_btn)
        self.earning.body.addLayout(add_row)
        left.addWidget(self.earning)
        left.addStretch(1)
        cols.addLayout(left, 3)

        self.rules_card = Card("How it works")
        self._build_rules(self.rules_card)
        cols.addWidget(self.rules_card, 2, Qt.AlignmentFlag.AlignTop)
        self.add(cols)
        self.layout_.addStretch(1)

        bus.rewards_changed.connect(lambda: self.isVisible() and self.refresh())
        bus.data_changed.connect(lambda: self.isVisible() and self.refresh())

    def _build_rules(self, card: Card) -> None:
        card.body.addWidget(
            label(
                "Each earning app pays out when today's focused time crosses a milestone. "
                "Repeating milestones pay again every time the amount is reached.",
                "dim",
                wrap=True,
            )
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        row = 0
        for metric, threshold, reward, repeat in rules.DEFAULT_RULES:
            if metric != "focused_ms":
                continue
            grid.addWidget(
                label(
                    f"Every {fmt.duration(threshold, short=True)}" if repeat else fmt.duration(threshold, short=True),
                    "muted",
                ),
                row,
                0,
            )
            grid.addWidget(label(fmt.reward(reward, ", ")), row, 1)
            row += 1
        card.body.addLayout(grid)
        card.body.addWidget(label("STREAKS", "section"))
        card.body.addWidget(
            label(
                "Spend 30 minutes in favorite apps each day to grow a streak. Milestone days pay a bonus.",
                "dim",
                wrap=True,
            )
        )
        streaks = QGridLayout()
        streaks.setHorizontalSpacing(12)
        streaks.setVerticalSpacing(6)
        for i, (days, reward) in enumerate(economy.STREAK_REWARDS.items()):
            streaks.addWidget(label(f"{days} days", "muted"), i, 0)
            streaks.addWidget(label(fmt.reward(reward, ", ")), i, 1)
        card.body.addLayout(streaks)
        card.body.addWidget(
            label(
                f"Every {economy.XP_PER_LEVEL} XP is a level. Each new level pays "
                f"{economy.CREDITS_PER_LEVEL} credits per level number, spendable at the "
                "village market.",
                "caption",
                wrap=True,
            )
        )

    # ------------------------------------------------------------------

    def refresh(self) -> None:
        rewards.evaluate_recent()
        profile = rewards.get_profile()
        bonuses = game_state.get_bonuses()
        self.crown.setVisible(bonuses["has_monument"])
        self.crown.setToolTip("Monument built")
        self.level.setText(f"Level {profile['level']}")
        into, need = economy.level_progress(profile["xp"])
        self.progress.setMaximum(need)
        self.progress.setValue(into)
        self.progress_text.setText(f"{into} / {need} XP to level {profile['level'] + 1}")
        self.stat_values["xp"].setText(fmt.count(profile["xp"]))
        self.stat_values["credits"].setText(fmt.count(profile["credits"]))
        streak = profile["streak"]
        self.stat_values["streak"].setText(f"{streak} day{'s' if streak != 1 else ''}")

        groups = rewards.unclaimed_by_app()
        self.claim_all.setEnabled(bool(groups))
        total = sum(len(g["event_ids"]) for g in groups)
        self.pending.title_label.setText(f"Pending rewards ({total})" if total else "Pending rewards")
        clear_layout(self.pending_list)
        if not groups:
            self.pending_list.addWidget(
                EmptyState("gift", "Nothing to claim", "New rewards show up here as earning apps reach milestones.")
            )
        for g in groups:
            self.pending_list.addWidget(self._pending_row(g))

        clear_layout(self.earning_list)
        milestones = rewards.next_milestones()
        if not milestones:
            self.earning_list.addWidget(
                EmptyState(
                    "zap", "No apps are earning yet", "Pick an app below, or turn on Earn rewards from any app's page."
                )
            )
        for item in milestones:
            self.earning_list.addWidget(self._earning_row(item))

        earning = rules.earning_app_ids()
        self.add_combo.clear()
        for app in queries.top_apps(queries.days_ago(29), queries.today_str(), limit=None):
            if app["app_id"] not in earning:
                self.add_combo.addItem(app["name"], app["app_id"])
        self.add_combo.setEnabled(self.add_combo.count() > 0)
        self.add_btn.setEnabled(self.add_combo.count() > 0)
        if not self.add_combo.count():
            self.add_combo.addItem("All recent apps are earning")

    def _pending_row(self, group: dict) -> QWidget:
        row = QWidget()
        row.setProperty("row", True)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(6, 6, 4, 6)
        lay.setSpacing(12)
        lay.addWidget(AppAvatar(group["name"], None, 30))
        text = QVBoxLayout()
        text.setSpacing(0)
        name = label(group["name"])
        name.setStyleSheet("font-weight: 600;")
        text.addWidget(name)
        n = len(group["event_ids"])
        text.addWidget(label(f"{n} milestone{'s' if n != 1 else ''}", "caption"))
        lay.addLayout(text, 1)
        lay.addWidget(label(fmt.reward(group["reward"]), "accent"))
        lay.addWidget(button("Claim", on_click=lambda ids=group["event_ids"]: self._claim(ids)))
        return row

    def _earning_row(self, item: dict) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(12)
        lay.addWidget(AppAvatar(item["name"], item.get("icon_path"), 28))
        col = QVBoxLayout()
        col.setSpacing(4)
        top = QHBoxLayout()
        name = label(item["name"])
        name.setStyleSheet("font-weight: 600;")
        top.addWidget(name)
        top.addStretch(1)
        nxt = item["next"]
        if nxt:
            top.addWidget(
                label(
                    f"{fmt.duration(item['focused_ms'], short=True)} / {fmt.duration(nxt['target_ms'], short=True)}",
                    "caption",
                )
            )
        col.addLayout(top)
        bar = QProgressBar()
        bar.setTextVisible(False)
        bar.setMaximum(1000)
        if nxt:
            bar.setValue(int(1000 * item["focused_ms"] / max(1, nxt["target_ms"])))
            col.addWidget(bar)
            col.addWidget(label(f"Next: {fmt.reward(nxt['reward'], ', ')}", "caption"))
        else:
            bar.setValue(1000)
            col.addWidget(bar)
            col.addWidget(label("All milestones reached today", "caption"))
        lay.addLayout(col, 1)
        remove = button(
            "",
            kind="ghost",
            icon="x",
            tooltip=f"Stop earning rewards for {item['name']}",
            on_click=lambda: self._remove_app(item["app_id"], item["name"]),
        )
        lay.addWidget(remove, 0, Qt.AlignmentFlag.AlignTop)
        return row

    # ------------------------------------------------------------------

    def _claim(self, event_ids: list[int]) -> None:
        self._report(rewards.claim_many(event_ids))

    def _claim_all(self) -> None:
        self._report(rewards.claim_many())

    def _report(self, applied: dict) -> None:
        bus.rewards_changed.emit()
        self.refresh()
        if applied:
            msg = "Claimed " + fmt.reward({k: v for k, v in applied.items() if k != "level_up"}, ", ")
            if applied.get("level_up"):
                msg += f". Level {applied['level_up']} reached!"
            self.ctx.toast(msg)

    def _add_app(self) -> None:
        app_id = self.add_combo.currentData()
        if app_id is None:
            return
        rules.enable_app_rewards(app_id, True)
        self.ctx.toast(f"{self.add_combo.currentText()} now earns rewards")
        bus.rewards_changed.emit()
        self.refresh()

    def _remove_app(self, app_id: int, name: str) -> None:
        rules.enable_app_rewards(app_id, False)
        bus.rewards_changed.emit()
        self.refresh()

        def undo():
            rules.enable_app_rewards(app_id, True)
            bus.rewards_changed.emit()
            self.refresh()

        self.ctx.toast(f"{name} no longer earns rewards", "info", "Undo", undo)
