"""Rewards: level progress, pending rewards, earning apps and how milestones work."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QProgressBar, QPushButton, QVBoxLayout, QWidget

from ...data import queries
from ...game import economy
from ...game import state as game_state
from ...rewards import engine as rewards
from ...rewards import rules
from .. import fmt, fonts, motion, theme
from ..signals import bus
from ..widgets.components import (
    AppAvatar,
    Card,
    EmptyState,
    Page,
    PageHeader,
    animate_progress,
    button,
    clear_layout,
    count_to,
    eyebrow,
    icon_label,
    label,
    set_role,
    vdivider,
)
from ..widgets.rolling import RollingLabel

METRIC_TEXT = {"focused_ms": "focused", "opens_count": "launches", "clicks_count": "clicks"}


class RewardsView(Page):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx

        self.header = PageHeader(
            "Rewards", "Time in the apps you choose earns XP and resources for your village.", kicker="Progress"
        )
        self.claim_all = button("Claim all", kind="primary", icon="sparkles", on_click=self._claim_all)
        self.header.actions.addWidget(self.claim_all)
        self.add(self.header)

        self.profile = Card(padding=20)
        top = QHBoxLayout()
        top.setSpacing(28)
        level_col = QVBoxLayout()
        level_col.setSpacing(2)
        cap = QHBoxLayout()
        cap.setSpacing(6)
        cap.addWidget(eyebrow("Level"))
        self.crown = icon_label("crown", "gold", 14)
        cap.addWidget(self.crown)
        cap.addStretch(1)
        level_col.addLayout(cap)
        self.level = RollingLabel("")
        set_role(self.level, "hero")
        level_col.addWidget(self.level)
        top.addLayout(level_col)
        progress_col = QVBoxLayout()
        progress_col.setSpacing(8)
        progress_col.addStretch(1)
        self.progress_text = label("", "caption")
        progress_col.addWidget(self.progress_text)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setProperty("tone", "accent")
        progress_col.addWidget(self.progress)
        progress_col.addSpacing(10)
        top.addLayout(progress_col, 1)
        self.stat_values = {}
        for key, caption in (("xp", "Total XP"), ("credits", "Credits"), ("streak", "Streak")):
            top.addWidget(vdivider())
            col = QVBoxLayout()
            col.setSpacing(4)
            col.addWidget(eyebrow(caption))
            value = RollingLabel("–")
            value.setFont(fonts.sans(20, 600, tabular=True))
            col.addWidget(value)
            col.addStretch(1)
            top.addLayout(col)
            self.stat_values[key] = value
        self.profile.body.addLayout(top)
        self.add(self.profile)

        cols = self.stack_when_narrow(QHBoxLayout())
        cols.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(16)
        self.pending = Card("Pending rewards", index=1)
        self.pending_list = QVBoxLayout()
        self.pending_list.setSpacing(2)
        self.pending.body.addLayout(self.pending_list)
        left.addWidget(self.pending)

        self.earning = Card("Earning apps", "Progress toward each app's next milestone today", index=2)
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

        self.rules_card = Card("How it works", index=3)
        self._build_rules(self.rules_card)
        cols.addWidget(self.rules_card, 2, Qt.AlignmentFlag.AlignTop)
        self.add(cols)
        self.layout_.addStretch(1)

        self._shown: dict = {}
        self._progress: dict[int, int] = {}
        self._pending_rows: list[QWidget] = []
        self._added_app: int | None = None
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
        card.body.addWidget(label("STREAKS", "eyebrow"))
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
        self.level.roll_to(str(profile["level"]))
        into, need = economy.level_progress(profile["xp"])
        self.progress.setMaximum(need)
        self.progress_text.setText(f"{into} / {need} XP to level {profile['level'] + 1}")
        self._animate_profile(profile, into)
        streak = profile["streak"]
        self.stat_values["streak"].roll_to(f"{streak} day{'s' if streak != 1 else ''}")

        groups = rewards.unclaimed_by_app()
        self.claim_all.setEnabled(bool(groups))
        total = sum(len(g["event_ids"]) for g in groups)
        self.pending.set_title(f"Pending rewards · {total}" if total else "Pending rewards")
        clear_layout(self.pending_list)
        self._pending_rows = []
        if not groups:
            self.pending_list.addWidget(
                EmptyState("gift", "Nothing to claim", "New rewards show up here as earning apps reach milestones.")
            )
        for g in groups:
            row = self._pending_row(g)
            self._pending_rows.append(row)
            self.pending_list.addWidget(row)

        clear_layout(self.earning_list)
        milestones = rewards.next_milestones()
        if not milestones:
            self.earning_list.addWidget(
                EmptyState(
                    "zap", "No apps are earning yet", "Pick an app below, or turn on Earn rewards from any app's page."
                )
            )
        progress = {}
        for item in milestones:
            row = self._earning_row(item)
            self.earning_list.addWidget(row)
            progress[item["app_id"]] = row.bar_value
            if item["app_id"] == self._added_app:
                motion.fade(row, 0.0, 1.0, motion.NORMAL)
        self._progress = progress
        self._added_app = None

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
        # Items keep together (non-breaking spaces) and wrap between each other on narrow windows.
        parts = [part.replace(" ", "\u00a0") for part in fmt.reward(group["reward"], "|").split("|")]
        amounts = label(
            "\u00a0·  ".join(parts),
            "tick",
            wrap=True,
            align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        amounts.setFont(fonts.mono(10, 500, 2))
        lay.addWidget(amounts, 2)
        lay.addWidget(button("Claim", on_click=lambda ids=group["event_ids"]: self._claim(ids, row)))
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
        value = int(1000 * item["focused_ms"] / max(1, nxt["target_ms"])) if nxt else 1000
        col.addWidget(bar)
        animate_progress(bar, self._progress.get(item["app_id"], 0), value)
        row.bar_value = value
        if nxt:
            col.addWidget(label(f"Next: {fmt.reward(nxt['reward'], ', ')}", "caption", wrap=True))
        else:
            col.addWidget(label("All milestones reached today", "caption"))
        lay.addLayout(col, 1)
        remove = button(
            "",
            kind="ghost",
            icon="x",
            tooltip=f"Stop earning rewards for {item['name']}",
            on_click=lambda: self._remove_app(item["app_id"], item["name"], row),
        )
        lay.addWidget(remove, 0, Qt.AlignmentFlag.AlignTop)
        return row

    # ------------------------------------------------------------------

    def _animate_profile(self, profile: dict, into: int) -> None:
        """Count XP and credits, and fill the level bar (wrapping on a level-up)."""
        shown = self._shown
        self._shown = {"xp": profile["xp"], "credits": profile["credits"], "level": profile["level"], "into": into}
        if not shown:
            self.progress.setValue(into)
            self.stat_values["xp"].setText(fmt.count(profile["xp"]))
            self.stat_values["credits"].setText(fmt.count(profile["credits"]))
            return
        for key in ("xp", "credits"):
            if shown[key] != profile[key]:
                count_to(self.stat_values[key], shown[key], profile[key], lambda v: fmt.count(int(round(v))))
        if profile["level"] > shown["level"]:
            bar = self.progress

            def restart():
                bar.setValue(0)
                animate_progress(bar, 0, into)

            motion.tween(
                bar,
                float(shown["into"]),
                float(bar.maximum()),
                motion.SLOW,
                lambda v: bar.setValue(int(v)),
                motion.EASY_EASE,
                restart,
                key="progress",
            )
            motion.flash(self.level, theme.current().gold, radius=6)
        elif shown["into"] != into:
            animate_progress(self.progress, shown["into"], into)

    def _claim(self, event_ids: list[int], row: QWidget) -> None:
        applied = rewards.claim_many(event_ids)  # claim first; the animation only presents it
        motion.burst(row.findChild(QPushButton))
        motion.collapse(row, lambda: self._report(applied))

    def _claim_all(self) -> None:
        rows = [r for r in self._pending_rows if r is not None]
        if not rows:
            return
        self.claim_all.setEnabled(False)
        applied = rewards.claim_many()
        motion.burst(self.claim_all, radius=40, ticks=16)
        for row in rows[1:]:
            motion.collapse(row, lambda: None)
        motion.collapse(rows[0], lambda: self._report(applied))

    def _report(self, applied: dict) -> None:
        bus.rewards_changed.emit()  # refreshes this page while it is visible
        if not self.isVisible():
            self.refresh()
        if applied:
            motion.flash(self.profile)
            if applied.get("level_up"):
                motion.burst(self.level, theme.current().gold, radius=46, ticks=18)
            msg = "Claimed " + fmt.reward({k: v for k, v in applied.items() if k != "level_up"}, ", ")
            if applied.get("level_up"):
                msg += f". Level {applied['level_up']} reached!"
            self.ctx.toast(msg)

    def _changed(self) -> None:
        bus.rewards_changed.emit()
        if not self.isVisible():
            self.refresh()

    def _add_app(self) -> None:
        app_id = self.add_combo.currentData()
        if app_id is None:
            return
        rules.enable_app_rewards(app_id, True)
        self._added_app = app_id
        self.ctx.toast(f"{self.add_combo.currentText()} now earns rewards")
        self._changed()

    def _remove_app(self, app_id: int, name: str, row: QWidget) -> None:
        rules.enable_app_rewards(app_id, False)

        def undo():
            rules.enable_app_rewards(app_id, True)
            self._added_app = app_id
            self._changed()

        motion.collapse(row, self._changed)
        self.ctx.toast(f"{name} no longer earns rewards", "info", "Undo", undo)
