"""Launch counter: counts how often each tracked app is started.

A launch is an executable going from "not running" to "running". Multi-process
apps such as browsers therefore count once, not once per child process.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import date

import psutil

from ..data import catalog, db, queries

log = logging.getLogger(__name__)

# How long a launch of a not-yet-known app is remembered while waiting for the
# tracker to see it in focus for the first time.
_PENDING_TTL = 600.0


class ProcessWatcher:
    def __init__(self, interval: float = 5.0) -> None:
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._running: set[str] | None = None
        self._pending: dict[str, float] = {}

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="launch-watch")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.check(self._running_names())
            except Exception:
                log.exception("Launch watcher failed")
            self._stop.wait(self._interval)
        db.close()

    @staticmethod
    def _running_names() -> set[str]:
        names = set()
        for proc in psutil.process_iter(["name"]):
            name = proc.info.get("name")  # type: ignore[union-attr]
            if name:
                names.add(catalog.canonical_exe(name))
        return names

    def check(self, running: set[str], now: float | None = None) -> None:
        """Process one snapshot of running executable names."""
        now = time.time() if now is None else now
        if self._running is None:
            self._running = running  # apps already open at startup are not launches
            return
        launched = {n for n in running - self._running if catalog.is_trackable(n)}
        self._running = running

        today = date.today().isoformat()
        for name in launched:
            self._pending[name] = now
        for name, seen in list(self._pending.items()):
            if name not in running or now - seen > _PENDING_TTL:
                del self._pending[name]
                continue
            app_id = queries.find_app_id(name)
            if app_id is not None:
                queries.increment_opens(today, app_id)
                del self._pending[name]
