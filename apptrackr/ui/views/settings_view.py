"""Settings view – idle, privacy, autostart, export."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QCheckBox, QFrame, QFileDialog, QMessageBox, QLineEdit,
    QComboBox, QScrollArea,
)

from .. import theme
from ..widgets.components import NeonCard
from ...data import db, export
from ...updater import check as updater_check
from ...updater import apply as updater_apply


class SettingsView(QWidget):
    """Application settings panel."""

    def __init__(self, tracker=None, parent=None):
        super().__init__(parent)
        self._tracker = tracker
        self._build_ui()
        self._load()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root_layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Settings")
        header.setObjectName("heading")
        layout.addWidget(header)

        # -- Tracking --
        track_card = NeonCard(glow_color=theme.BG_CARD, title="TRACKING")
        tl = track_card.content_layout()

        # Idle threshold
        idle_row = QHBoxLayout()
        idle_row.setSpacing(16)
        idle_lbl = QLabel("Idle threshold (seconds):")
        idle_lbl.setStyleSheet("background: transparent;")
        idle_row.addWidget(idle_lbl)
        self._idle_spin = QSpinBox()
        self._idle_spin.setRange(0, 3600)
        self._idle_spin.setSingleStep(30)
        self._idle_spin.setFixedWidth(100)
        self._idle_spin.setToolTip("0 = disabled")
        idle_row.addWidget(self._idle_spin)
        idle_row.addStretch()
        tl.addLayout(idle_row)

        # Polling rate
        poll_row = QHBoxLayout()
        poll_row.setSpacing(16)
        poll_lbl = QLabel("Polling rate (Hz):")
        poll_lbl.setStyleSheet("background: transparent;")
        poll_row.addWidget(poll_lbl)
        self._poll_spin = QSpinBox()
        self._poll_spin.setRange(1, 10)
        self._poll_spin.setFixedWidth(100)
        poll_row.addWidget(self._poll_spin)
        poll_row.addStretch()
        tl.addLayout(poll_row)

        layout.addWidget(track_card)

        # -- Privacy --
        privacy_card = NeonCard(glow_color=theme.BG_CARD, title="PRIVACY")
        pl = privacy_card.content_layout()

        self._title_check = QCheckBox("Track window titles (hashed)")
        pl.addWidget(self._title_check)

        self._click_check = QCheckBox("Track mouse clicks (count only)")
        pl.addWidget(self._click_check)

        layout.addWidget(privacy_card)

        # -- System --
        sys_card = NeonCard(glow_color=theme.BG_CARD, title="SYSTEM")
        sl = sys_card.content_layout()

        self._autostart_check = QCheckBox("Launch on system startup")
        sl.addWidget(self._autostart_check)

        self._tray_check = QCheckBox("Minimize to system tray")
        sl.addWidget(self._tray_check)

        self._rewards_check = QCheckBox("Enable rewards system")
        sl.addWidget(self._rewards_check)

        layout.addWidget(sys_card)

        # -- Data --
        data_card = NeonCard(glow_color=theme.BG_CARD, title="DATA")
        dl = data_card.content_layout()

        btn_row = QHBoxLayout()
        export_csv_btn = QPushButton("Export CSV")
        export_csv_btn.clicked.connect(self._export_csv)
        btn_row.addWidget(export_csv_btn)

        export_json_btn = QPushButton("Export JSON")
        export_json_btn.clicked.connect(self._export_json)
        btn_row.addWidget(export_json_btn)

        backup_btn = QPushButton("Backup Database")
        backup_btn.clicked.connect(self._backup)
        btn_row.addWidget(backup_btn)

        restore_btn = QPushButton("Restore Backup")
        restore_btn.clicked.connect(self._restore)
        btn_row.addWidget(restore_btn)

        btn_row.addStretch()
        dl.addLayout(btn_row)

        # DB location
        db_path = QLabel(f"DB: {db._db_path()}")
        db_path.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px; background: transparent;")
        dl.addWidget(db_path)

        layout.addWidget(data_card)

        # -- Appearance --
        appearance_card = NeonCard(glow_color=theme.BG_CARD, title="APPEARANCE")
        al = appearance_card.content_layout()

        theme_row = QHBoxLayout()
        theme_row.setSpacing(16)
        theme_lbl = QLabel("Theme Color:")
        theme_lbl.setStyleSheet("background: transparent;")
        theme_row.addWidget(theme_lbl)
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(list(theme.THEME_PRESETS.keys()))
        self._theme_combo.setFixedWidth(150)
        theme_row.addWidget(self._theme_combo)
        theme_row.addStretch()
        al.addLayout(theme_row)

        theme_note = QLabel("Changes apply after restart")
        theme_note.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px; background: transparent;")
        al.addWidget(theme_note)

        layout.addWidget(appearance_card)

        # -- Updates --
        updates_card = NeonCard(glow_color=theme.BG_CARD, title="UPDATES")
        ul = updates_card.content_layout()

        self._auto_update_check = QCheckBox("Automatically check for updates on startup")
        ul.addWidget(self._auto_update_check)

        url_row = QHBoxLayout()
        url_row.setSpacing(16)
        url_lbl = QLabel("Update feed URL:")
        url_lbl.setStyleSheet("background: transparent;")
        url_row.addWidget(url_lbl)
        self._update_url_edit = QLineEdit()
        self._update_url_edit.setPlaceholderText("https://api.github.com/repos/<owner>/<repo>/releases/latest")
        url_row.addWidget(self._update_url_edit, stretch=1)
        ul.addLayout(url_row)

        update_actions = QHBoxLayout()
        check_btn = QPushButton("Check for Updates")
        check_btn.clicked.connect(self._check_for_updates)
        update_actions.addWidget(check_btn)
        update_actions.addStretch()
        ul.addLayout(update_actions)

        update_note = QLabel("If an update is found, AppTrackr can download and launch the new installer.")
        update_note.setWordWrap(True)
        update_note.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px; background: transparent;")
        ul.addWidget(update_note)

        layout.addWidget(updates_card)

        # Save button
        save_row = QHBoxLayout()
        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save)
        save_row.addWidget(save_btn)
        save_row.addStretch()
        layout.addLayout(save_row)

        layout.addStretch()

    def _load(self):
        self._idle_spin.setValue(int(db.get_setting("idle_threshold_sec", "300")))
        self._poll_spin.setValue(int(db.get_setting("polling_hz", "4")))
        self._title_check.setChecked(db.get_setting("track_window_titles", "0") == "1")
        self._click_check.setChecked(db.get_setting("track_clicks", "0") == "1")
        self._autostart_check.setChecked(db.get_setting("autostart", "0") == "1")
        self._tray_check.setChecked(db.get_setting("minimize_to_tray", "1") == "1")
        self._rewards_check.setChecked(db.get_setting("rewards_enabled", "1") == "1")
        self._auto_update_check.setChecked(db.get_setting("auto_update_check", "1") == "1")
        self._update_url_edit.setText(db.get_setting("update_url", ""))
        
        # Theme
        current_theme = db.get_setting("ui_theme", "Cyan")
        idx = self._theme_combo.findText(current_theme)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)

    def _save(self):
        db.set_setting("idle_threshold_sec", str(self._idle_spin.value()))
        db.set_setting("polling_hz", str(self._poll_spin.value()))
        db.set_setting("track_window_titles", "1" if self._title_check.isChecked() else "0")
        db.set_setting("track_clicks", "1" if self._click_check.isChecked() else "0")
        db.set_setting("autostart", "1" if self._autostart_check.isChecked() else "0")
        db.set_setting("minimize_to_tray", "1" if self._tray_check.isChecked() else "0")
        db.set_setting("rewards_enabled", "1" if self._rewards_check.isChecked() else "0")
        db.set_setting("ui_theme", self._theme_combo.currentText())
        db.set_setting("auto_update_check", "1" if self._auto_update_check.isChecked() else "0")
        db.set_setting("update_url", self._update_url_edit.text().strip())

        # Apply autostart
        self._apply_autostart(self._autostart_check.isChecked())

        if self._tracker:
            self._tracker.reload_settings()

        QMessageBox.information(self, "Settings", "Settings saved.")

    def _apply_autostart(self, enable: bool):
        """Set or remove autostart via Windows registry."""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE,
            )
            if enable:
                exe = sys.executable
                if getattr(sys, "frozen", False):
                    cmd = f'"{exe}"'
                else:
                    cmd = f'"{exe}" -m apptrackr'
                winreg.SetValueEx(key, "AppTrackr", 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, "AppTrackr")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception:
            pass

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "apptrackr_export.csv", "CSV (*.csv)")
        if path:
            export.export_csv(path)
            QMessageBox.information(self, "Export", f"Exported to {path}")

    def _export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export JSON", "apptrackr_export.json", "JSON (*.json)")
        if path:
            export.export_json(path)
            QMessageBox.information(self, "Export", f"Exported to {path}")

    def _backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "Backup Database", "apptrackr_backup.sqlite", "SQLite (*.sqlite)")
        if path:
            export.backup_db(path)
            QMessageBox.information(self, "Backup", f"Backed up to {path}")

    def _restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "Restore Backup", "", "SQLite (*.sqlite)")
        if path:
            reply = QMessageBox.warning(
                self, "Restore",
                "This will replace your current data. The app will restart. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                export.restore_db(path)
                QMessageBox.information(self, "Restore", "Restored. Please restart the app.")

    def _check_for_updates(self):
        update_url = self._update_url_edit.text().strip() or db.get_setting("update_url", "")
        if not update_url:
            QMessageBox.information(
                self,
                "Updates",
                "Set an Update feed URL first.\n\n"
                "Example:\nhttps://api.github.com/repos/<owner>/<repo>/releases/latest",
            )
            return

        info = updater_check.check_for_update(update_url)
        if not info:
            QMessageBox.information(self, "Updates", "You're up to date.")
            return

        version = info.get("version", "unknown")
        url = info.get("url", "")
        if not url:
            QMessageBox.information(self, "Updates", f"Update v{version} found, but no installer asset was published.")
            return

        reply = QMessageBox.question(
            self,
            "Update Available",
            f"AppTrackr v{version} is available. Download and launch installer now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        downloaded = updater_apply.download_and_apply(url)
        if not downloaded:
            QMessageBox.warning(self, "Updates", "Download failed. Please try again later.")
            return

        QMessageBox.information(self, "Updates", "Installer launched. AppTrackr will now close.")
        sys.exit(0)
