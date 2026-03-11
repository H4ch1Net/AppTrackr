"""Main application window with sidebar navigation and tray icon."""

from __future__ import annotations

import sys
import threading

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QSystemTrayIcon, QMenu, QApplication, QLabel, QButtonGroup,
)

from . import theme
from .widgets.components import SidebarButton
from .views.dashboard import DashboardView
from .views.calendar_view import CalendarView
from .views.apps_view import AppsView
from .views.app_detail import AppDetailView
from .views.rewards_view import RewardsView
from .views.village_view import VillageView
from .views.settings_view import SettingsView
from ..data import db
from ..updater import check as updater_check


def _make_icon() -> QIcon:
    """Create a simple neon 'A' icon programmatically."""
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Background circle
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(theme.BG_DARK))
    p.drawRoundedRect(0, 0, 64, 64, 16, 16)
    # Letter
    p.setPen(QColor(theme.get_accent()))
    p.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "A")
    p.end()
    return QIcon(pix)


class MainWindow(QMainWindow):
    """Main AppTrackr window with sidebar and stacked views."""

    PAGE_DASHBOARD = 0
    PAGE_CALENDAR = 1
    PAGE_APPS = 2
    PAGE_APP_DETAIL = 3
    PAGE_REWARDS = 4
    PAGE_VILLAGE = 5
    PAGE_SETTINGS = 6

    def __init__(self, tracker):
        super().__init__()
        self._tracker = tracker
        self.setWindowTitle("AppTrackr")
        self.setMinimumSize(1080, 720)
        self.setWindowIcon(_make_icon())

        self._build_ui()
        self._setup_tray()

        # Optional startup update check (non-blocking)
        QTimer.singleShot(8000, self._startup_update_check)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # -- Sidebar --
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(f"background-color: {theme.BG_DARKEST};")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(12, 20, 12, 20)
        sb_layout.setSpacing(4)

        # Logo
        logo = QLabel("⚡ AppTrackr")
        logo.setStyleSheet(
            f"font-size: 20px; font-weight: 800; color: {theme.get_accent()}; "
            f"padding: 8px 8px 20px 8px; background: transparent;"
        )
        sb_layout.addWidget(logo)

        # Nav buttons
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        nav_items = [
            ("📊", "Dashboard",  self.PAGE_DASHBOARD),
            ("📅", "Calendar",   self.PAGE_CALENDAR),
            ("📱", "Apps",       self.PAGE_APPS),
            ("🎁", "Rewards",    self.PAGE_REWARDS),
            ("🎮", "Game",    self.PAGE_VILLAGE),
            ("⚙️", "Settings",   self.PAGE_SETTINGS),
        ]

        for icon, text, page_idx in nav_items:
            btn = SidebarButton(icon, text)
            btn.clicked.connect(lambda checked, idx=page_idx: self._show_page(idx))
            self._nav_group.addButton(btn, page_idx)
            sb_layout.addWidget(btn)

        sb_layout.addStretch()

        # Version label
        ver = QLabel("v1.0.0")
        ver.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 10px; padding: 8px; background: transparent;")
        sb_layout.addWidget(ver)

        main_layout.addWidget(sidebar)

        # -- Content stack --
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background-color: {theme.BG_DARK};")

        self._dashboard = DashboardView(self._tracker)
        self._dashboard.app_selected.connect(self._show_app_detail)
        self._stack.addWidget(self._dashboard)

        self._calendar = CalendarView()
        self._calendar.app_selected.connect(self._show_app_detail)
        self._stack.addWidget(self._calendar)

        self._apps = AppsView()
        self._apps.app_selected.connect(self._show_app_detail)
        self._stack.addWidget(self._apps)

        self._app_detail = AppDetailView()
        self._app_detail.back_clicked.connect(lambda: self._show_page(self.PAGE_APPS))
        self._stack.addWidget(self._app_detail)

        self._rewards = RewardsView()
        self._stack.addWidget(self._rewards)

        self._village = VillageView()
        self._stack.addWidget(self._village)

        self._settings = SettingsView(tracker=self._tracker)
        self._stack.addWidget(self._settings)

        main_layout.addWidget(self._stack, stretch=1)

        # Default page
        self._show_page(self.PAGE_DASHBOARD)

        # Periodic reward eval
        self._reward_timer = QTimer(self)
        self._reward_timer.timeout.connect(self._periodic_eval)
        self._reward_timer.start(60_000)  # every 60s

    def _show_page(self, idx: int):
        self._stack.setCurrentIndex(idx)
        btn = self._nav_group.button(idx)
        if btn:
            btn.setChecked(True)
        # Refresh view on show
        widget = self._stack.currentWidget()
        if hasattr(widget, "refresh"):
            widget.refresh()

    def _show_app_detail(self, app_id: int):
        self._app_detail.load_app(app_id)
        self._stack.setCurrentIndex(self.PAGE_APP_DETAIL)

    def _periodic_eval(self):
        from ..rewards import engine
        engine.evaluate()
        engine.update_streak()

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _setup_tray(self):
        self._tray = QSystemTrayIcon(_make_icon(), self)

        menu = QMenu()
        show_action = QAction("Show AppTrackr", self)
        show_action.triggered.connect(self._tray_show)
        menu.addAction(show_action)

        self._pause_action = QAction("Pause Tracking", self)
        self._pause_action.triggered.connect(self._tray_toggle_pause)
        menu.addAction(self._pause_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._tray_quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _tray_show(self):
        self.showNormal()
        self.activateWindow()

    def _tray_toggle_pause(self):
        if self._tracker.paused:
            self._tracker.resume()
            self._pause_action.setText("Pause Tracking")
        else:
            self._tracker.pause()
            self._pause_action.setText("Resume Tracking")

    def _tray_quit(self):
        self._tracker.stop()
        QApplication.quit()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._tray_show()

    def closeEvent(self, event):
        minimize_to_tray = db.get_setting("minimize_to_tray", "1") == "1"
        if minimize_to_tray:
            event.ignore()
            self.hide()
            self._tray.showMessage("AppTrackr", "Running in background", QSystemTrayIcon.MessageIcon.Information, 2000)
        else:
            self._tracker.stop()
            event.accept()

    def _startup_update_check(self):
        if db.get_setting("auto_update_check", "1") != "1":
            return

        update_url = db.get_setting("update_url", "").strip()
        if not update_url:
            return

        last_check_day = db.get_setting("last_update_check_day", "")
        from datetime import date
        today = date.today().isoformat()
        if last_check_day == today:
            return
        db.set_setting("last_update_check_day", today)

        def worker():
            info = updater_check.check_for_update(update_url)
            if not info:
                return
            version = info.get("version", "?")

            def notify():
                self._tray.showMessage(
                    "AppTrackr Update",
                    f"Version {version} is available. Open Settings > Updates to install.",
                    QSystemTrayIcon.MessageIcon.Information,
                    7000,
                )

            QTimer.singleShot(0, notify)

        threading.Thread(target=worker, daemon=True, name="update-check").start()
