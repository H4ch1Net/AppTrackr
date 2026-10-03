"""Settings. Every control applies immediately."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QWidget,
)

from ... import APP_NAME, REPO_URL, __version__
from ...core import autostart
from ...data import db, export, queries
from ...updater import apply as updater_apply
from ...updater import check as updater
from .. import fmt, theme
from ..signals import bus, run_async
from ..widgets.components import (
    Card,
    Page,
    PageHeader,
    SegmentedControl,
    SettingRow,
    Toggle,
    button,
    clear_layout,
    divider,
    label,
)

IDLE_CHOICES = (
    ("Never", 0),
    ("1 minute", 60),
    ("2 minutes", 120),
    ("3 minutes", 180),
    ("5 minutes", 300),
    ("10 minutes", 600),
    ("15 minutes", 900),
    ("30 minutes", 1800),
)
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


class Swatch(QAbstractButton):
    """Round accent color picker button."""

    def __init__(self, name: str, color: str, parent=None):
        super().__init__(parent)
        self.name = name
        self.color = color
        self.setCheckable(True)
        self.setToolTip(name)
        self.setAccessibleName(f"{name} accent")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def sizeHint(self) -> QSize:
        return QSize(28, 28)

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.isChecked() or self.hasFocus():
            p.setPen(QPen(QColor(t.text), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(1, 1, 26, 26)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.color))
        p.drawEllipse(5, 5, 18, 18)


class SettingsView(Page):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        self.add(PageHeader("Settings", "Changes are saved automatically."))

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
        card = Card("General")
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
        self.notifications.toggled.connect(lambda on: self._save("notifications_enabled", on))
        card.body.addWidget(
            SettingRow(
                "Notifications", "Daily limits, streaks and updates while the window is hidden.", self.notifications
            )
        )
        card.body.addWidget(divider())
        self.rewards = Toggle()
        self.rewards.toggled.connect(self._set_rewards)
        card.body.addWidget(
            SettingRow(
                "Rewards and village",
                "XP, levels and the Neon Village game. Turning this off hides both pages; nothing is deleted.",
                self.rewards,
            )
        )
        self.add(card)

    def _build_tracking(self) -> None:
        card = Card("Tracking")
        self.idle = QComboBox()
        for text, sec in IDLE_CHOICES:
            self.idle.addItem(text, sec)
        self.idle.currentIndexChanged.connect(self._set_idle)
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
        self.excluded = QGridLayout()
        self.excluded.setHorizontalSpacing(10)
        self.excluded.setVerticalSpacing(4)
        card.body.addLayout(self.excluded)
        self.add(card)

    def _build_appearance(self) -> None:
        card = Card("Appearance")
        self.mode = SegmentedControl(["Dark", "Light", "System"])
        self.mode.changed.connect(self._set_mode)
        card.body.addWidget(SettingRow("Theme", "", self.mode))
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
        card.body.addWidget(SettingRow("Accent color", "", swatches))
        self.add(card)

    def _build_data(self) -> None:
        card = Card("Data", "Usage is stored only on this computer.")
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(button("Export CSV", icon="download", on_click=lambda: self._export("csv")))
        row.addWidget(button("Export JSON", icon="download", on_click=lambda: self._export("json")))
        row.addWidget(button("Back up…", icon="database", on_click=self._backup))
        row.addWidget(button("Restore…", icon="archive-restore", on_click=self._restore))
        row.addStretch(1)
        row.addWidget(button("Open data folder", kind="ghost", icon="folder-open", on_click=self._open_folder))
        card.body.addLayout(row)
        self.db_path = label("", "caption")
        self.db_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.body.addWidget(self.db_path)
        self.add(card)

    def _build_updates(self) -> None:
        card = Card("Updates")
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
        card = Card("About")
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
        card.body.addWidget(label("KEYBOARD SHORTCUTS", "section"))
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
        self.clicks.set_silently(db.get_bool("track_clicks"))
        self.auto_update.set_silently(db.get_bool("auto_update_check", True))
        self.feed.setText(db.get_setting("update_url", ""))

        idle = db.get_int("idle_threshold_sec", 300)
        idx = self.idle.findData(idle)
        if idx < 0:
            self.idle.addItem(fmt.duration(idle * 1000), idle)
            idx = self.idle.count() - 1
        self.idle.blockSignals(True)
        self.idle.setCurrentIndex(idx)
        self.idle.blockSignals(False)

        self.mode.set_current(theme.MODES.index(theme.mode()))
        self.swatches[theme.accent_name()].setChecked(True)
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
            self.excluded.addWidget(label("No excluded apps.", "muted"), 0, 0)
            return
        for i, app in enumerate(hidden):
            self.excluded.addWidget(label(app["name"]), i, 0)
            self.excluded.addWidget(label(app["exe_name"], "caption"), i, 1)
            self.excluded.addWidget(button("Track again", kind="ghost", on_click=lambda a=app: self._include(a)), i, 2)
        self.excluded.setColumnStretch(1, 1)

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
        self.ctx.toast("Rewards turned on" if on else "Rewards turned off")

    def _set_idle(self) -> None:
        sec = self.idle.currentData()
        db.set_setting("idle_threshold_sec", sec)
        self.ctx.tracker.reload_settings()
        self.ctx.toast("Idle detection off" if not sec else f"Idle after {self.idle.currentText()}")

    def _set_clicks(self, on: bool) -> None:
        db.set_setting("track_clicks", on)
        if self.ctx.clicks is not None:
            self.ctx.clicks.set_enabled(on)
        self.ctx.toast("Click counting on" if on else "Click counting off")

    def _set_mode(self, index: int) -> None:
        db.set_setting("ui_mode", theme.MODES[index])
        self.ctx.window.apply_theme()

    def _set_accent(self, name: str) -> None:
        db.set_setting("ui_theme", name)
        self.ctx.window.apply_theme()

    def _include(self, app: dict) -> None:
        queries.set_hidden(app["app_id"], False)
        self.ctx.tracker.reload_settings()
        bus.data_changed.emit()
        self._fill_excluded()
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
