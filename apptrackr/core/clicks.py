"""Opt-in mouse click counter. Stores counts per app per day, nothing else."""

from __future__ import annotations

import logging
import threading
from collections import Counter
from datetime import date

from ..data import db, queries

log = logging.getLogger(__name__)


class ClickCounter:
    """Counts global mouse clicks and attributes them to the tracked app."""

    FLUSH_SEC = 20.0

    def __init__(self, tracker) -> None:
        self._tracker = tracker
        self._listener = None
        self._counts: Counter[tuple[str, int]] = Counter()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._flusher: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._listener is not None

    def set_enabled(self, enabled: bool) -> None:
        if enabled and not self.running:
            self._start()
        elif not enabled and self.running:
            self.stop()

    def _start(self) -> None:
        if not self._tracker.supported:
            return
        try:
            from pynput import mouse
        except Exception:
            log.warning("pynput unavailable; click counting disabled")
            return
        self._listener = mouse.Listener(on_click=self._on_click)
        self._listener.daemon = True
        self._listener.start()
        self._stop.clear()
        self._flusher = threading.Thread(target=self._flush_loop, daemon=True, name="click-flush")
        self._flusher.start()
        log.info("Click counter started")

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._stop.set()
        self.flush()

    def _on_click(self, _x, _y, _button, pressed) -> None:
        if not pressed:
            return
        # Runs inside the low-level mouse hook: never block here.
        app_id = self._tracker.current_app_id
        if app_id is not None:
            with self._lock:
                self._counts[(date.today().isoformat(), app_id)] += 1

    def _flush_loop(self) -> None:
        while not self._stop.wait(self.FLUSH_SEC):
            self.flush()
        db.close()

    def flush(self) -> None:
        with self._lock:
            pending, self._counts = self._counts, Counter()
        try:
            for (day, app_id), count in pending.items():
                queries.increment_clicks(day, app_id, count)
        except Exception:
            log.exception("Failed to store click counts")
