"""Foreground window tracker – polls the active window and records focus sessions."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import date

import psutil

from ..data import db, queries, rollup

log = logging.getLogger(__name__)

# Win32 API bindings
user32 = ctypes.windll.user32  # type: ignore[attr-defined]
kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

# System / ignored executables
_IGNORED_EXES = frozenset({
    "explorer.exe", "searchui.exe", "shellexperiencehost.exe",
    "startmenuexperiencehost.exe", "textinputhost.exe", "lockapp.exe",
    "systemsettings.exe", "searchhost.exe", "widgets.exe",
})


@dataclass
class _TrackerState:
    current_app_id: int | None = None
    current_session_id: int | None = None
    current_exe: str | None = None
    current_start: float = 0.0
    paused: bool = False
    running: bool = False
    session_locked: bool = False


class Tracker:
    """Polls the foreground window and attributes time to apps."""

    def __init__(self) -> None:
        self._state = _TrackerState()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._callbacks: list = []
        self._idle_threshold: int = 300  # seconds
        self._poll_interval: float = 0.25  # 4 Hz
        self._track_titles: bool = False

    # ------------------------------------------------------------------
    # Public control
    # ------------------------------------------------------------------

    def start(self) -> None:
        db.init_db()
        self._load_settings()
        self._state.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="tracker")
        self._thread.start()
        log.info("Tracker started (poll %.0f Hz)", 1 / self._poll_interval)

    def stop(self) -> None:
        self._state.running = False
        self._flush()

    def pause(self) -> None:
        with self._lock:
            self._state.paused = True
            self._flush_unlocked()

    def resume(self) -> None:
        with self._lock:
            self._state.paused = False

    @property
    def paused(self) -> bool:
        return self._state.paused

    @property
    def current_exe(self) -> str | None:
        return self._state.current_exe

    @property
    def current_app_id(self) -> int | None:
        return self._state.current_app_id

    @property
    def session_elapsed_ms(self) -> int:
        s = self._state
        if s.current_start and s.current_app_id and not s.paused:
            return int((time.time() - s.current_start) * 1000)
        return 0

    def on_change(self, callback) -> None:
        """Register callback(app_id, exe_name) for focus changes."""
        self._callbacks.append(callback)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _load_settings(self) -> None:
        self._idle_threshold = int(db.get_setting("idle_threshold_sec", "300"))
        self._track_titles = db.get_setting("track_window_titles", "0") == "1"
        hz = int(db.get_setting("polling_hz", "4"))
        self._poll_interval = 1.0 / max(hz, 1)

    def reload_settings(self) -> None:
        self._load_settings()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while self._state.running:
            try:
                self._tick()
            except Exception:
                log.exception("Tracker tick error")
            time.sleep(self._poll_interval)

    def _tick(self) -> None:
        with self._lock:
            if self._state.paused or self._is_locked():
                if self._state.current_app_id:
                    self._flush_unlocked()
                return

            # Idle detection
            if self._idle_threshold > 0 and self._get_idle_seconds() > self._idle_threshold:
                if self._state.current_app_id:
                    self._flush_unlocked(was_idle=True)
                return

            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return

            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            pid_val = pid.value
            if not pid_val:
                return

            try:
                proc = psutil.Process(pid_val)
                exe_name = proc.name().lower()
                exe_path = proc.exe()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return

            if exe_name in _IGNORED_EXES:
                return

            # Same app as before → nothing to do
            if exe_name == self._state.current_exe:
                return

            # App changed – close old session, open new
            self._switch_app(exe_name, exe_path, hwnd)

    def _switch_app(self, exe_name: str, exe_path: str, hwnd: int) -> None:
        now = time.time()

        # Close previous session
        if self._state.current_session_id is not None:
            queries.end_session(self._state.current_session_id, now)
            rollup.rollup_session(self._state.current_session_id)

        # Get or create app
        app_id = queries.get_or_create_app(exe_name, icon_path=exe_path)
        session_id = queries.start_session(app_id, now)
        today = date.today().isoformat()
        queries.increment_opens(today, app_id)

        # Optional title tracking
        if self._track_titles:
            title_hash = self._hash_title(hwnd)
            queries.log_focus_event(app_id, "focus_in", title_hash)

        self._state.current_app_id = app_id
        self._state.current_session_id = session_id
        self._state.current_exe = exe_name
        self._state.current_start = now

        for cb in self._callbacks:
            try:
                cb(app_id, exe_name)
            except Exception:
                log.exception("Callback error")

    def _flush(self) -> None:
        with self._lock:
            self._flush_unlocked()

    def _flush_unlocked(self, was_idle: bool = False) -> None:
        if self._state.current_session_id is not None:
            queries.end_session(self._state.current_session_id, was_idle=was_idle)
            rollup.rollup_session(self._state.current_session_id)
        self._state.current_app_id = None
        self._state.current_session_id = None
        self._state.current_exe = None
        self._state.current_start = 0.0
        for cb in self._callbacks:
            try:
                cb(None, None)
            except Exception:
                log.exception("Callback error")

    # ------------------------------------------------------------------
    # Win32 helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_idle_seconds() -> float:
        """Seconds since last user input (keyboard/mouse)."""

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = kernel32.GetTickCount() - lii.dwTime
            return millis / 1000.0
        return 0.0

    @staticmethod
    def _is_locked() -> bool:
        """Check if the workstation is locked."""
        # OpenInputDesktop returns NULL when desktop is locked / switched
        hdesk = user32.OpenInputDesktop(0, False, 0x0001)  # DESKTOP_READOBJECTS
        if hdesk:
            user32.CloseDesktop(hdesk)
            return False
        return True

    @staticmethod
    def _hash_title(hwnd: int) -> str:
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        return hashlib.sha256(buf.value.encode()).hexdigest()[:16]
