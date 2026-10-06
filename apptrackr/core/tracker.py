"""Foreground tracker: samples the focused app and records focus sessions.

Time is committed to the database in small checkpoints, so totals are live,
a crash loses at most one checkpoint interval, and sessions that cross
midnight are split between days.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

from ..data import catalog, db, queries
from .platform import Platform

log = logging.getLogger(__name__)

STATUS_TRACKING = "tracking"
STATUS_IDLE = "idle"
STATUS_PAUSED = "paused"
STATUS_LOCKED = "locked"
STATUS_WAITING = "waiting"  # nothing trackable in focus
STATUS_UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class Snapshot:
    """Thread-safe view of the tracker for the UI."""

    status: str
    app_id: int | None = None
    exe_name: str | None = None
    session_start: float = 0.0
    session_ms: int = 0
    uncommitted_ms: int = 0
    paused_until: float | None = None


class Tracker:
    """Polls the platform for the focused app and attributes time to it."""

    CHECKPOINT_SEC = 30.0
    # A pause between samples longer than this means the machine slept or the
    # process was suspended; the session is closed at the last sample.
    GAP_SEC = 15.0
    # Focus that changes with no input for this long was not caused by the user,
    # so the previous session ends at the last input.
    SWITCH_IDLE_SEC = 30.0

    def __init__(self, platform: Platform, clock: Callable[[], float] = time.time) -> None:
        self._platform = platform
        self._clock = clock
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

        self._idle_threshold = 300
        self._poll_interval = 0.25
        self._excluded: set[str] = set()

        self._app_id: int | None = None
        self._exe: str | None = None
        self._session_id: int | None = None
        self._session_start = 0.0
        self._committed_until = 0.0
        self._next_checkpoint = 0.0
        self._last_tick: float | None = None
        self._paused = False
        self._paused_until: float | None = None
        self._status = STATUS_WAITING if platform.supported else STATUS_UNSUPPORTED

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self.reload_settings()
        if not self._platform.supported:
            log.info("Tracker not started: platform unsupported")
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="tracker")
        self._thread.start()
        log.info("Tracker started (%.1f Hz, idle after %ss)", 1 / self._poll_interval, self._idle_threshold)

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        with self._lock:
            self._close(self._clock())

    def flush(self) -> None:
        """Commit the live session so far without ending it (sign-out, installer closing the app)."""
        with self._lock:
            self._checkpoint(self._clock())

    def reload_settings(self) -> None:
        with self._lock:
            self._idle_threshold = max(0, db.get_int("idle_threshold_sec", 300))
            hz = min(max(db.get_int("polling_hz", 4), 1), 10)
            self._poll_interval = 1.0 / hz
            self._excluded = queries.hidden_exes()
            if self._exe in self._excluded:
                self._close(self._clock())

    # ------------------------------------------------------------------
    # Pause / resume
    # ------------------------------------------------------------------

    def pause(self, minutes: float | None = None) -> None:
        """Pause tracking, optionally resuming automatically after *minutes*."""
        with self._lock:
            now = self._clock()
            self._close(now)
            self._paused = True
            self._paused_until = now + minutes * 60 if minutes else None
            self._status = STATUS_PAUSED

    def resume(self) -> None:
        with self._lock:
            self._paused = False
            self._paused_until = None
            self._status = STATUS_WAITING

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def supported(self) -> bool:
        return self._platform.supported

    @property
    def current_app_id(self) -> int | None:
        """Lock-free read for hot paths such as the mouse hook."""
        return self._app_id

    def foreground_fullscreen(self) -> bool:
        """True while a full-screen window is in front (Windows only)."""
        check = getattr(self._platform, "foreground_fullscreen", None)
        try:
            return bool(check()) if check else False
        except OSError:
            return False

    def snapshot(self) -> Snapshot:
        with self._lock:
            now = self._clock()
            if self._app_id is None:
                return Snapshot(self._status, paused_until=self._paused_until)
            return Snapshot(
                status=self._status,
                app_id=self._app_id,
                exe_name=self._exe,
                session_start=self._session_start,
                session_ms=int(max(0.0, now - self._session_start) * 1000),
                uncommitted_ms=int(max(0.0, now - self._committed_until) * 1000),
                paused_until=self._paused_until,
            )

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("Tracker tick failed")
            self._stop.wait(self._poll_interval)
        db.close()

    def tick(self) -> None:
        """Take one sample. Public so tests can drive the tracker deterministically."""
        with self._lock:
            now = self._clock()
            last_tick, self._last_tick = self._last_tick, now
            if last_tick is not None and now - last_tick > self.GAP_SEC:
                self._close(last_tick)

            if self._paused:
                if self._paused_until is not None and now >= self._paused_until:
                    self.resume()
                else:
                    return

            idle = self._platform.idle_seconds() if self._idle_threshold else 0.0
            # Checkpoints only commit time up to the last input, so a session
            # that ends in idleness never has the idle stretch already counted.
            last_input = now - idle

            if self._platform.is_locked():
                self._close(last_input)
                self._status = STATUS_LOCKED
                return

            if self._idle_threshold and idle >= self._idle_threshold:
                self._close(last_input, was_idle=True)
                self._status = STATUS_IDLE
                return

            fg = self._platform.foreground_app()
            if fg is None:
                if self._app_id is not None and now >= self._next_checkpoint:
                    self._checkpoint(last_input)
                return

            # A focus change nobody caused (a popup while the user is away) should
            # not credit the away time to the previous app.
            switch_end = last_input if idle >= self.SWITCH_IDLE_SEC else now

            exe = catalog.canonical_exe(fg.exe_name)
            if not catalog.is_trackable(exe) or exe in self._excluded:
                self._close(switch_end)
                self._status = STATUS_WAITING
                return

            if exe == self._exe:
                self._status = STATUS_TRACKING
                if now >= self._next_checkpoint:
                    self._checkpoint(last_input)
                return

            self._close(switch_end)
            self._open(exe, fg.exe_path, now)

    # ------------------------------------------------------------------
    # Session bookkeeping (call with the lock held)
    # ------------------------------------------------------------------

    def _open(self, exe: str, exe_path: str | None, now: float) -> None:
        self._app_id = queries.get_or_create_app(exe, icon_path=exe_path)
        self._session_id = queries.start_session(self._app_id, now)
        self._exe = exe
        self._session_start = now
        self._committed_until = now
        self._next_checkpoint = now + self.CHECKPOINT_SEC
        self._status = STATUS_TRACKING

    def _checkpoint(self, now: float, was_idle: bool = False) -> None:
        """Commit focus time up to *now* (never moves backwards)."""
        if self._app_id is None or self._session_id is None:
            return
        end = max(now, self._committed_until)
        if end > self._committed_until:
            queries.add_focus_span(self._app_id, self._committed_until, end)
            self._committed_until = end
        queries.update_session_end(self._session_id, end, was_idle=was_idle)
        db.commit()
        self._next_checkpoint = self._clock() + self.CHECKPOINT_SEC

    def _close(self, end: float, was_idle: bool = False) -> None:
        if self._app_id is None:
            return
        try:
            self._checkpoint(end, was_idle=was_idle)
        finally:
            self._app_id = None
            self._exe = None
            self._session_id = None
            self._session_start = 0.0
            self._committed_until = 0.0
