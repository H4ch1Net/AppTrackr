"""Focus: live flow, today's goal and chest, level, and the apps that count as focus."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QProgressBar, QSizePolicy, QVBoxLayout, QWidget

from ...core import tracker as trk
from ...data import queries
from ...game import economy, focus
from ...game import state as game_state
from ...rewards import engine as rewards
from ...rewards import rules
from .. import fmt, fonts, motion, theme
from ..signals import bus
from ..widgets.components import (
    AppAvatar,
    Card,
    Page,
    PageHeader,
    animate_progress,
    button,
    clear_layout,
    eyebrow,
    icon_label,
    label,
    set_role,
    vdivider,
)
from ..widgets.rolling import RollingLabel

LADDER_END_MIN = 90  # the ladder's right edge, a little past the top tier


class FlowLadder(QWidget):
    """The flow tiers as a ruler, filled up to how far the current run has come."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._minutes = 0.0
        self._shown = 0.0
        self._active = False

    def sizeHint(self) -> QSize:
        return QSize(400, 46)

    def set_run(self, minutes: float, active: bool) -> None:
        self._active = active
        target = min(minutes, LADDER_END_MIN)
        if abs(target - self._minutes) > 0.01:
            start = self._shown
            self._minutes = target
            jump = abs(target - start) > 2  # a new run or a break eases; live seconds just move
            motion.tween(
                self, start, target, motion.SLOW if jump else 0, self._set_shown, motion.DECELERATE, key="fill"
            )
        self.update()

    def _set_shown(self, value: float) -> None:
        self._shown = value
        self.update()

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width() - 2
        x_of = lambda m: 1 + w * min(m, LADDER_END_MIN) / LADDER_END_MIN  # noqa: E731
        y = 10
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.track))
        p.drawRoundedRect(QRectF(1, y - 3, w, 6), 3, 3)
        if self._shown > 0:
            p.setBrush(QColor(t.accent if self._active else t.text_dim))
            p.drawRoundedRect(QRectF(1, y - 3, x_of(self._shown) - 1, 6), 3, 3)
        current = economy.tier_index(self._shown)
        p.setFont(fonts.mono(9, 500, 4))
        for i, (start, mult, name) in enumerate(economy.FLOW_TIERS):
            x = x_of(start)
            reached = self._shown >= start and (self._shown > 0 or i == 0)
            p.setPen(QPen(QColor(t.text if reached else t.border_strong), 1.5))
            p.drawLine(QPointF(x, y - 7), QPointF(x, y + 7))
            color = t.accent_text if i == current and self._active else (t.text_dim if reached else t.text_muted)
            p.setPen(QColor(color))
            tiers = economy.FLOW_TIERS
            room = (x_of(tiers[i + 1][0]) if i + 1 < len(tiers) else self.width()) - x - 10
            full = f"×{mult:g}  {name.upper()}"
            show_name = i in (current, len(tiers) - 1) and p.fontMetrics().horizontalAdvance(full) <= room
            p.drawText(QPointF(x + 4, y + 24), full if show_name else f"×{mult:g}")


class RewardsView(Page):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx

        self.header = PageHeader(
            "Focus",
            "Stay in your focus apps to build flow. Flow multiplies what your village makes.",
            kicker="Progress",
        )
        self.add(self.header)

        # 01 Flow -------------------------------------------------------------
        self.flow_card = Card("Flow", index=1, padding=20)
        top = QHBoxLayout()
        top.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(2)
        self.multiplier = RollingLabel("×1")
        set_role(self.multiplier, "hero")
        left.addWidget(self.multiplier)
        self.tier = label("", "heading")
        left.addWidget(self.tier)
        top.addLayout(left)
        top.addWidget(vdivider())
        facts = QGridLayout()
        facts.setHorizontalSpacing(28)
        facts.setVerticalSpacing(4)
        self.facts: dict[str, RollingLabel] = {}
        for col, (key, caption) in enumerate((("run", "This run"), ("next", "Next tier"), ("today", "Focus today"))):
            facts.addWidget(eyebrow(caption), 0, col)
            value = RollingLabel("–")
            value.setFont(fonts.sans(20, 600, tabular=True))
            facts.addWidget(value, 1, col)
            self.facts[key] = value
        top.addLayout(facts, 1)
        self.flow_card.body.addLayout(top)
        self.ladder = FlowLadder()
        self.flow_card.body.addWidget(self.ladder)
        self.flow_hint = label("", "caption", wrap=True)
        self.flow_card.body.addWidget(self.flow_hint)
        self.add(self.flow_card)

        # 02 Today and 03 Level -----------------------------------------------
        row = self.stack_when_narrow(QHBoxLayout())
        row.setSpacing(16)
        self.today_card = Card("Today", index=2)
        goal_head = QHBoxLayout()
        self.goal_text = label("", "dim")
        goal_head.addWidget(self.goal_text, 1)
        self.streak_text = label("", "caption")
        goal_head.addWidget(self.streak_text)
        self.today_card.body.addLayout(goal_head)
        self.goal_bar = QProgressBar()
        self.goal_bar.setTextVisible(False)
        self.goal_bar.setMaximum(1000)
        self.goal_bar.setProperty("tone", "accent")
        self.today_card.body.addWidget(self.goal_bar)
        chest_row = QHBoxLayout()
        chest_row.setSpacing(12)
        self.chest_icon = icon_label("gift", "text_dim", 20)
        chest_row.addWidget(self.chest_icon)
        self.chest_text = label("", "dim", wrap=True)
        chest_row.addWidget(self.chest_text, 1)
        self.chest_btn = button("Open chest", kind="primary", icon="gift", on_click=self._open_chest)
        chest_row.addWidget(self.chest_btn)
        self.today_card.body.addLayout(chest_row)
        self.today_card.body.addStretch(1)
        row.addWidget(self.today_card, 3)

        self.level_card = Card("Level", index=3)
        lvl_row = QHBoxLayout()
        lvl_row.setSpacing(20)
        lvl_col = QVBoxLayout()
        lvl_col.setSpacing(0)
        cap = QHBoxLayout()
        cap.setSpacing(6)
        self.crown = icon_label("crown", "gold", 14)
        cap.addWidget(self.crown)
        cap.addStretch(1)
        lvl_col.addLayout(cap)
        self.level = RollingLabel("")
        set_role(self.level, "hero")
        lvl_col.addWidget(self.level)
        lvl_row.addLayout(lvl_col)
        stats = QVBoxLayout()
        stats.setSpacing(6)
        stats.addStretch(1)
        self.progress_text = label("", "caption")
        stats.addWidget(self.progress_text)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setProperty("tone", "accent")
        stats.addWidget(self.progress)
        self.credits_text = label("", "caption")
        stats.addWidget(self.credits_text)
        lvl_row.addLayout(stats, 1)
        self.level_card.body.addLayout(lvl_row)
        self.level_card.body.addStretch(1)
        row.addWidget(self.level_card, 2)
        self.add(row)

        # 04 Focus apps -------------------------------------------------------
        cols = self.stack_when_narrow(QHBoxLayout())
        cols.setSpacing(16)
        left_col = QVBoxLayout()
        left_col.setSpacing(16)
        self.apps_card = Card("Focus apps", "Time in these apps builds flow and powers the village", index=4)
        self.apps_list = QVBoxLayout()
        self.apps_list.setSpacing(4)
        self.apps_card.body.addLayout(self.apps_list)
        add_row = QHBoxLayout()
        self.add_combo = QComboBox()
        self.add_combo.setAccessibleName("App to add")
        self.add_combo.setMinimumWidth(200)
        add_row.addWidget(self.add_combo, 1)
        self.add_btn = button("Add app", icon="plus", on_click=self._add_app)
        add_row.addWidget(self.add_btn)
        self.apps_card.body.addLayout(add_row)
        left_col.addWidget(self.apps_card)

        # 05 Rewards saved from 1.x (only while some are pending)
        self.legacy = Card("Rewards from before", "Earned with the old milestones. Claim them any time.", index=5)
        self.claim_all = button("Claim all", kind="primary", icon="sparkles", on_click=self._claim_all)
        self.legacy.header_actions.addWidget(self.claim_all)
        self.legacy_text = label("", "dim", wrap=True)
        self.legacy.body.addWidget(self.legacy_text)
        left_col.addWidget(self.legacy)
        left_col.addStretch(1)
        cols.addLayout(left_col, 3)

        self.rules_card = Card("How it works", index=6)
        self._build_rules(self.rules_card)
        cols.addWidget(self.rules_card, 2, Qt.AlignmentFlag.AlignTop)
        self.add(cols)
        self.layout_.addStretch(1)

        self._shown: dict = {}
        self._added_app: int | None = None
        self._ticks = 0
        self._last_mult: float | None = None
        bus.rewards_changed.connect(lambda: self.isVisible() and self.refresh())
        bus.data_changed.connect(lambda: self.isVisible() and self.refresh())

    def _build_rules(self, card: Card) -> None:
        card.body.addWidget(
            label(
                "Every minute in a focus app earns focus points. Stay with it and the run climbs the flow tiers, "
                "multiplying what each minute is worth:",
                "dim",
                wrap=True,
            )
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(3)
        for i, (start, mult, name) in enumerate(economy.FLOW_TIERS):
            grid.addWidget(label(f"×{mult:g}"), i, 0)
            grid.addWidget(label(name, "dim"), i, 1)
            grid.addWidget(label(f"from {start} min" if start else "from the start", "caption"), i, 2)
        grid.setColumnStretch(1, 1)
        card.body.addLayout(grid)
        card.body.addWidget(
            label(
                f"A run survives {economy.FLOW_GRACE_SEC // 60} minutes away (a quick look at chat or docs). "
                "Taverns add more. Time outside focus apps never earns points.",
                "caption",
                wrap=True,
            )
        )
        card.body.addWidget(eyebrow("Every day"))
        card.body.addWidget(
            label(
                "Reach your daily focus goal to open a chest with credits and a blueprint and to grow your streak. "
                "Longer streaks fill bigger chests. The village turns focus points into resources; collect them "
                "on the Village page.",
                "caption",
                wrap=True,
            )
        )

    # ------------------------------------------------------------------

    def refresh(self) -> None:
        profile = rewards.get_profile()
        bonuses = game_state.get_bonuses()
        self.crown.setVisible(bonuses["has_monument"])
        self.level.roll_to(str(profile["level"]))
        into, need = economy.level_progress(profile["xp"])
        self.progress.setMaximum(need)
        self.progress_text.setText(f"{into} / {need} XP to level {profile['level'] + 1}")
        self.credits_text.setText(f"{fmt.count(profile['credits'])} credits · {fmt.count(profile['xp'])} XP in total")
        self._animate_level(profile, into)
        self._fill_today(profile)
        self._fill_apps()
        legacy = rewards.unclaimed_rewards()
        self.legacy.setVisible(bool(legacy))
        if legacy:
            total: dict = {}
            for item in legacy:
                for k, v in item["reward"].items():
                    total[k] = total.get(k, 0) + v
            self.legacy_text.setText(f"{len(legacy)} pending: {fmt.reward(total, ', ')}")
        self.tick()

    def tick(self) -> None:
        snap = self.ctx.snapshot()
        live = snap.app_id if snap.status == trk.STATUS_TRACKING else None
        village = game_state.get_village()
        flow = focus.current(
            live_app_id=live,
            live_since=snap.session_start if live else None,
            tavern_level=game_state.building_level(village, "tavern"),
        )
        self.multiplier.roll_to(f"×{flow.multiplier:g}")
        if flow.active and self._last_mult is not None and flow.multiplier > self._last_mult:
            motion.flash(self.multiplier, theme.current().accent, radius=6)
            motion.burst(self.multiplier, theme.current().accent, radius=44, ticks=16)  # a new flow tier
        self._last_mult = flow.multiplier
        self.tier.setText(flow.tier if flow.run_ms else "Not in a run")
        self.facts["run"].roll_to(fmt.clock(flow.run_ms) if flow.run_ms else "–")
        if flow.next_tier and flow.run_ms:
            self.facts["next"].roll_to(
                fmt.duration(flow.next_in_ms, short=True) if flow.next_in_ms >= 60_000 else "<1m"
            )
        else:
            self.facts["next"].roll_to("Top tier" if flow.run_ms else "–")
        self.facts["today"].roll_to(fmt.duration(flow.today_focus_ms, short=True) if flow.today_focus_ms else "0m")
        self.ladder.set_run(flow.run_ms / 60000, flow.active)
        if flow.active:
            pts = f"{flow.multiplier:g} focus point{'s' if flow.multiplier != 1 else ''}"
            if flow.next_tier:
                soon = fmt.duration(flow.next_in_ms, short=True) if flow.next_in_ms >= 60_000 else "under a minute"
                self.flow_hint.setText(f"Every minute here earns {pts}. {flow.next_tier} starts in {soon}.")
            else:
                self.flow_hint.setText(f"Top tier. Every minute here earns {pts}.")
        elif flow.run_ms:
            self.flow_hint.setText("Run paused. Come back to a focus app within the grace period to keep it.")
        elif not focus.focus_app_ids():
            self.flow_hint.setText("Add a focus app below to start building flow.")
        else:
            self.flow_hint.setText("Open one of your focus apps to start a run.")
        self._ticks += 1

    def _fill_today(self, profile: dict) -> None:
        today = date.today().isoformat()
        goal = rewards.goal_ms()
        snap = self.ctx.snapshot()
        live = snap.uncommitted_ms if snap.app_id in focus.focus_app_ids() else 0
        done = rewards.focus_ms(today) + live
        self.goal_text.setText(
            f"{fmt.duration(done, short=True)} of your {fmt.duration(goal, short=True)} focus goal"
            if done < goal
            else f"Goal reached: {fmt.duration(done, short=True)} of focus"
        )
        streak = profile["streak"]
        self.streak_text.setText(f"Streak {streak} day{'s' if streak != 1 else ''}" if streak else "No streak yet")
        animate_progress(self.goal_bar, self.goal_bar.value(), int(1000 * min(1.0, done / goal)))
        status = game_state.chest_state(today)
        ready = game_state.ready_chests()
        self.chest_btn.setVisible(bool(ready))
        reward = economy.chest_for(max(1, streak))
        contents = fmt.reward(reward, ", ")
        if ready:
            self.chest_text.setText(f"Your chest is ready: {contents}.")
            set_role(self.chest_icon, None)
        elif status == "claimed":
            self.chest_text.setText("Today's chest is open. Come back tomorrow for the next one.")
        else:
            self.chest_text.setText(f"Reach the goal to open today's chest ({contents}).")

    def _fill_apps(self) -> None:
        clear_layout(self.apps_list)
        today = date.today().isoformat()
        ids = rules.earning_app_ids()
        apps = [queries.get_app(i) for i in ids]
        apps = [a for a in apps if a and not a.get("is_hidden")]
        apps.sort(key=lambda a: -queries.app_usage_on(today, a["app_id"]))
        if not apps:
            self.apps_list.addWidget(
                label("No focus apps yet. Add the apps you want to spend your time in.", "dim", wrap=True)
            )
        goal = rewards.goal_ms()
        for app in apps:
            self.apps_list.addWidget(self._app_row(app, queries.app_usage_on(today, app["app_id"]), goal))
        self.add_combo.clear()
        for app in queries.top_apps(queries.days_ago(13), today, limit=40):
            if app["app_id"] not in ids:
                self.add_combo.addItem(app["name"], app["app_id"])
        self.add_combo.setEnabled(self.add_combo.count() > 0)
        self.add_btn.setEnabled(self.add_combo.count() > 0)
        if not self.add_combo.count():
            self.add_combo.addItem("All recent apps are focus apps")

    def _app_row(self, app: dict, used_ms: int, goal_ms: int) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(12)
        lay.addWidget(AppAvatar(app["name"], app.get("icon_path"), 28))
        col = QVBoxLayout()
        col.setSpacing(4)
        top = QHBoxLayout()
        name = label(app["name"])
        name.setFont(fonts.sans(13, 600))
        top.addWidget(name)
        top.addStretch(1)
        top.addWidget(label(f"{fmt.duration(used_ms, short=True)} today" if used_ms else "Not yet today", "caption"))
        col.addLayout(top)
        bar = QProgressBar()
        bar.setTextVisible(False)
        bar.setMaximum(1000)
        animate_progress(bar, 0, int(1000 * min(1.0, used_ms / max(1, goal_ms))))
        col.addWidget(bar)
        lay.addLayout(col, 1)
        remove = button(
            "",
            kind="ghost",
            icon="x",
            tooltip=f"Stop counting {app['name']} as focus",
            on_click=lambda: self._remove_app(app["app_id"], app["name"], row),
        )
        lay.addWidget(remove, 0, Qt.AlignmentFlag.AlignTop)
        if app["app_id"] == self._added_app:
            motion.fade(row, 0.0, 1.0, motion.NORMAL)
            self._added_app = None
        return row

    def _animate_level(self, profile: dict, into: int) -> None:
        shown = self._shown
        self._shown = {"level": profile["level"], "into": into}
        if not shown:
            self.progress.setValue(into)
            return
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
            motion.burst(self.level, theme.current().gold, radius=46, ticks=18)
        elif shown["into"] != into:
            animate_progress(self.progress, shown["into"], into)

    # ------------------------------------------------------------------

    def _open_chest(self) -> None:
        days = game_state.ready_chests()
        if not days:
            return
        applied = game_state.open_chest(days[-1]) or {}
        motion.burst(self.chest_btn, radius=44, ticks=18)
        msg = "Chest opened: " + fmt.reward({k: v for k, v in applied.items() if k != "level_up"}, ", ")
        if applied.get("level_up"):
            msg += f". Level {applied['level_up']} reached!"
        self.ctx.toast(msg)
        self._changed()

    def _claim_all(self) -> None:
        applied = rewards.claim_many()
        motion.burst(self.claim_all, radius=40, ticks=16)
        if applied:
            self.ctx.toast("Claimed " + fmt.reward({k: v for k, v in applied.items() if k != "level_up"}, ", "))
        self._changed()

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
        self.ctx.toast(f"{self.add_combo.currentText()} now counts as focus")
        self._changed()

    def _remove_app(self, app_id: int, name: str, row: QWidget) -> None:
        rules.enable_app_rewards(app_id, False)

        def undo():
            rules.enable_app_rewards(app_id, True)
            self._added_app = app_id
            self._changed()

        motion.collapse(row, self._changed)
        self.ctx.toast(f"{name} no longer counts as focus", "info", "Undo", undo)
