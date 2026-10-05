"""Dashboard: what is being tracked right now and how today is going."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QHBoxLayout, QMenu, QVBoxLayout, QWidget

from ...core import tracker as trk
from ...data import db, queries
from ...game import economy
from ...rewards import engine as rewards
from .. import fmt, fonts, icons, motion, theme
from ..signals import bus
from ..widgets.charts import Bar, BarChart, SessionDial, ShareBar
from ..widgets.components import (
    AppAvatar,
    AppRow,
    Card,
    EmptyState,
    FlowLayout,
    MetricGrid,
    Page,
    PageHeader,
    StatTile,
    button,
    clear_layout,
    divider,
    eyebrow,
    icon_label,
    label,
    legend_item,
    set_role,
    tone_color,
)
from ..widgets.other_terms import OtherTermsCard
from ..widgets.rolling import RollingLabel

TOP_APPS = 7


class NowCard(Card):
    """Live session: chronograph dial, current app and pause controls."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent=parent, padding=18, spacing=12)
        self.ctx = ctx
        head = QHBoxLayout()
        head.addWidget(eyebrow("Now", 1))
        head.addStretch(1)
        self.pulse = motion.PulseDot(5)
        head.addWidget(self.pulse)
        self.state = label("", "pillAccent")
        head.addWidget(self.state)
        self.body.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(18)
        self.dial = SessionDial(150)
        row.addWidget(self.dial)

        self.identity = QWidget()
        col = QVBoxLayout(self.identity)
        col.setContentsMargins(0, 4, 0, 0)
        col.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.avatar = AppAvatar("", None, 32)
        top.addWidget(self.avatar)
        self.state_icon = icon_label("pause", "warning", 22)
        top.addWidget(self.state_icon)
        self.name = label("", "heading")
        self.name.setFont(fonts.sans(19, 600))
        top.addWidget(self.name, 1)
        col.addLayout(top)
        self.detail = label("", "caption", wrap=True)
        col.addWidget(self.detail)
        col.addSpacing(6)
        col.addWidget(divider())
        col.addSpacing(4)
        facts = QHBoxLayout()
        facts.setSpacing(18)
        self.fact_started = self._fact("Started")
        self.fact_today = self._fact("Today in app")
        facts.addLayout(self.fact_started[0])
        facts.addLayout(self.fact_today[0])
        facts.addStretch(1)
        col.addLayout(facts)
        col.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.pause_btn = button("Pause", kind="primary", on_click=ctx.window.toggle_pause)
        self.pause_btn.setIconSize(QSize(14, 14))
        actions.addWidget(self.pause_btn)
        self.later_btn = button("Pause for…", icon="timer", tooltip="Pause for a while")
        menu = QMenu(self.later_btn)
        for text, minutes in (("15 minutes", 15), ("30 minutes", 30), ("1 hour", 60), ("2 hours", 120)):
            menu.addAction(f"Pause for {text}", lambda m=minutes: ctx.window.pause_for(m))
        self.later_btn.clicked.connect(
            lambda: menu.exec(self.later_btn.mapToGlobal(self.later_btn.rect().bottomLeft()))
        )
        actions.addWidget(self.later_btn)
        actions.addStretch(1)
        col.addLayout(actions)
        row.addWidget(self.identity, 1)
        self.body.addLayout(row)
        self._last_app: int | None = None
        self._last_key: tuple | None = None

    @staticmethod
    def _fact(caption: str):
        box = QVBoxLayout()
        box.setSpacing(2)
        box.addWidget(eyebrow(caption))
        value = RollingLabel("–")
        value.setFont(fonts.sans(14, 600, tabular=True))
        box.addWidget(value)
        return box, value

    def update_from(self, snap: trk.Snapshot) -> None:
        tracking = snap.status == trk.STATUS_TRACKING and snap.app_id is not None
        key = (snap.status, snap.app_id)
        if self._last_key is not None and key != self._last_key and self.isVisible():
            motion.fade(self.identity, 0.0, 1.0, motion.NORMAL, motion.DECELERATE)
        self._last_key = key
        self.pulse.set_state(tracking, theme.current().accent)
        self.pulse.setVisible(tracking)
        self.avatar.setVisible(tracking)
        self.state_icon.setVisible(not tracking)
        paused = snap.status == trk.STATUS_PAUSED
        self.pause_btn.setText("Resume" if paused else "Pause")
        self.pause_btn.setIcon(icons.icon("play" if paused else "pause", tone_color("text_on"), 14))
        self.pause_btn.setEnabled(self.ctx.tracker.supported)
        self.later_btn.setVisible(self.ctx.tracker.supported and not paused)

        if tracking:
            app = queries.get_app(snap.app_id) or {"name": snap.exe_name}
            if snap.app_id != self._last_app:
                self.avatar.set_app(app["name"], app.get("icon_path"))
                self._last_app = snap.app_id
            self.name.setText(app["name"])
            today = queries.app_usage_on(queries.today_str(), snap.app_id) + snap.uncommitted_ms
            parts = [app.get("category") or "Uncategorized"]
            if app.get("daily_limit_ms"):
                parts.append(f"limit {fmt.duration(app['daily_limit_ms'], short=True)}")
            self.detail.setText(" · ".join(parts))
            self.fact_started[1].setText(fmt.time_of_day(snap.session_start))
            self.fact_today[1].roll_to(fmt.duration(today, short=True))
            self.dial.set_state(True, snap.session_ms, "Session")
            self._set_state("Live", "pillAccent")
            return

        self._last_app = None
        icon, title, detail, pill = {
            trk.STATUS_PAUSED: ("pause", "Tracking paused", "Nothing is recorded until you resume.", "Paused"),
            trk.STATUS_IDLE: ("clock", "Away", self._idle_text(), "Idle"),
            trk.STATUS_LOCKED: ("clock", "Screen locked", "Tracking continues when you unlock.", "Locked"),
            trk.STATUS_UNSUPPORTED: (
                "power",
                "Tracking unavailable",
                "Foreground tracking needs Windows. Run with --demo to explore with sample data.",
                "Off",
            ),
        }.get(snap.status, ("activity", "Waiting for an app", "Switch to any app to start tracking.", "Ready"))
        if paused and snap.paused_until:
            detail = f"Resumes automatically at {fmt.time_of_day(snap.paused_until)}."
        self.state_icon.setPixmap(icons.pixmap(icon, tone_color("warning" if paused else "text_muted"), 22))
        self.name.setText(title)
        self.detail.setText(detail)
        self.fact_started[1].setText("–")
        self.fact_today[1].setText("–")
        self.dial.set_state(False, 0, pill)
        self._set_state(pill, "pill")

    @staticmethod
    def _idle_text() -> str:
        minutes = db.get_int("idle_threshold_sec", 300) // 60
        return f"No input for {minutes} min. Tracking resumes when you're back."

    def _set_state(self, text: str, role: str) -> None:
        if self.state.property("role") != role:
            set_role(self.state, role)
        self.state.setText(text)


class DashboardView(Page):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        self._ticks = 0
        self._yesterday_hours: list[int] | None = None
        self._day_keys: list[str] = []
        self._fractions: dict[int, float] = {}

        self.header = PageHeader("Dashboard", "", kicker=_kicker_date())
        self.add(self.header)

        top = self.stack_when_narrow(QHBoxLayout())
        top.setSpacing(16)
        self.now = NowCard(ctx)
        self.now.setMinimumWidth(380)
        top.addWidget(self.now, 6)
        self.t_today = StatTile("Today", framed=False)
        self.t_week = StatTile("This week", framed=False)
        self.t_apps = StatTile("Apps used today", framed=False)
        self.t_streak = StatTile("Streak", framed=False)
        self.metrics = MetricGrid([self.t_today, self.t_week, self.t_apps, self.t_streak])
        top.addWidget(self.metrics, 5)
        self.add(top)

        cols = self.stack_when_narrow(QHBoxLayout())
        cols.setSpacing(16)
        charts = QVBoxLayout()
        charts.setSpacing(16)
        self.hourly_card = Card("Today by hour", "Focused time in each hour", index=2)
        self.hourly = BarChart(150)
        self.hourly_card.body.addWidget(self.hourly)
        charts.addWidget(self.hourly_card)

        self.days_card = Card("Last 14 days", "Click a day to open it in the calendar", index=3)
        self.days = BarChart(150)
        self.days.bar_clicked.connect(self._open_day)
        self.days_card.body.addWidget(self.days)
        charts.addWidget(self.days_card)
        cols.addLayout(charts, 6)

        self.top_card = Card("Top apps today", index=4)
        self.top_card.header_actions.addWidget(button("View all", kind="link", on_click=self._view_all))
        self.top_list = QVBoxLayout()
        self.top_list.setSpacing(2)
        self.top_card.body.addLayout(self.top_list)
        self.top_card.body.addStretch(1)
        self.category_title = eyebrow("By category")
        self.top_card.body.addWidget(self.category_title)
        self.share = ShareBar()
        self.top_card.body.addWidget(self.share)
        legend_host = QWidget()
        self.legend = FlowLayout(legend_host)
        self.top_card.body.addWidget(legend_host)
        cols.addWidget(self.top_card, 5)
        self.add(cols)

        self.other_terms = OtherTermsCard(index=5)
        self.add(self.other_terms)
        self.layout_.addStretch(1)

        bus.data_changed.connect(lambda: self.isVisible() and self.refresh())

    # ------------------------------------------------------------------

    def refresh(self) -> None:
        self.header.set_kicker(_kicker_date())
        snap = self.ctx.snapshot()
        self._refresh_totals(snap)
        self._refresh_charts(snap)
        self._refresh_top(snap)
        self.now.update_from(snap)

    def tick(self) -> None:
        self._ticks += 1
        snap = self.ctx.snapshot()
        self.now.update_from(snap)
        self._refresh_totals(snap)
        if self._ticks % 15 == 0:
            self._refresh_charts(snap)
            self._refresh_top(snap)

    def _refresh_totals(self, snap: trk.Snapshot) -> None:
        today = queries.today_str()
        live = snap.uncommitted_ms if snap.app_id else 0
        today_ms = queries.total_ms(today, today) + live

        now = datetime.now()
        if self._ticks % 60 == 0 or self._yesterday_hours is None:
            self._yesterday_hours = queries.hourly_totals((date.today() - timedelta(days=1)).isoformat())
        hours = self._yesterday_hours
        same_time = sum(hours[: now.hour]) + hours[now.hour] * now.minute / 60
        change = fmt.percent_change(today_ms, same_time)
        if change:
            role = "success" if today_ms >= same_time else "caption"
            self.t_today.set_number(today_ms, _short, f"{change} vs this time yesterday", role)
        else:
            total = sum(hours)
            sub = f"Yesterday: {fmt.duration(total, short=True)}" if total else "Nothing tracked yesterday"
            self.t_today.set_number(today_ms, _short, sub)

        week_ms = queries.total_ms(queries.week_start(), today) + live
        days_in = date.today().weekday() + 1
        self.t_week.set_number(week_ms, _short, f"{fmt.duration(week_ms / days_in, short=True)} per day on average")
        all_ms = queries.total_ms(queries.first_tracked_day() or today, today) + live
        self.other_terms.set_totals(today_ms, week_ms, all_ms)

        profile = rewards.get_profile()
        streak = profile["streak"]
        fav_today = rewards.favorites_ms(today)
        current = queries.get_app(snap.app_id) if snap.app_id else None
        if current and current.get("is_favorite"):
            fav_today += live
        if not db.fetchone("SELECT 1 FROM apps WHERE is_favorite = 1 AND is_hidden = 0"):
            sub = "Star an app to start a streak"
        elif profile.get("last_streak_day") == today or fav_today >= economy.STREAK_GOAL_MS:
            sub = "Today's goal is done"
        else:
            left = economy.STREAK_GOAL_MS - fav_today
            sub = f"{fmt.duration(left, short=True)} in favorites to go today"
        self.t_streak.set_number(streak, _days, sub, tooltip="A streak day needs 30 minutes in your favorite apps.")

    def _refresh_charts(self, snap: trk.Snapshot) -> None:
        today = date.today()
        hours = queries.hourly_totals(today.isoformat())
        if snap.app_id:
            hours[datetime.now().hour] += snap.uncommitted_ms
        self.hourly.set_data(
            [
                Bar(f"{h:02d}" if h % 3 == 0 else "", ms, f"{h:02d}:00 to {(h + 1) % 24:02d}:00\n{fmt.duration(ms)}")
                for h, ms in enumerate(hours)
            ],
            highlight=datetime.now().hour,
            empty_text="Nothing tracked today yet",
        )
        start = today - timedelta(days=13)
        totals = queries.daily_totals(start.isoformat(), today.isoformat())
        self._day_keys = [(start + timedelta(days=i)).isoformat() for i in range(14)]
        bars = []
        for key in self._day_keys:
            d = date.fromisoformat(key)
            ms = totals.get(key, 0) + (snap.uncommitted_ms if key == today.isoformat() and snap.app_id else 0)
            bars.append(Bar(str(d.day), ms, f"{fmt.long_date(d)}\n{fmt.duration(ms) if ms else 'No activity'}"))
        self.days.set_data(bars, highlight=13, empty_text="No activity in the last two weeks")

    def _refresh_top(self, snap: trk.Snapshot) -> None:
        today = queries.today_str()
        apps = queries.top_apps(today, today, limit=None)
        if snap.app_id:
            for app in apps:
                if app["app_id"] == snap.app_id:
                    app["focused_ms"] += snap.uncommitted_ms
            apps.sort(key=lambda a: -a["focused_ms"])
        total = sum(a["focused_ms"] for a in apps) or 1
        self.t_apps.set_number(len(apps), _count, f"Most used: {apps[0]['name']}" if apps else "No apps yet today")

        clear_layout(self.top_list)
        if not apps:
            self.top_list.addWidget(
                EmptyState("layout-grid", "No apps yet today", "Apps appear here as soon as they have been in focus.")
            )
        peak = apps[0]["focused_ms"] if apps else 1
        for rank, app in enumerate(apps[:TOP_APPS], start=1):
            limit = app.get("daily_limit_ms")
            over = bool(limit and app["focused_ms"] >= limit)
            fraction = app["focused_ms"] / peak
            row = AppRow(
                app,
                fmt.duration(app["focused_ms"], short=True),
                fraction,
                rank=rank,
                dot=None if limit else theme.category_color(app.get("category")),
                animate_from=self._fractions.get(app["app_id"], 0.0),
                sub=f"Limit {fmt.duration(limit, short=True)}" + (" reached" if over else "")
                if limit
                else (app.get("category") or "Uncategorized"),
                tone="danger" if over else ("accent" if app["app_id"] == snap.app_id else "ink"),
                extra=f"{app['focused_ms'] / total:.0%}",
                marker=(limit / peak) if limit and limit < peak else None,
            )
            row.clicked.connect(self.ctx.open_app)
            row.context_requested.connect(self.ctx.app_menu)
            self.top_list.addWidget(row)
        self._fractions = {a["app_id"]: a["focused_ms"] / peak for a in apps[:TOP_APPS]}

        by_cat: dict[str | None, int] = {}
        for app in apps:
            by_cat[app.get("category")] = by_cat.get(app.get("category"), 0) + app["focused_ms"]
        ranked = sorted(by_cat.items(), key=lambda kv: -kv[1])
        self.share.set_segments([(c or "Uncategorized", ms, theme.category_color(c)) for c, ms in ranked])
        clear_layout(self.legend)
        for cat, ms in ranked:
            self.legend.addWidget(legend_item(theme.category_color(cat), f"{cat or 'Uncategorized'} {ms / total:.0%}"))
        has_cats = any(c for c in by_cat)
        for w in (self.category_title, self.share):
            w.setVisible(bool(apps))
        self.legend.parentWidget().setVisible(bool(apps))
        if apps and not has_cats:
            self.category_title.setText("By category · set categories on an app's page")
        else:
            self.category_title.setText("By category")

    def _open_day(self, index: int) -> None:
        if 0 <= index < len(self._day_keys):
            self.ctx.open_day(self._day_keys[index])

    def _view_all(self) -> None:
        apps_view = self.ctx.window._views["apps"]
        apps_view.set_period(0)
        self.ctx.navigate("apps")


def _short(ms: float) -> str:
    return fmt.duration(ms, short=True)


def _count(n: float) -> str:
    return str(int(round(n)))


def _days(n: float) -> str:
    n = int(round(n))
    return f"{n} day{'s' if n != 1 else ''}"


def _kicker_date() -> str:
    """Instrument-style date readout, e.g. SAT 03 OCT 2026."""
    d = date.today()
    return f"{d:%a} {d.day:02d} {d:%b} {d.year}"
