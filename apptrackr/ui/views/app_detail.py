"""App detail: totals, 30-day history, limit, rewards and recent sessions for one app."""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...data import catalog, queries
from ...rewards import engine as rewards
from ...rewards import rules
from .. import fmt
from ..signals import bus
from ..widgets.charts import Bar, BarChart
from ..widgets.components import (
    AppAvatar,
    Card,
    EmptyState,
    IconBinding,
    Page,
    SettingRow,
    StatTile,
    Toggle,
    button,
    clear_layout,
    divider,
    label,
)

LIMITS = (
    ("No limit", 0),
    ("15 minutes", 15),
    ("30 minutes", 30),
    ("45 minutes", 45),
    ("1 hour", 60),
    ("1.5 hours", 90),
    ("2 hours", 120),
    ("3 hours", 180),
    ("4 hours", 240),
    ("6 hours", 360),
)
MINUTE = 60_000


class AppDetailView(Page):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        self.app_id: int | None = None

        self.back = button("Back", kind="ghost", icon="arrow-left", tooltip="Back (Esc)", on_click=ctx.window.go_back)
        back_row = QHBoxLayout()
        back_row.addWidget(self.back)
        back_row.addStretch(1)
        self.add(back_row)

        head = QHBoxLayout()
        head.setSpacing(14)
        self.avatar = AppAvatar("", None, 48)
        head.addWidget(self.avatar)
        names = QVBoxLayout()
        names.setSpacing(2)
        self.title = label("", "title")
        names.addWidget(self.title)
        self.subtitle = label("", "subtitle")
        self.subtitle.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        names.addWidget(self.subtitle)
        head.addLayout(names, 1)
        self.fav_btn = QPushButton("Favorite")
        self.fav_btn.setCheckable(True)
        self.fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fav_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        IconBinding.attach(self.fav_btn, "star", "text_dim", checked_tone="gold")
        self.fav_btn.clicked.connect(self._toggle_favorite)
        head.addWidget(self.fav_btn)
        self.more_btn = button("", icon="ellipsis", tooltip="More actions")
        self.more_btn.clicked.connect(self._more_menu)
        head.addWidget(self.more_btn)
        self.add(head)

        tiles = QGridLayout()
        tiles.setSpacing(14)
        self.t_today = StatTile("Today", "clock")
        self.t_week = StatTile("Last 7 days", "calendar-days")
        self.t_month = StatTile("Last 30 days", "activity")
        self.t_avg = StatTile("Daily average", "timer")
        for i, tile in enumerate((self.t_today, self.t_week, self.t_month, self.t_avg)):
            tiles.addWidget(tile, 0, i)
        self.add(tiles)

        self.chart_card = Card("Last 30 days", "Focused time per day")
        self.chart = BarChart(180)
        self.chart_card.body.addWidget(self.chart)
        self.add(self.chart_card)

        cols = QHBoxLayout()
        cols.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(14)

        self.settings_card = Card("Settings")
        self.category = QComboBox()
        self.category.addItem("Uncategorized", None)
        for cat in queries.CATEGORIES:
            self.category.addItem(cat, cat)
        self.category.currentIndexChanged.connect(self._on_category)
        self.settings_card.body.addWidget(
            SettingRow("Category", "Groups apps on the dashboard and in filters.", self.category)
        )
        self.settings_card.body.addWidget(divider())
        self.limit = QComboBox()
        for text, minutes in LIMITS:
            self.limit.addItem(text, minutes)
        self.limit.currentIndexChanged.connect(self._on_limit)
        self.settings_card.body.addWidget(
            SettingRow("Daily limit", "Get a notification once today's time passes it.", self.limit)
        )
        self.rewards_divider = divider()
        self.settings_card.body.addWidget(self.rewards_divider)
        self.rewards_toggle = Toggle()
        self.rewards_toggle.toggled.connect(self._on_rewards)
        self.rewards_row = SettingRow(
            "Earn rewards", "Time in this app earns XP and village resources.", self.rewards_toggle
        )
        self.settings_card.body.addWidget(self.rewards_row)
        self.reward_hint = label("", "caption", wrap=True)
        self.settings_card.body.addWidget(self.reward_hint)
        left.addWidget(self.settings_card)

        self.facts = Card("Details")
        self.facts_grid = QGridLayout()
        self.facts_grid.setHorizontalSpacing(16)
        self.facts_grid.setVerticalSpacing(8)
        self.facts.body.addLayout(self.facts_grid)
        left.addWidget(self.facts)
        left.addStretch(1)
        cols.addLayout(left, 1)

        self.sessions_card = Card("Recent sessions", "Each continuous stretch of focus")
        self.sessions = QVBoxLayout()
        self.sessions.setSpacing(0)
        self.sessions_card.body.addLayout(self.sessions)
        self.sessions_card.body.addStretch(1)
        cols.addWidget(self.sessions_card, 1)
        self.add(cols)
        self.layout_.addStretch(1)

    # ------------------------------------------------------------------

    def load_app(self, app_id: int) -> None:
        self.app_id = app_id
        self.verticalScrollBar().setValue(0)
        self.reload()

    def reload(self) -> None:
        if self.app_id is None:
            return
        app = queries.get_app(self.app_id)
        if not app:
            self.ctx.window.go_back()
            return
        self.back.setText(f"Back to {self.ctx.window.back_label()}")
        self.avatar.set_app(app["name"], app.get("icon_path"))
        self.title.setText(app["name"])
        self.subtitle.setText(app["exe_name"] + (f"  ·  {app['icon_path']}" if app.get("icon_path") else ""))
        self.fav_btn.setChecked(bool(app.get("is_favorite")))
        self.fav_btn.setText("Favorite" if app.get("is_favorite") else "Add to favorites")

        self._set_combo(self.category, app.get("category"))
        limit_minutes = (app.get("daily_limit_ms") or 0) // MINUTE
        if self.limit.findData(limit_minutes) < 0:
            self.limit.addItem(fmt.duration(limit_minutes * MINUTE), limit_minutes)
        self._set_combo(self.limit, limit_minutes)

        on = rewards.enabled()
        for w in (self.rewards_divider, self.rewards_row, self.reward_hint):
            w.setVisible(on)
        self.rewards_toggle.set_silently(rules.app_rewards_enabled(self.app_id))
        self._update_reward_hint()

        history = queries.app_daily_history(self.app_id, 30)
        snap = self.ctx.snapshot()
        live = snap.uncommitted_ms if snap.app_id == self.app_id else 0
        history[-1]["focused_ms"] += live
        week = history[-7:]
        total_30 = sum(h["focused_ms"] for h in history)
        active = [h for h in history if h["focused_ms"] > 0]
        limit_ms = app.get("daily_limit_ms")
        today_ms = history[-1]["focused_ms"]

        self.t_today.set(
            fmt.duration(today_ms, short=True),
            (
                f"of {fmt.duration(limit_ms, short=True)} limit"
                if limit_ms
                else f"{history[-1]['opens_count']} launches"
            ),
            "danger" if limit_ms and today_ms >= limit_ms else "caption",
        )
        self.t_week.set(
            fmt.duration(sum(h["focused_ms"] for h in week), short=True),
            f"{sum(h['opens_count'] for h in week)} launches",
        )
        self.t_month.set(fmt.duration(total_30, short=True), f"{len(active)} active days")
        self.t_avg.set(
            fmt.duration(total_30 / len(active), short=True) if active else "0s", "per active day, last 30 days"
        )

        self.chart.set_data(
            [
                Bar(
                    str(date.fromisoformat(h["day"]).day) if i % 3 == 2 or i == 29 else "",
                    h["focused_ms"],
                    f"{fmt.long_date(h['day'])}\n{fmt.duration(h['focused_ms'])}"
                    + (f" · {h['opens_count']} launches" if h["opens_count"] else ""),
                )
                for i, h in enumerate(history)
            ],
            highlight=29,
            limit=limit_ms,
            empty_text="No activity in the last 30 days",
        )
        self.chart_card.set_caption(
            "Focused time per day"
            + (f" · dashed line is your {fmt.duration(limit_ms, short=True)} limit" if limit_ms else "")
        )

        self._fill_facts(app)
        self._fill_sessions()

    def _fill_facts(self, app: dict) -> None:
        clear_layout(self.facts_grid)
        summary = queries.app_summary(self.app_id)
        facts = [
            ("First seen", fmt.relative_day(summary["first_day"])),
            ("Last used", fmt.relative_day(summary["last_day"])),
            ("All-time total", fmt.duration(summary["total_ms"], short=True)),
            ("Active days", str(summary["active_days"])),
            ("Longest session", fmt.duration(summary["longest_session_ms"], short=True)),
            ("Executable", app["exe_name"]),
        ]
        for row, (name, value) in enumerate(facts):
            self.facts_grid.addWidget(label(name, "muted"), row, 0)
            val = label(value)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.facts_grid.addWidget(val, row, 1)
        self.facts_grid.setColumnStretch(1, 1)

    def _fill_sessions(self) -> None:
        clear_layout(self.sessions)
        sessions = queries.recent_sessions(self.app_id, limit=12)
        if not sessions:
            self.sessions.addWidget(EmptyState("clock", "No sessions yet"))
            return
        last_day = None
        for s in sessions:
            day = datetime.fromtimestamp(s["start_ts"]).date()
            if day != last_day:
                heading = label(
                    fmt.relative_day(day).upper() if (date.today() - day).days < 2 else fmt.long_date(day).upper(),
                    "section",
                )
                heading.setContentsMargins(0, 10 if last_day else 0, 0, 4)
                self.sessions.addWidget(heading)
                last_day = day
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 5, 0, 5)
            lay.addWidget(label(f"{fmt.time_of_day(s['start_ts'])} – {fmt.time_of_day(s['end_ts'])}", "dim"))
            if s["was_idle"]:
                tag = label("then idle", "pill")
                tag.setToolTip("This session ended because there was no input for the idle timeout.")
                lay.addWidget(tag)
            lay.addStretch(1)
            dur = label(fmt.duration(s["duration_ms"], short=True))
            dur.setStyleSheet("font-weight: 600;")
            lay.addWidget(dur)
            self.sessions.addWidget(row)

    def _update_reward_hint(self) -> None:
        if not self.rewards_toggle.isChecked():
            self.reward_hint.setText("")
            self.reward_hint.hide()
            return
        item = next((m for m in rewards.next_milestones() if m["app_id"] == self.app_id), None)
        if item and item["next"]:
            nxt = item["next"]
            self.reward_hint.setText(
                f"Next milestone at {fmt.duration(nxt['target_ms'], short=True)} today "
                f"({fmt.duration(item['focused_ms'], short=True)} so far): {fmt.reward(nxt['reward'], ', ')}"
            )
        else:
            self.reward_hint.setText("All of today's milestones are done.")
        self.reward_hint.setVisible(rewards.enabled())

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @staticmethod
    def _set_combo(combo: QComboBox, data) -> None:
        idx = combo.findData(data)
        combo.blockSignals(True)
        combo.setCurrentIndex(max(0, idx))
        combo.blockSignals(False)

    def _toggle_favorite(self) -> None:
        queries.set_favorite(self.app_id, self.fav_btn.isChecked())
        bus.data_changed.emit()
        self.reload()

    def _on_category(self) -> None:
        if self.app_id is not None:
            queries.set_category(self.app_id, self.category.currentData())
            bus.data_changed.emit()

    def _on_limit(self) -> None:
        if self.app_id is None:
            return
        minutes = self.limit.currentData() or 0
        queries.set_daily_limit(self.app_id, minutes * MINUTE)
        bus.data_changed.emit()
        self.ctx.toast(f"Daily limit set to {fmt.duration(minutes * MINUTE)}" if minutes else "Daily limit removed")
        self.reload()

    def _on_rewards(self, on: bool) -> None:
        if self.app_id is None:
            return
        rules.enable_app_rewards(self.app_id, on)
        bus.rewards_changed.emit()
        self._update_reward_hint()

    def _more_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Rename…", self._rename)
        menu.addAction("Reset name", lambda: self._apply_name(None))
        menu.addSeparator()
        menu.addAction("Exclude from tracking", lambda: self.ctx.window.exclude_app(self.app_id))
        menu.exec(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))

    def _rename(self) -> None:
        app = queries.get_app(self.app_id)
        name, ok = QInputDialog.getText(self, "Rename app", f"Display name for {app['exe_name']}:", text=app["name"])
        if ok:
            self._apply_name(name)

    def _apply_name(self, name: str | None) -> None:
        app = queries.get_app(self.app_id)
        queries.set_display_name(self.app_id, name or catalog.friendly_name(app["exe_name"]))
        bus.data_changed.emit()
        self.reload()
