"""Calendar: month heatmap with a breakdown of the selected day."""

from __future__ import annotations

import calendar
from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from ...data import queries
from .. import fmt, motion
from ..signals import bus
from ..widgets.charts import Bar, BarChart, MonthHeatmap
from ..widgets.components import AppRow, Card, EmptyState, Page, PageHeader, button, clear_layout, count_to, label


class CalendarView(Page):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        self._month = date.today().replace(day=1)
        self._selected = date.today()
        self._day_total = 0
        self._fractions: dict[int, float] = {}

        self.header = PageHeader("Calendar")
        self.prev_btn = button(
            "", icon="chevron-left", tooltip="Previous month (PgUp)", on_click=lambda: self._shift(-1)
        )
        self.next_btn = button("", icon="chevron-right", tooltip="Next month (PgDown)", on_click=lambda: self._shift(1))
        self.today_btn = button("Today", on_click=self._go_today)
        for b in (self.prev_btn, self.today_btn, self.next_btn):
            self.header.actions.addWidget(b)
        self.add(self.header)

        cols = QHBoxLayout()
        cols.setSpacing(14)

        self.month_card = Card()
        self.month_title = label("", "heading")
        self.month_card.body.addWidget(self.month_title)
        self.heatmap = MonthHeatmap()
        self.heatmap.day_selected.connect(self._on_day)
        self.month_card.body.addWidget(self.heatmap)
        stats = QHBoxLayout()
        stats.setSpacing(18)
        self.stat_labels = {}
        for key, caption in (
            ("total", "Total"),
            ("avg", "Daily average"),
            ("active", "Active days"),
            ("best", "Busiest day"),
        ):
            box = QVBoxLayout()
            box.setSpacing(0)
            box.addWidget(label(caption, "caption"))
            value = label("–")
            value.setStyleSheet("font-weight: 700; font-size: 15px;")
            box.addWidget(value)
            self.stat_labels[key] = value
            stats.addLayout(box)
        stats.addStretch(1)
        self.month_card.body.addLayout(stats)
        self.month_card.body.addStretch(1)
        cols.addWidget(self.month_card, 11)

        self.day_card = Card()
        head = QHBoxLayout()
        names = QVBoxLayout()
        names.setSpacing(2)
        self.day_title = label("", "heading")
        names.addWidget(self.day_title)
        self.day_sub = label("", "caption")
        names.addWidget(self.day_sub)
        head.addLayout(names, 1)
        self.day_total = label("", "value")
        head.addWidget(self.day_total, 0, Qt.AlignmentFlag.AlignTop)
        self.day_card.body.addLayout(head)
        self.day_hours = BarChart(110)
        self.day_card.body.addWidget(self.day_hours)
        self.day_list = QVBoxLayout()
        self.day_list.setSpacing(2)
        self.day_card.body.addLayout(self.day_list)
        self.day_card.body.addStretch(1)
        cols.addWidget(self.day_card, 10)
        self.add(cols)
        self.layout_.addStretch(1)

        bus.data_changed.connect(lambda: self.isVisible() and self.refresh())

    def select_day(self, day: str) -> None:
        self._selected = date.fromisoformat(day)
        self._month = self._selected.replace(day=1)

    def refresh(self, animate: bool = False) -> None:
        first = self._month
        last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
        totals = queries.daily_totals(first.isoformat(), last.isoformat())
        snap = self.ctx.snapshot()
        today = date.today()
        if first <= today <= last and snap.app_id:
            totals[today.isoformat()] = totals.get(today.isoformat(), 0) + snap.uncommitted_ms

        self.month_title.setText(f"{first:%B %Y}")
        self.heatmap.set_month(first, totals)
        self.heatmap.set_selected(self._selected)
        self.next_btn.setEnabled(first < today.replace(day=1))
        self.today_btn.setEnabled(self._selected != today or first != today.replace(day=1))

        total = sum(totals.values())
        active = [v for v in totals.values() if v > 0]
        self.stat_labels["total"].setText(fmt.duration(total, short=True))
        self.stat_labels["avg"].setText(fmt.duration(total / len(active), short=True) if active else "–")
        self.stat_labels["active"].setText(str(len(active)))
        if active:
            best = max(totals.items(), key=lambda kv: kv[1])
            self.stat_labels["best"].setText(f"{fmt.short_date(best[0])} · {fmt.duration(best[1], short=True)}")
        else:
            self.stat_labels["best"].setText("–")
        self.header.set_subtitle(
            f"{fmt.duration(total, short=True)} tracked in {first:%B}" if total else f"Nothing tracked in {first:%B}"
        )
        self._show_day(animate)

    def _show_day(self, animate: bool = False) -> None:
        day = self._selected
        key = day.isoformat()
        apps = queries.top_apps(key, key, limit=None)
        snap = self.ctx.snapshot()
        if day == date.today() and snap.app_id:
            for app in apps:
                if app["app_id"] == snap.app_id:
                    app["focused_ms"] += snap.uncommitted_ms
        total = sum(a["focused_ms"] for a in apps)
        self.day_title.setText(fmt.long_date(day))
        self.day_sub.setText(fmt.relative_day(day) if (date.today() - day).days < 7 else f"{day:%Y}")
        if animate and total and self._day_total:
            count_to(self.day_total, self._day_total, total, _short)
        else:
            self.day_total.setText(fmt.duration(total, short=True) if total else "")
        self._day_total = total

        hours = queries.hourly_totals(key)
        self.day_hours.set_data(
            [
                Bar(f"{h:02d}" if h % 6 == 0 else "", ms, f"{h:02d}:00 · {fmt.duration(ms)}")
                for h, ms in enumerate(hours)
            ],
            highlight=datetime.now().hour if day == date.today() else None,
            empty_text="No activity on this day",
        )
        self.day_hours.setVisible(bool(total))

        clear_layout(self.day_list)
        if not apps:
            self.day_list.addWidget(EmptyState("calendar-days", "No activity", "Nothing was tracked on this day."))
            return
        peak = apps[0]["focused_ms"] or 1
        rows = []
        for app in apps[:12]:
            row = AppRow(
                app,
                fmt.duration(app["focused_ms"], short=True),
                app["focused_ms"] / peak,
                sub=app.get("category") or "",
                extra=f"{app['focused_ms'] / (total or 1):.0%}",
                animate_from=self._fractions.get(app["app_id"], 0.0),
            )
            row.clicked.connect(self.ctx.open_app)
            row.context_requested.connect(self.ctx.app_menu)
            self.day_list.addWidget(row)
            rows.append(row)
        self._fractions = {row.app_id: row.fraction for row in rows}
        if animate:
            motion.stagger_in(rows)
        if len(apps) > 12:
            self.day_list.addWidget(label(f"and {len(apps) - 12} more", "caption"))

    def _on_day(self, day: str) -> None:
        self._selected = date.fromisoformat(day)
        if self._selected.replace(day=1) != self._month:
            self._month = self._selected.replace(day=1)
            self.refresh(animate=True)
        else:
            self.today_btn.setEnabled(self._selected != date.today())
            self._show_day(animate=True)

    def _shift(self, months: int) -> None:
        y, m = self._month.year, self._month.month + months
        y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
        target = date(y, m, 1)
        if target > date.today().replace(day=1):
            return
        self._month = target
        last = calendar.monthrange(y, m)[1]
        self._selected = min(date.today(), target.replace(day=min(self._selected.day, last)))
        self.refresh(animate=True)

    def _go_today(self) -> None:
        self._selected = date.today()
        self._month = self._selected.replace(day=1)
        self.refresh(animate=True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_PageUp:
            self._shift(-1)
        elif event.key() == Qt.Key.Key_PageDown:
            self._shift(1)
        else:
            super().keyPressEvent(event)


def _short(ms: float) -> str:
    return fmt.duration(ms, short=True)
