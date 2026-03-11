"""Rollup engine – builds daily aggregates from raw sessions."""

from __future__ import annotations

import time
from datetime import date, datetime

from . import db, queries


def rollup_session(session_id: int) -> None:
    """Add a completed session's duration into the daily_rollup table."""
    row = db.fetchone(
        "SELECT app_id, start_ts, duration_ms, was_idle FROM usage_sessions WHERE session_id = ?",
        (session_id,),
    )
    if not row or row["duration_ms"] is None:
        return
    if row["was_idle"]:
        return  # Don't count idle time
    day = datetime.fromtimestamp(row["start_ts"]).date().isoformat()
    queries.add_focused_time(day, row["app_id"], row["duration_ms"])


def flush_current_session(app_id: int, session_id: int, now: float | None = None) -> int:
    """End the current session and roll it up. Returns new session_id."""
    now = now or time.time()
    queries.end_session(session_id, now)
    rollup_session(session_id)
    return queries.start_session(app_id, now)
