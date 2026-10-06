"""Settings. Every control applies immediately."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QVBoxLayout,
    QWidget,
)

from ... import APP_NAME, REPO_URL, __version__
from ...core import autostart
from ...data import db, export, queries
from ...game import economy
from ...updater import apply as updater_apply
from ...updater import check as updater
from .. import fmt, fonts, motion, theme
from ..signals import bus, run_async
from ..widgets.charts import _column
from ..widgets.components import (
    Card,
    ElidedLabel,
    Page,
    PageHeader,
    SegmentedControl,
    SettingRow,
    Toggle,
    button,
    clear_layout,
    divider,
    eyebrow,
    label,
)
from ..widgets.controls import CheckBox, TickSlider

IDLE_CHOICES = (  # slider stops, shortest first; 0 turns idle detection off
    ("1m", 60),
    ("2m", 120),
    ("3m", 180),
    ("5m", 300),
    ("10m", 600),
    ("15m", 900),
    ("30m", 1800),
    ("Never", 0),
)
NOTIFY_KINDS = (("limits", "Daily limits"), ("streaks", "Streaks"), ("updates", "Updates"))
SHORTCUTS = (
    ("Ctrl+1 … Ctrl+5", "Switch page"),
    ("Ctrl+,", "Settings"),
    ("Ctrl+F", "Search apps"),
    ("Ctrl+Shift+P", "Pause or resume tracking"),
    ("Esc / Alt+Left", "Back from an app"),
    ("F5", "Refresh"),
    ("Ctrl+Q", "Quit"),
)


class _ProgressRelay(QObject):
    progress = Signal(int, int)


PALETTE_NOTES = {
    "Graphite": "Warm graphite. The default.",
    "Carbon": "True black for OLED screens.",
    "Midnight": "Deep blue night panel.",
    "Paper": "Warm paper. The default.",
    "Porcelain": "Cool, neutral white.",
    "Sage": "Soft green-grey.",
}


class _Selectable(QAbstractButton):
    """Checkable tile whose hover and selection states ease in and out."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._hover = 0.0
        self._sel = 0.0
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, on: bool) -> None:
        motion.tween(self, self._sel, 1.0 if on else 0.0, motion.GENTLE, self._set_sel, motion.DECELERATE, key="sel")

    def set_checked_silently(self, on: bool) -> None:
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self._sel = 1.0 if on else 0.0
        self.update()

    def _set_sel(self, v: float) -> None:
        self._sel = v
        self.update()

    def _set_hover(self, v: float) -> None:
        self._hover = v
        self.update()

    def enterEvent(self, event):
        motion.tween(self, self._hover, 1.0, motion.FAST, self._set_hover, motion.DECELERATE, key="hover")
        super().enterEvent(event)

    def leaveEvent(self, event):
        motion.tween(self, self._hover, 0.0, motion.NORMAL, self._set_hover, motion.EASY_EASE, key="hover")
        super().leaveEvent(event)


class Swatch(_Selectable):
    """Accent picker: the accent as it will render on the current palette."""

    def __init__(self, name: str, color: str, parent=None):
        super().__init__(parent)
        self.name = name
        self.color = color
        self.setToolTip(name)
        self.setAccessibleName(f"{name} accent")

    def sizeHint(self) -> QSize:
        return QSize(30, 30)

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._sel > 0.01 or self.hasFocus():
            ring = QColor(t.text if self.isChecked() else t.accent)
            ring.setAlphaF(max(self._sel, 1.0 if self.hasFocus() else 0.0))
            p.setPen(QPen(ring, 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(1.5, 1.5, 27, 27), 5, 5)
        inset = 7 - 1.5 * self._hover + 1.0 * self._sel
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.fit_accent(self.color, theme.current())))
        p.drawRoundedRect(QRectF(inset, inset, 30 - 2 * inset, 30 - 2 * inset), 3, 3)


class ThemeTile(_Selectable):
    """A palette rendered as a miniature AppTrackr window."""

    W, H = 168, 104

    def __init__(self, palette: str, parent=None):
        super().__init__(parent)
        self.palette = palette
        self.active = False  # palette currently on screen (vs. chosen for the other mode)
        self.setToolTip(f"{palette}: {PALETTE_NOTES.get(palette, '')}")
        self.setAccessibleName(f"{palette} palette")

    def sizeHint(self) -> QSize:
        return QSize(self.W, self.H + 40)

    def paintEvent(self, _event):
        t = theme.current()
        pv = theme.build(self.palette, theme.accent_name())
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        frame = QRectF(1, 1, self.W - 2, self.H - 2)
        ring = QColor(t.accent if self.active else t.text_dim)
        edge = QColor(t.border_strong)
        if self._hover:
            edge = QColor(theme._mix(t.border_strong, t.text_muted, self._hover))
        p.setPen(QPen(edge, 1))
        p.setBrush(QColor(pv.window))
        p.drawRoundedRect(frame, 6, 6)
        # Sidebar with nav lines; the first is the current page.
        side = QRectF(frame.left() + 1, frame.top() + 1, 34, frame.height() - 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(pv.sidebar))
        p.drawRoundedRect(side, 5, 5)
        p.drawRect(QRectF(side.right() - 6, side.top(), 6, side.height()))
        for i in range(4):
            y = side.top() + 16 + i * 11
            p.setBrush(QColor(pv.surface_alt if i == 0 else pv.sidebar))
            p.drawRoundedRect(QRectF(side.left() + 4, y - 3, side.width() - 8, 8), 2, 2)
            p.setBrush(QColor(pv.text if i == 0 else pv.text_muted))
            p.drawRoundedRect(QRectF(side.left() + 9, y, 14 if i else 18, 2), 1, 1)
            if i == 0:
                p.setBrush(QColor(pv.accent))
                p.drawRect(QRectF(side.left() + 4, y - 3, 1.5, 8))
        # Panel with a hero number line and bars: history in ink, now in the accent.
        panel = QRectF(side.right() + 8, frame.top() + 10, frame.right() - side.right() - 18, frame.height() - 20)
        p.setPen(QPen(QColor(pv.border), 1))
        p.setBrush(QColor(pv.surface))
        p.drawRoundedRect(panel, 4, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(pv.text_muted))
        p.drawRoundedRect(QRectF(panel.left() + 8, panel.top() + 8, 26, 2), 1, 1)
        p.setBrush(QColor(pv.text))
        p.drawRoundedRect(QRectF(panel.left() + 8, panel.top() + 15, 44, 6), 2, 2)
        base = panel.bottom() - 9
        p.setPen(QPen(QColor(pv.border), 1))
        p.drawLine(QPointF(panel.left() + 8, base + 0.5), QPointF(panel.right() - 8, base + 0.5))
        p.setPen(Qt.PenStyle.NoPen)
        heights = (14, 26, 30, 18, 9, 22, 28, 12)
        slot = (panel.width() - 16) / len(heights)
        for i, h in enumerate(heights):
            p.setBrush(QColor(pv.accent if i == len(heights) - 1 else pv.ink))
            p.drawPath(_column(panel.left() + 8 + i * slot + slot * 0.2, base, slot * 0.6, h, 1.5))
        # Selection ring eases in around the preview.
        if self._sel > 0.01:
            ring.setAlphaF(self._sel)
            p.setPen(QPen(ring, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            grow = 2 * (1 - self._sel)
            p.drawRoundedRect(frame.adjusted(-grow, -grow, grow, grow).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        if self.hasFocus():
            p.setPen(QPen(QColor(t.accent), 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(frame.adjusted(-3, -3, 3, 3), 8, 8)
        # Caption: engraved name and a one-line note.
        p.setPen(QColor(t.text if self.isChecked() else t.text_dim))
        p.setFont(fonts.mono(10, 500, 8))
        p.drawText(QPointF(2, self.H + 16), self.palette.upper())
        p.setPen(QColor(t.text_muted))
        p.setFont(fonts.sans(11))
        p.drawText(QPointF(2, self.H + 32), PALETTE_NOTES.get(self.palette, ""))


class SettingsView(Page):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        self.add(PageHeader("Settings", "Changes are saved automatically.", kicker="Preferences"))

        self.update_banner = Card(padding=14)
        self.update_banner.setProperty("card", False)
        self.update_banner.setProperty("banner", True)
        banner_row = QHBoxLayout()
        self.update_text = label("", wrap=True)
        banner_row.addWidget(self.update_text, 1)
        self.update_btn = button("Download and install", kind="primary", on_click=self._install_update)
        banner_row.addWidget(self.update_btn)
        self.update_banner.body.addLayout(banner_row)
        self.update_banner.hide()
        self.add(self.update_banner)

        self._build_general()
        self._build_tracking()
        self._build_appearance()
        self._build_data()
        self._build_updates()
        self._build_about()
        self.layout_.addStretch(1)

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _build_general(self) -> None:
        card = Card("General", index=1)
        self.autostart = Toggle()
        self.autostart.toggled.connect(self._set_autostart)
        desc = "Starts in the tray when you sign in to Windows."
        if not autostart.supported():
            desc = "Available on Windows."
            self.autostart.setEnabled(False)
        card.body.addWidget(SettingRow("Launch at startup", desc, self.autostart))
        card.body.addWidget(divider())
        self.tray = Toggle()
        self.tray.toggled.connect(lambda on: self._save("minimize_to_tray", on, "Close behavior updated"))
        card.body.addWidget(
            SettingRow(
                "Keep running when closed",
                "Closing the window hides it to the system tray so tracking continues.",
                self.tray,
            )
        )
        card.body.addWidget(divider())
        self.notifications = Toggle()
        self.notifications.toggled.connect(self._set_notifications)
        card.body.addWidget(
            SettingRow("Notifications", "Shown by Windows while the AppTrackr window is hidden.", self.notifications)
        )
        kinds = QHBoxLayout()
        kinds.setContentsMargins(0, 0, 0, 6)
        kinds.setSpacing(20)
        self.notify_boxes: dict[str, CheckBox] = {}
        for key, text in NOTIFY_KINDS:
            box = CheckBox(text)
            box.toggled.connect(
                lambda on, k=key, t=text: self._save(f"notify_{k}", on, f"{t} notifications {'on' if on else 'off'}")
            )
            self.notify_boxes[key] = box
            kinds.addWidget(box)
        kinds.addStretch(1)
        card.body.addLayout(kinds)
        card.body.addWidget(divider())
        self.rewards = Toggle()
        self.rewards.toggled.connect(self._set_rewards)
        card.body.addWidget(
            SettingRow(
                "Focus game",
                "Flow, levels and the village. Turning this off hides both pages; nothing is deleted.",
                self.rewards,
            )
        )
        card.body.addWidget(divider())
        self.goal = TickSlider([(fmt.duration(m * 60_000, short=True), m) for m in economy.GOAL_CHOICES])
        self.goal.setAccessibleName("Daily focus goal")
        self.goal.committed.connect(self._set_goal)
        card.body.addWidget(
            SettingRow(
                "Daily focus goal",
                "Time in your focus apps that counts as a streak day and opens the daily chest.",
                self.goal,
            )
        )
        self.add(card)

    def _build_tracking(self) -> None:
        card = Card("Tracking", index=2)
        self.idle = TickSlider(list(IDLE_CHOICES))
        self.idle.setAccessibleName("Idle timeout")
        self.idle.committed.connect(self._set_idle)
        card.body.addWidget(
            SettingRow(
                "Idle timeout",
                "Stop counting after this long without keyboard or mouse "
                "input. Time up to your last input still counts.",
                self.idle,
            )
        )
        card.body.addWidget(divider())
        self.clicks = Toggle()
        self.clicks.toggled.connect(self._set_clicks)
        card.body.addWidget(
            SettingRow(
                "Count mouse clicks",
                "Stores a click count per app per day. Positions, buttons and keystrokes are never recorded.",
                self.clicks,
            )
        )
        card.body.addWidget(divider())
        card.body.addWidget(
            SettingRow(
                "Excluded apps",
                "Excluded apps are not tracked and are hidden everywhere. Right-click any app to exclude it.",
            )
        )
        self.excluded = QVBoxLayout()
        self.excluded.setSpacing(4)
        card.body.addLayout(self.excluded)
        self.add(card)

    def _build_appearance(self) -> None:
        card = Card("Appearance", index=3)
        self.mode = SegmentedControl(["Dark", "Light", "System"])
        self.mode.changed.connect(self._set_mode)
        card.body.addWidget(SettingRow("Mode", "System follows Windows' app mode.", self.mode))
        card.body.addWidget(divider())
        card.body.addWidget(
            SettingRow("Palette", "One for dark mode and one for light mode. System switches between them.")
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        self.tiles: dict[str, ThemeTile] = {}
        for row, (kind, names) in enumerate((("Dark", theme.DARK_PALETTES), ("Light", theme.LIGHT_PALETTES))):
            heading = eyebrow(kind)
            heading.setContentsMargins(0, 12 if row else 2, 0, 0)
            grid.addWidget(heading, row * 2, 0, 1, 3)
            for col, name in enumerate(names):
                tile = ThemeTile(name)
                tile.clicked.connect(lambda _=False, n=name: self._set_palette(n))
                self.tiles[name] = tile
                grid.addWidget(tile, row * 2 + 1, col, Qt.AlignmentFlag.AlignLeft)
        grid.setColumnStretch(3, 1)
        card.body.addLayout(grid)
        card.body.addWidget(divider())
        swatches = QWidget()
        lay = QHBoxLayout(swatches)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.swatch_group = QButtonGroup(self)
        self.swatches: dict[str, Swatch] = {}
        for name, color in theme.ACCENTS.items():
            sw = Swatch(name, color)
            self.swatch_group.addButton(sw)
            self.swatches[name] = sw
            sw.clicked.connect(lambda _=False, n=name: self._set_accent(n))
            lay.addWidget(sw)
        card.body.addWidget(
            SettingRow("Accent color", "Marks what is live, selected or current. Adjusted per palette.", swatches)
        )
        card.body.addWidget(divider())
        self.animations = Toggle()
        self.animations.toggled.connect(self._set_animations)
        card.body.addWidget(
            SettingRow(
                "Animations",
                "Transitions, counters and chart motion. Follows Windows' Animation effects setting until changed.",
                self.animations,
            )
        )
        self.add(card)

    def _build_data(self) -> None:
        card = Card("Data", "Usage is stored only on this computer.", index=4)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(button("Export CSV", icon="download", on_click=lambda: self._export("csv")))
        row.addWidget(button("Export JSON", icon="download", on_click=lambda: self._export("json")))
        row.addWidget(button("Back up…", icon="database", on_click=self._backup))
        row.addWidget(button("Restore…", icon="archive-restore", on_click=self._restore))
        row.addStretch(1)
        row.addWidget(button("Open data folder", kind="ghost", icon="folder-open", on_click=self._open_folder))
        card.body.addLayout(row)
        self.db_path = ElidedLabel("", "caption")  # long data paths must not widen the page
        card.body.addWidget(self.db_path)
        self.add(card)

    def _build_updates(self) -> None:
        card = Card("Updates", index=5)
        self.auto_update = Toggle()
        self.auto_update.toggled.connect(lambda on: self._save("auto_update_check", on))
        card.body.addWidget(
            SettingRow(
                "Check for updates automatically",
                "Asks GitHub for the latest release once a day. Nothing else is sent.",
                self.auto_update,
            )
        )
        card.body.addWidget(divider())
        check_row = QHBoxLayout()
        self.version_label = label(f"{APP_NAME} {__version__}")
        self.version_label.setStyleSheet("font-weight: 600;")
        check_row.addWidget(self.version_label)
        self.update_status = label("", "caption")
        check_row.addWidget(self.update_status, 1)
        self.check_btn = button("Check now", icon="refresh-cw", on_click=self._check_updates)
        check_row.addWidget(self.check_btn)
        card.body.addLayout(check_row)
        self.feed = QLineEdit()
        self.feed.setPlaceholderText(updater.DEFAULT_UPDATE_URL)
        self.feed.setAccessibleName("Update feed URL")
        self.feed.editingFinished.connect(lambda: self._save("update_url", self.feed.text().strip()))
        card.body.addWidget(
            SettingRow("Release feed", "GitHub releases API URL. Leave empty for the official releases.", None)
        )
        card.body.addWidget(self.feed)
        self.add(card)

    def _build_about(self) -> None:
        card = Card("About", index=6)
        links = QHBoxLayout()
        links.setSpacing(16)
        for text, url in (
            ("Source code", REPO_URL),
            ("Report an issue", REPO_URL + "/issues"),
            ("Releases", REPO_URL + "/releases"),
            ("License (MIT)", REPO_URL + "/blob/main/LICENSE"),
        ):
            links.addWidget(button(text, kind="link", on_click=lambda u=url: QDesktopServices.openUrl(QUrl(u))))
        links.addStretch(1)
        card.body.addLayout(links)
        card.body.addWidget(label("KEYBOARD SHORTCUTS", "eyebrow"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        for i, (keys, action) in enumerate(SHORTCUTS):
            k = label(keys)
            k.setObjectName("kbd")
            grid.addWidget(k, i // 2, (i % 2) * 2, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(label(action, "dim"), i // 2, (i % 2) * 2 + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        card.body.addLayout(grid)
        self.add(card)

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        self.autostart.set_silently(autostart.is_enabled())
        self.tray.set_silently(db.get_bool("minimize_to_tray", True))
        self.notifications.set_silently(db.get_bool("notifications_enabled", True))
        self.rewards.set_silently(db.get_bool("rewards_enabled", True))
        goal = db.get_int("focus_goal_min", economy.DEFAULT_GOAL_MIN)
        if self.goal.index_of(goal) < 0:  # a value set outside the slider keeps its own stop
            stops = sorted({*economy.GOAL_CHOICES, goal})
            self.goal.set_stops([(fmt.duration(m * 60_000, short=True), m) for m in stops])
        self.goal.set_stop_value(goal)
        self.clicks.set_silently(db.get_bool("track_clicks"))
        self.auto_update.set_silently(db.get_bool("auto_update_check", True))
        self.feed.setText(db.get_setting("update_url", ""))

        idle = db.get_int("idle_threshold_sec", 300)
        if self.idle.index_of(idle) < 0:  # a value set outside the slider keeps its own stop
            stops = [s for s in IDLE_CHOICES if s[1]] + [(fmt.duration(idle * 1000, short=True), idle)]
            self.idle.set_stops(sorted(stops, key=lambda s: s[1]) + [IDLE_CHOICES[-1]])
        self.idle.set_stop_value(idle)
        for key, box in self.notify_boxes.items():
            box.set_silently(db.get_bool(f"notify_{key}", True))
            box.setEnabled(self.notifications.isChecked())

        self.animations.set_silently(motion.preference())
        self.mode.set_current(theme.MODES.index(theme.mode()))
        self.swatches[theme.accent_name()].setChecked(True)
        self._sync_tiles()
        self.db_path.setText(f"Database: {db.db_path()}")
        self._fill_excluded()

        info = self.ctx.update_info
        self.update_banner.setVisible(info is not None)
        if info:
            self.update_text.setText(f"<b>{APP_NAME} {info.version} is available.</b> You have {__version__}.")
            self.update_btn.setVisible(bool(info.download_url) and sys.platform.startswith("win"))

    def _fill_excluded(self) -> None:
        clear_layout(self.excluded)
        hidden = queries.hidden_apps()
        if not hidden:
            self.excluded.addWidget(label("No excluded apps.", "muted"))
            return
        for app in hidden:
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(10)
            lay.addWidget(label(app["name"]))
            lay.addWidget(label(app["exe_name"], "caption"), 1)
            lay.addWidget(button("Track again", kind="ghost", on_click=lambda a=app, r=row: self._include(a, r)))
            self.excluded.addWidget(row)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _save(self, key: str, value, message: str = "Saved") -> None:
        db.set_setting(key, value)
        self.ctx.toast(message)

    def _set_autostart(self, on: bool) -> None:
        if autostart.set_enabled(on):
            self.ctx.toast("AppTrackr will start when you sign in" if on else "Launch at startup turned off")
        else:
            self.autostart.set_silently(autostart.is_enabled())
            self.ctx.toast("Could not change the startup setting", "danger")

    def _set_rewards(self, on: bool) -> None:
        db.set_setting("rewards_enabled", on)
        self.ctx.window.apply_rewards_visibility()
        self.ctx.toast("Focus game turned on" if on else "Focus game turned off")

    def _set_goal(self, minutes: int) -> None:
        db.set_setting("focus_goal_min", minutes)
        bus.rewards_changed.emit()
        self.ctx.toast(f"Daily focus goal set to {fmt.duration(minutes * 60_000)}")

    def _set_idle(self, sec: int) -> None:
        db.set_setting("idle_threshold_sec", sec)
        self.ctx.tracker.reload_settings()
        self.ctx.toast("Idle detection off" if not sec else f"Idle after {fmt.duration(sec * 1000)}")

    def _set_notifications(self, on: bool) -> None:
        self._save("notifications_enabled", on)
        for box in self.notify_boxes.values():
            box.setEnabled(on)

    def _set_clicks(self, on: bool) -> None:
        db.set_setting("track_clicks", on)
        if self.ctx.clicks is not None:
            self.ctx.clicks.set_enabled(on)
        self.ctx.toast("Click counting on" if on else "Click counting off")

    def _set_animations(self, on: bool) -> None:
        motion.set_enabled(on)
        self.ctx.toast("Animations on" if on else "Animations off")

    def _set_mode(self, index: int) -> None:
        db.set_setting("ui_mode", theme.MODES[index])
        self.ctx.window.apply_theme()

    def _set_accent(self, name: str) -> None:
        db.set_setting("ui_theme", name)
        self.ctx.window.apply_theme()

    def _set_palette(self, name: str) -> None:
        kind = "dark" if name in theme.DARK_PALETTES else "light"
        db.set_setting(f"ui_{kind}_palette", name)
        if theme.mode() != "system":
            db.set_setting("ui_mode", kind)  # picking a palette shows it
        self.ctx.window.apply_theme()
        self._sync_tiles()

    def _sync_tiles(self) -> None:
        shown = theme.current().name
        chosen = {theme.palette_choice("dark"), theme.palette_choice("light")}
        for name, tile in self.tiles.items():
            tile.active = name == shown
            if tile.isChecked() != (name in chosen):
                tile.setChecked(name in chosen)
            tile.update()

    def _include(self, app: dict, row: QWidget) -> None:
        queries.set_hidden(app["app_id"], False)
        self.ctx.tracker.reload_settings()
        bus.data_changed.emit()
        motion.collapse(row, self._fill_excluded)
        self.ctx.toast(f"{app['name']} is tracked again")

    # Data ----------------------------------------------------------------

    def _export(self, kind: str) -> None:
        default = f"apptrackr-{queries.today_str()}.{kind}"
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {kind.upper()}", default, "CSV (*.csv)" if kind == "csv" else "JSON (*.json)"
        )
        if not path:
            return
        try:
            n = export.export_csv(path) if kind == "csv" else export.export_json(path)
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        self.ctx.toast(
            f"Exported {n:,} rows",
            action="Show",
            callback=lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent))),
        )

    def _backup(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Back up database",
            f"apptrackr-backup-{queries.today_str()}.sqlite",
            "SQLite database (*.sqlite *.db)",
        )
        if not path:
            return
        try:
            export.backup_db(path)
        except Exception as exc:
            QMessageBox.warning(self, "Backup failed", str(exc))
            return
        self.ctx.toast("Backup saved")

    def _restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Restore backup", "", "SQLite database (*.sqlite *.db);;All files (*)"
        )
        if not path:
            return
        try:
            export.validate_backup(path)
        except export.RestoreError as exc:
            QMessageBox.warning(self, "Cannot restore", str(exc))
            return
        reply = QMessageBox.warning(
            self,
            "Replace current data?",
            "Restoring replaces everything AppTrackr has recorded with the contents of the backup. "
            "Consider backing up first.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        tracker = self.ctx.tracker
        was_paused = tracker.paused
        paused_until = tracker.snapshot().paused_until
        tracker.pause()
        try:
            export.restore_db(path)
        except Exception as exc:
            QMessageBox.warning(self, "Restore failed", str(exc))
            return
        finally:
            tracker.resume()
            if was_paused:
                remaining = (paused_until - time.time()) / 60 if paused_until else None
                if remaining is None or remaining > 0:
                    tracker.pause(remaining)
            tracker.reload_settings()
        bus.data_changed.emit()
        bus.rewards_changed.emit()
        self.ctx.window.apply_theme()
        self.refresh()
        self.ctx.toast("Backup restored")

    def _open_folder(self) -> None:
        folder = db.db_path().parent
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # Updates -------------------------------------------------------------

    def _check_updates(self) -> None:
        self.check_btn.setEnabled(False)
        self.update_status.setText("Checking…")
        url = self.feed.text().strip()

        def done(info):
            self.check_btn.setEnabled(True)
            if info is None:
                self.update_status.setText(f"You're up to date (checked {fmt.time_of_day(time.time())})")
                return
            self.update_status.setText(f"Version {info.version} is available")
            self.ctx.window.set_update_available(info)
            self.refresh()

        def failed(exc):
            self.check_btn.setEnabled(True)
            self.update_status.setText(str(exc) if isinstance(exc, updater.UpdateError) else "Update check failed")

        run_async(lambda: updater.check_for_update(url), done, failed)

    def _install_update(self) -> None:
        info = self.ctx.update_info
        if not info:
            return
        if not info.download_url:
            QDesktopServices.openUrl(QUrl(info.page_url or REPO_URL + "/releases"))
            return
        cancel = threading.Event()
        dialog = QProgressDialog(f"Downloading {APP_NAME} {info.version}…", "Cancel", 0, 1000, self)
        dialog.setWindowTitle("Updating")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.canceled.connect(cancel.set)
        relay = _ProgressRelay()
        relay.progress.connect(lambda done_, total: dialog.setValue(int(1000 * done_ / total)) if total else None)

        def finished(path):
            dialog.close()
            if (
                QMessageBox.question(
                    self, "Install update", f"{APP_NAME} will close and the installer will start. Continue?"
                )
                == QMessageBox.StandardButton.Yes
            ):
                updater_apply.launch_installer(path)
                self.ctx.window.quit()

        def failed(exc):
            dialog.close()
            if not isinstance(exc, updater_apply.DownloadCancelled):
                QMessageBox.warning(self, "Download failed", f"The update could not be downloaded.\n\n{exc}")

        run_async(lambda: updater_apply.download(info.download_url, relay.progress.emit, cancel), finished, failed)
        self._relay = relay
