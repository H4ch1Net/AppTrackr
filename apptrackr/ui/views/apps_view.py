"""Apps: every tracked app for a period, sortable, searchable and filterable."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout

from ...data import db, queries
from .. import fmt, icons, motion
from ..signals import bus
from ..widgets.components import (
    AppRow,
    Card,
    EmptyState,
    IconBinding,
    Page,
    PageHeader,
    SegmentedControl,
    button,
    clear_layout,
    label,
    tone_color,
)

PERIODS = (("Today", 0), ("Last 7 days", 6), ("Last 30 days", 29), ("Last 90 days", 89), ("All time", None))
SORTS = (
    ("Most used", queries.SORT_FOCUSED),
    ("Least used", queries.SORT_LEAST),
    ("Most launched", queries.SORT_OPENS),
    ("Most clicked", queries.SORT_CLICKS),
)


class AppsView(Page):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        self._fractions: dict[int, float] = {}

        self.header = PageHeader("Apps")
        self.add(self.header)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search apps  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search apps")
        self._search_action = self.search.addAction(
            icons.icon("search", tone_color("text_muted")), QLineEdit.ActionPosition.LeadingPosition
        )
        bus.theme_changed.connect(lambda: self._search_action.setIcon(icons.icon("search", tone_color("text_muted"))))
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._user_refresh)
        self.search.textChanged.connect(lambda *_: self._debounce.start())
        bar.addWidget(self.search, 1)

        self.period = QComboBox()
        self.period.setAccessibleName("Period")
        for text, _ in PERIODS:
            self.period.addItem(text)
        self.period.setCurrentIndex(1)
        self.period.currentIndexChanged.connect(self._user_refresh)
        bar.addWidget(self.period)

        self.category = QComboBox()
        self.category.setAccessibleName("Category")
        self.category.addItem("All categories", None)
        for cat in queries.CATEGORIES:
            self.category.addItem(cat, cat)
        self.category.currentIndexChanged.connect(self._user_refresh)
        bar.addWidget(self.category)

        self.favorites = QPushButton("Favorites")
        self.favorites.setCheckable(True)
        self.favorites.setProperty("kind", "ghost")
        self.favorites.setToolTip("Show only favorite apps")
        IconBinding.attach(self.favorites, "star", "text_dim", checked_tone="gold")
        self.favorites.toggled.connect(self._user_refresh)
        bar.addWidget(self.favorites)
        self.add(bar)

        self.sort = SegmentedControl([s[0] for s in SORTS])
        self.sort.changed.connect(self._user_refresh)
        sort_row = QHBoxLayout()
        sort_row.addWidget(self.sort)
        sort_row.addStretch(1)
        self.summary = label("", "caption")
        sort_row.addWidget(self.summary)
        self.add(sort_row)

        self.card = Card(padding=8, spacing=2)
        self.list = QVBoxLayout()
        self.list.setSpacing(2)
        self.card.body.addLayout(self.list)
        self.add(self.card)

        self.hidden_note = button("", kind="link", on_click=lambda: ctx.navigate("settings"))
        self.add(self.hidden_note)
        self.layout_.addStretch(1)

        bus.data_changed.connect(lambda: self.isVisible() and self.refresh())

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def set_period(self, index: int) -> None:
        self.period.setCurrentIndex(index)

    def _user_refresh(self, *_args) -> None:
        self.refresh(animate=True)

    def refresh(self, animate: bool = False) -> None:
        """Rebuild the list. *animate* staggers rows in after a user-driven change."""
        _label, days = PERIODS[self.period.currentIndex()]
        end = queries.today_str()
        start = queries.days_ago(days) if days is not None else "0000-01-01"
        sort = SORTS[self.sort.current()][1]
        apps = queries.top_apps(
            start,
            end,
            sort=sort,
            limit=None,
            category=self.category.currentData(),
            favorites_only=self.favorites.isChecked(),
            search=self.search.text(),
        )

        total_ms = sum(a["focused_ms"] for a in apps)
        count = len(apps)
        self.header.set_subtitle(
            f"{count} app{'s' if count != 1 else ''} · {fmt.duration(total_ms, short=True)} "
            f"focused · {PERIODS[self.period.currentIndex()][0].lower()}"
        )
        self.summary.setText("Right-click an app for quick actions")

        clear_layout(self.list)
        if not apps:
            self.list.addWidget(self._empty_state(sort))
        else:
            metric = {queries.SORT_OPENS: "opens_count", queries.SORT_CLICKS: "clicks_count"}.get(sort, "focused_ms")
            peak = max(a[metric] for a in apps) or 1
            rows = [self._row(app, sort, metric, peak, total_ms) for app in apps]
            for row in rows:
                self.list.addWidget(row)
            self._fractions = {row.app_id: row.fraction for row in rows}
            if animate:
                motion.stagger_in(rows)

        hidden = len(queries.hidden_apps())
        self.hidden_note.setText(f"{hidden} excluded app{'s are' if hidden != 1 else ' is'} hidden. Manage in Settings")
        self.hidden_note.setVisible(hidden > 0)

    def _row(self, app: dict, sort: str, metric: str, peak: int, total_ms: int) -> AppRow:
        opens = app["opens_count"]
        launches = f"{opens} launch{'es' if opens != 1 else ''}"
        if sort == queries.SORT_OPENS:
            value = launches
            sub = fmt.duration(app["focused_ms"], short=True) + " focused"
        elif sort == queries.SORT_CLICKS:
            value = f"{fmt.count(app['clicks_count'])} clicks"
            sub = fmt.duration(app["focused_ms"], short=True) + " focused"
        else:
            value = fmt.duration(app["focused_ms"], short=True)
            days = app.get("active_days") or 0
            sub = " · ".join(
                filter(
                    None,
                    [
                        app.get("category"),
                        launches if opens else "",
                        f"{days} active day{'s' if days != 1 else ''}" if days > 1 else "",
                    ],
                )
            )
        extra = f"{app['focused_ms'] / total_ms:.0%}" if total_ms and metric == "focused_ms" else ""
        row = AppRow(
            app,
            value,
            app[metric] / peak,
            sub=sub,
            extra=extra,
            animate_from=self._fractions.get(app["app_id"], 0.0),
        )
        row.clicked.connect(self.ctx.open_app)
        row.context_requested.connect(self.ctx.app_menu)
        return row

    def _empty_state(self, sort: str) -> EmptyState:
        if self.search.text().strip():
            return EmptyState(
                "search",
                f"No apps match “{self.search.text().strip()}”",
                "Try a different name or clear the filters.",
                "Clear search",
                lambda: self.search.clear(),
            )
        if sort == queries.SORT_CLICKS and not db.get_bool("track_clicks"):
            return EmptyState(
                "mouse-pointer-click",
                "Click counting is off",
                "Turn it on in Settings to see which apps you click the most.",
                "Open Settings",
                lambda: self.ctx.navigate("settings"),
            )
        if self.favorites.isChecked():
            return EmptyState(
                "star",
                "No favorites in this period",
                "Mark apps as favorites from their detail page or the right-click menu. "
                "Favorites also drive your daily streak.",
            )
        if self.category.currentData():
            return EmptyState(
                "layout-grid",
                f"No {self.category.currentText()} apps in this period",
                "Assign categories from an app's detail page.",
            )
        if not self.ctx.tracker.supported and not queries.first_tracked_day():
            return EmptyState(
                "power",
                "Nothing tracked on this platform",
                "Foreground tracking runs on Windows. Start with --demo to explore sample data.",
            )
        return EmptyState(
            "layout-grid", "No apps tracked in this period", "Use your computer as usual and apps will appear here."
        )
