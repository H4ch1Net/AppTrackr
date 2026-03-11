"""Global mouse click counter (opt-in). Uses pynput."""

from __future__ import annotations

import logging
import ctypes
import ctypes.wintypes
import threading
import time
from datetime import date

import psutil

from ..data import db, queries

log = logging.getLogger(__name__)


class ClickCounter:
    """Counts global mouse clicks attributed to the foreground app. Opt-in only."""

    def __init__(self) -> None:
        self._running = False
        self._thread: threading.Thread | None = None
        self._listener = None

    def start(self) -> None:
        if db.get_setting("track_clicks", "0") != "1":
            log.info("Click tracking disabled")
            return
        try:
            from pynput import mouse
            self._running = True
            self._listener = mouse.Listener(on_click=self._on_click)
            self._listener.start()
            log.info("Click counter started")
        except ImportError:
            log.warning("pynput not installed – click tracking unavailable")

    def stop(self) -> None:
        self._running = False
        if self._listener:
            self._listener.stop()

    def _on_click(self, x, y, button, pressed) -> None:
        if not pressed or not self._running:
            return
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()  # type: ignore[attr-defined]
            pid = ctypes.wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))  # type: ignore[attr-defined]
            proc = psutil.Process(pid.value)
            exe = proc.name().lower()
            app_id = queries.get_or_create_app(exe)
            queries.increment_clicks(date.today().isoformat(), app_id)
        except Exception:
            pass
