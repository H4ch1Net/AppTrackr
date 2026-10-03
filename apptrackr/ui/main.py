"""Main window: sidebar navigation, page stack, tray icon, shortcuts and background timers."""

from __future__ import annotations

import logging
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__, paths
from ..core import tracker as trk
from ..core.limits import LimitMonitor
from ..data import db, queries
from ..rewards import engine as rewards
from ..updater import check as updater
from . import fmt, icons, theme
from .signals import bus, run_async
from .widgets.components import Badge, IconBinding, Toast, label, tone_color

log = logging.getLogger(__name__)

PAGES = ("dashboard", "calendar", "apps", "rewards", "village", "settings", "app")
NAV = (
    ("dashboard", "Dashboard", "layout-dashboard"),
    ("calendar", "Calendar", "calendar-days"),
    ("apps", "Apps", "layout-grid"),
    ("rewards", "Rewards", "gift"),
    ("village", "Village", "castle"),
)


class AppContext:
    """Services and navigation shared with every view."""

    def __init__(self, window: MainWindow, tracker, clicks, demo: bool):
        self.window = window
        self.tracker = tracker
        self.clicks = clicks
        self.demo = demo
        self.update_info: updater.UpdateInfo | None = None

    def navigate(self, page: str) -> None:
        self.window.show_page(page)

    def open_app(self, app_id: int) -> None:
        self.window.open_app(app_id)

    def toast(self, text: str, tone: str = "success", action: str = "", callback: Callable | None = None) -> None:
        self.window.toast.show_message(text, tone, action, callback)

    def snapshot(self) -> trk.Snapshot:
        return self.tracker.snapshot()

    def app_menu(self, app_id: int, pos: QPoint) -> None:
        self.window.show_app_menu(app_id, pos)

    def open_day(self, day: str) -> None:
        self.window.open_day(day)


class MainWindow(QMainWindow):
    def __init__(self, tracker, clicks=None, demo: bool = False):
        super().__init__()
        self.ctx = AppContext(self, tracker, clicks, demo)
        self._tracker = tracker
        self._history: list[str] = []
        self._current = "dashboard"
        self._limits = LimitMonitor()
        self._quitting = False

        self.setWindowTitle(APP_NAME + (" (demo)" if demo else ""))
        self.setWindowIcon(icons.logo_icon())
        self.setMinimumSize(980, 640)
        self.resize(1240, 800)

        self._build()
        self._setup_tray()
        self._setup_shortcuts()
        self.toast = Toast(self.centralWidget())
        bus.toast.connect(lambda text, tone: self.toast.show_message(text, tone))
        bus.rewards_changed.connect(self._update_badges)
        bus.theme_changed.connect(self._refresh_status)

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(1000)
        self._slow_timer = QTimer(self)
        self._slow_timer.timeout.connect(self._slow_tick)
        self._slow_timer.start(30_000)

        self.apply_rewards_visibility()
        self.show_page("dashboard")
        QTimer.singleShot(1500, self._slow_tick)
        QTimer.singleShot(10_000, self._startup_update_check)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        from .views.app_detail import AppDetailView
        from .views.apps_view import AppsView
        from .views.calendar_view import CalendarView
        from .views.dashboard import DashboardView
        from .views.rewards_view import RewardsView
        from .views.settings_view import SettingsView
        from .views.village_view import VillageView

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        self._stack = QStackedWidget()
        self._stack.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._views = {
            "dashboard": DashboardView(self.ctx),
            "calendar": CalendarView(self.ctx),
            "apps": AppsView(self.ctx),
            "rewards": RewardsView(self.ctx),
            "village": VillageView(self.ctx),
            "settings": SettingsView(self.ctx),
            "app": AppDetailView(self.ctx),
        }
        for view in self._views.values():
            self._stack.addWidget(view)
        root.addWidget(self._stack, 1)

    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(216)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(12, 18, 12, 14)
        lay.setSpacing(2)

        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 0, 0)
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(icons.logo_pixmap(28))
        brand.addWidget(logo)
        name = QLabel(APP_NAME)
        name.setObjectName("brand")
        brand.addWidget(name, 1)
        lay.addLayout(brand)
        lay.addSpacing(18)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_buttons: dict[str, QPushButton] = {}
        self._badges: dict[str, Badge] = {}
        for i, (key, text, icon) in enumerate(NAV, start=1):
            lay.addWidget(self._nav_button(key, text, icon, f"Ctrl+{i}"))
        lay.addStretch(1)
        lay.addWidget(self._nav_button("settings", "Settings", "settings", "Ctrl+,"))
        lay.addSpacing(10)

        self._status = QPushButton()
        self._status.setObjectName("statusPill")
        self._status.setCursor(Qt.CursorShape.PointingHandCursor)
        self._status.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._status.setToolTip("Pause or resume tracking (Ctrl+Shift+P)")
        self._status.clicked.connect(self.toggle_pause)
        lay.addWidget(self._status)

        self._version = label(f"v{__version__}", "caption")
        self._version.setContentsMargins(8, 8, 0, 0)
        self._version.setTextFormat(Qt.TextFormat.RichText)
        self._version.linkActivated.connect(lambda *_: self.show_page("settings"))
        lay.addWidget(self._version)
        return side

    def _nav_button(self, key: str, text: str, icon: str, shortcut: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setProperty("nav", True)
        btn.setCheckable(True)
        btn.setFixedHeight(38)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        btn.setToolTip(f"{text} ({shortcut})")
        IconBinding.attach(btn, icon, "text_muted", 17, checked_tone="accent_text")
        btn.clicked.connect(lambda *_: self.show_page(key))
        badge = Badge(btn)
        self._badges[key] = badge
        btn.installEventFilter(self)
        self._nav_group.addButton(btn)
        self._nav_buttons[key] = btn
        return btn

    def eventFilter(self, obj, event):
        if event.type() == event.Type.Resize and isinstance(obj, QPushButton):
            for key, btn in self._nav_buttons.items():
                if btn is obj:
                    badge = self._badges[key]
                    badge.adjustSize()
                    badge.move(btn.width() - badge.width() - 10, (btn.height() - badge.height()) // 2)
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def show_page(self, key: str, remember: bool = True) -> None:
        if key not in self._views:
            return
        if remember and key != self._current and self._current != "app":
            self._history = [self._current]
        self._current = key
        view = self._views[key]
        self._stack.setCurrentWidget(view)
        btn = self._nav_buttons.get(key)
        if btn:
            btn.setChecked(True)
        if hasattr(view, "refresh"):
            view.refresh()

    def open_app(self, app_id: int) -> None:
        if self._current != "app":
            self._history = [self._current]
        self._views["app"].load_app(app_id)
        self._current = "app"
        self._stack.setCurrentWidget(self._views["app"])
        for btn in self._nav_buttons.values():
            if btn.isChecked():
                self._nav_group.setExclusive(False)
                btn.setChecked(False)
                self._nav_group.setExclusive(True)
        origin = self._history[-1] if self._history else "apps"
        if origin in self._nav_buttons:
            self._nav_buttons[origin].setChecked(True)

    def open_day(self, day: str) -> None:
        self._views["calendar"].select_day(day)
        self.show_page("calendar")

    def go_back(self) -> None:
        if self._current == "app":
            self.show_page(self._history[-1] if self._history else "apps", remember=False)

    def back_label(self) -> str:
        origin = self._history[-1] if self._history else "apps"
        return dict((k, t) for k, t, _ in NAV).get(origin, "Settings" if origin == "settings" else "Apps")

    def refresh_current(self) -> None:
        view = self._views[self._current]
        if self._current == "app":
            view.reload()
        elif hasattr(view, "refresh"):
            view.refresh()

    def apply_rewards_visibility(self) -> None:
        on = rewards.enabled()
        for key in ("rewards", "village"):
            self._nav_buttons[key].setVisible(on)
        if not on and self._current in ("rewards", "village"):
            self.show_page("dashboard")
        self._update_badges()

    def _update_badges(self) -> None:
        self._badges["rewards"].set_count(rewards.unclaimed_count() if rewards.enabled() else 0)
        btn = self._nav_buttons["rewards"]
        badge = self._badges["rewards"]
        badge.adjustSize()
        badge.move(btn.width() - badge.width() - 10, (btn.height() - badge.height()) // 2)

    # ------------------------------------------------------------------
    # App context menu (shared by every list)
    # ------------------------------------------------------------------

    def show_app_menu(self, app_id: int, pos: QPoint) -> None:
        app = queries.get_app(app_id)
        if not app:
            return
        menu = QMenu(self)
        menu.addAction("Open details", lambda: self.open_app(app_id))
        fav = bool(app.get("is_favorite"))
        menu.addAction(
            "Remove from favorites" if fav else "Add to favorites", lambda: self._set_favorite(app_id, not fav)
        )
        menu.addSeparator()
        menu.addAction("Exclude from tracking", lambda: self.exclude_app(app_id))
        menu.exec(pos)

    def _set_favorite(self, app_id: int, fav: bool) -> None:
        queries.set_favorite(app_id, fav)
        bus.data_changed.emit()
        self.refresh_current()

    def exclude_app(self, app_id: int) -> None:
        app = queries.get_app(app_id)
        if not app:
            return
        queries.set_hidden(app_id, True)
        self._tracker.reload_settings()
        bus.data_changed.emit()
        if self._current == "app":
            self.go_back()
        else:
            self.refresh_current()

        def undo():
            queries.set_hidden(app_id, False)
            self._tracker.reload_settings()
            bus.data_changed.emit()
            self.refresh_current()

        self.toast.show_message(f"{app['name']} is no longer tracked", "info", "Undo", undo)

    # ------------------------------------------------------------------
    # Tracking state
    # ------------------------------------------------------------------

    def toggle_pause(self) -> None:
        if not self._tracker.supported:
            self.toast.show_message("Tracking is only available on Windows", "info")
            return
        if self._tracker.paused:
            self._tracker.resume()
            self.toast.show_message("Tracking resumed", "success")
        else:
            self._tracker.pause()
            self.toast.show_message("Tracking paused", "info")
        self._tick()

    def pause_for(self, minutes: float | None) -> None:
        self._tracker.pause(minutes)
        until = f" for {fmt.duration(minutes * 60_000)}" if minutes else ""
        self.toast.show_message(f"Tracking paused{until}", "info")
        self._tick()

    def _status_text(self, snap: trk.Snapshot) -> tuple[str, str, str]:
        """(headline, detail, icon) for the sidebar pill and tray tooltip."""
        if snap.status == trk.STATUS_TRACKING and snap.exe_name:
            app = queries.get_app(snap.app_id) if snap.app_id else None
            name = app["name"] if app else snap.exe_name
            return "Tracking", f"{name} · {fmt.clock(snap.session_ms)}", "activity"
        if snap.status == trk.STATUS_PAUSED:
            if snap.paused_until:
                left = max(0, snap.paused_until - time.time())
                return "Paused", f"Resumes in {fmt.duration(left * 1000, short=True)}", "pause"
            return "Paused", "Click to resume", "pause"
        if snap.status == trk.STATUS_IDLE:
            return "Idle", "Waiting for input", "clock"
        if snap.status == trk.STATUS_LOCKED:
            return "Locked", "Screen is locked", "clock"
        if snap.status == trk.STATUS_UNSUPPORTED:
            return "Not tracking", "Windows only", "power"
        return "Tracking", "Waiting for an app", "activity"

    def _refresh_status(self) -> None:
        snap = self._tracker.snapshot()
        head, detail, icon = self._status_text(snap)
        tone = {"activity": "accent", "pause": "warning"}.get(icon, "text_muted")
        self._status.setText(f"{head}\n{detail}")
        self._status.setIcon(icons.icon(icon, tone_color(tone), 16))
        if getattr(self, "_tray", None):
            today = queries.total_ms(queries.today_str(), queries.today_str()) + snap.uncommitted_ms
            self._tray.setToolTip(f"{APP_NAME}: {head.lower()}\n{detail}\nToday: {fmt.duration(today, short=True)}")
            self._pause_action.setText("Resume tracking" if self._tracker.paused else "Pause tracking")

    def _tick(self) -> None:
        self._refresh_status()
        if self.isVisible() and not self.isMinimized():
            view = self._views[self._current]
            if hasattr(view, "tick"):
                view.tick()

    def _slow_tick(self) -> None:
        snap = self._tracker.snapshot()
        try:
            if rewards.enabled() and rewards.evaluate_recent():
                bus.rewards_changed.emit()
            fav_live = 0
            if snap.app_id:
                app = queries.get_app(snap.app_id)
                fav_live = snap.uncommitted_ms if app and app.get("is_favorite") else 0
            streak = rewards.update_streak(extra_ms=fav_live)
            if streak:
                msg = f"Streak extended to {streak['streak']} days"
                if streak.get("reward"):
                    msg += f" ({fmt.reward(streak['reward'], ', ')})"
                self.notify("Streak", msg)
                bus.rewards_changed.emit()
            for app in self._limits.check(snap.app_id, snap.uncommitted_ms):
                self.notify(
                    "Daily limit reached",
                    f"{app['name']}: {fmt.duration(app['used_ms'], short=True)} today "
                    f"(limit {fmt.duration(app['daily_limit_ms'], short=True)})",
                    tone="warning",
                )
        except Exception:
            log.exception("Background evaluation failed")
        self._update_badges()

    def notify(self, title: str, message: str, tone: str = "success") -> None:
        """Toast when the window is visible, tray notification otherwise."""
        if self.isVisible() and not self.isMinimized() and self.isActiveWindow():
            self.toast.show_message(message, tone)
        elif getattr(self, "_tray", None) and db.get_bool("notifications_enabled", True):
            self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 6000)

    # ------------------------------------------------------------------
    # Tray
    # ------------------------------------------------------------------

    def _setup_tray(self) -> None:
        self._tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(icons.logo_icon(), self)
        menu = QMenu(self)
        menu.addAction(f"Open {APP_NAME}", self.bring_to_front)
        menu.addSeparator()
        self._pause_action = QAction("Pause tracking", self)
        self._pause_action.triggered.connect(self.toggle_pause)
        menu.addAction(self._pause_action)
        pause_menu = menu.addMenu("Pause for")
        for text, minutes in (("15 minutes", 15), ("30 minutes", 30), ("1 hour", 60), ("2 hours", 120)):
            pause_menu.addAction(text, lambda m=minutes: self.pause_for(m))
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self._tray_menu = menu
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.messageClicked.connect(self.bring_to_front)
        self._tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.isVisible() and self.isActiveWindow():
                self.hide()
            else:
                self.bring_to_front()

    def has_tray(self) -> bool:
        return self._tray is not None

    def bring_to_front(self) -> None:
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        self.refresh_current()

    def quit(self) -> None:
        self._quitting = True
        if self._tray:
            self._tray.hide()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        if not self._quitting and self._tray and db.get_bool("minimize_to_tray", True):
            event.ignore()
            self.hide()
            if not db.get_bool("tray_hint_shown"):
                db.set_setting("tray_hint_shown", True)
                self._tray.showMessage(
                    APP_NAME,
                    "Still tracking in the background. Right-click the tray icon to quit.",
                    QSystemTrayIcon.MessageIcon.Information,
                    5000,
                )
            return
        event.accept()
        self.quit()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "toast") and self.toast.isVisible():
            self.toast.reposition()

    # ------------------------------------------------------------------
    # Shortcuts
    # ------------------------------------------------------------------

    def _setup_shortcuts(self) -> None:
        def add(seq, fn):
            QShortcut(QKeySequence(seq), self, activated=fn)

        for i, (key, _text, _icon) in enumerate(NAV, start=1):
            add(f"Ctrl+{i}", lambda k=key: self._nav_buttons[k].isVisible() and self.show_page(k))
        add("Ctrl+,", lambda: self.show_page("settings"))
        add("Ctrl+F", self._focus_search)
        add("Ctrl+Shift+P", self.toggle_pause)
        add("F5", self.refresh_current)
        add("Alt+Left", self.go_back)
        add("Escape", self.go_back)
        add("Ctrl+Q", self.quit)

    def _focus_search(self) -> None:
        self.show_page("apps")
        self._views["apps"].focus_search()

    # ------------------------------------------------------------------
    # Theme and updates
    # ------------------------------------------------------------------

    def apply_theme(self) -> None:
        apply_app_theme(QApplication.instance())
        set_dark_titlebar(self, theme.current().dark)
        for view in self._views.values():
            view.update()
        self.refresh_current()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        set_dark_titlebar(self, theme.current().dark)
        self._stack.setFocus()

    def _startup_update_check(self) -> None:
        if self.ctx.demo or not db.get_bool("auto_update_check", True):
            return
        today = queries.today_str()
        if db.get_setting("last_update_check_day") == today:
            return
        db.set_setting("last_update_check_day", today)
        url = db.get_setting("update_url", "")
        run_async(lambda: updater.check_for_update(url), self._on_update_checked, lambda exc: None)

    def _on_update_checked(self, info) -> None:
        if not info:
            return
        self.set_update_available(info)
        self.notify("Update available", f"{APP_NAME} {info.version} is available. Open Settings to install.", "info")

    def set_update_available(self, info) -> None:
        self.ctx.update_info = info
        accent = theme.current().accent_text
        self._version.setText(
            f'v{__version__} · <a href="#" style="color:{accent}; text-decoration:none;">Update to {info.version}</a>'
        )


FONT_FAMILIES = ("Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text", "Noto Sans", "Ubuntu", "Cantarell")


def prepare_app(app: QApplication) -> None:
    """Style, font, icon and theme shared by the app and the screenshot script."""
    from PySide6.QtGui import QFont, QFontDatabase

    app.setStyle("Fusion")
    available = set(QFontDatabase.families())
    for family in FONT_FAMILIES:
        if family in available:
            font = QFont(family)
            font.setPixelSize(13)
            app.setFont(font)
            break
    app.setWindowIcon(icons.logo_icon())
    apply_app_theme(app)


def system_prefers_dark() -> bool:
    hints = QGuiApplication.styleHints()
    try:
        return hints.colorScheme() != Qt.ColorScheme.Light
    except AttributeError:
        return True


def apply_app_theme(app: QApplication) -> None:
    theme.configure(
        db.get_setting("ui_mode", "dark"),
        db.get_setting("ui_theme", theme.DEFAULT_ACCENT),
        system_dark=system_prefers_dark(),
    )
    app.setPalette(theme.palette())
    app.setStyleSheet(theme.stylesheet(arrow_icon=_combo_arrow(theme.current().text_dim)))
    bus.theme_changed.emit()


def _combo_arrow(color: str) -> str:
    """Write a tinted chevron for QComboBox (QSS needs a file path) and return it."""
    folder = Path(tempfile.gettempdir()) / "apptrackr-ui"
    folder.mkdir(exist_ok=True)
    target = folder / f"chevron-{color.lstrip('#')}.svg"
    if not target.exists():
        svg = (paths.assets_dir() / "icons" / "chevron-down.svg").read_text(encoding="utf-8")
        target.write_text(svg.replace("currentColor", color), encoding="utf-8")
    return target.as_posix()


def set_dark_titlebar(window: QWidget, dark: bool) -> None:
    """Match the Windows title bar to the app theme (Windows 10 20H1+ / 11)."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        value = ctypes.c_int(1 if dark else 0)
        hwnd = int(window.winId())
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (and pre-20H1 value)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), 4) == 0:
                break
    except Exception:
        log.debug("Could not set title bar theme", exc_info=True)
