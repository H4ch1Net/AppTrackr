"""Process watch – detect new process launches by diffing the PID set."""

from __future__ import annotations

import logging
import threading
import time
from datetime import date

import psutil

from ..data import queries

log = logging.getLogger(__name__)


class ProcessWatcher:
    """Periodically diffs running processes to detect new app launches."""

    def __init__(self, interval: float = 5.0) -> None:
        self._interval = interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._known_pids: set[int] = set()

    def start(self) -> None:
        self._known_pids = {p.pid for p in psutil.process_iter(["pid"])}
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="proc-watch")
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            try:
                self._check()
            except Exception:
                log.exception("ProcessWatcher error")
            time.sleep(self._interval)

    def _check(self) -> None:
        current = set()
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            current.add(proc.pid)
            if proc.pid not in self._known_pids:
                try:
                    exe = proc.info["name"]  # type: ignore[index]
                    exe_path = proc.info.get("exe")  # type: ignore[union-attr]
                    if exe:
                        app_id = queries.get_or_create_app(exe.lower(), icon_path=exe_path)
                        queries.increment_opens(date.today().isoformat(), app_id)
                except Exception:
                    pass
        self._known_pids = current
