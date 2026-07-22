"""Tests for session recording, rollup, and the idle-time accounting fix."""

from __future__ import annotations

from apptrackr.data import db, queries, rollup


def _focused_ms(app_id: int, day: str) -> int:
    row = db.fetchone(
        "SELECT focused_ms FROM daily_rollup WHERE day = ? AND app_id = ?",
        (day, app_id),
    )
    return row["focused_ms"] if row else 0


def test_session_duration_clamped_non_negative():
    app_id = queries.get_or_create_app("foo.exe")
    sid = queries.start_session(app_id, ts=1000.0)
    # End before start (clock skew / bad idle timestamp) must not go negative.
    queries.end_session(sid, ts=900.0)
    row = db.fetchone("SELECT duration_ms FROM usage_sessions WHERE session_id = ?", (sid,))
    assert row["duration_ms"] == 0


def test_rollup_counts_completed_session():
    app_id = queries.get_or_create_app("foo.exe")
    sid = queries.start_session(app_id, ts=1000.0)
    queries.end_session(sid, ts=1005.0)  # 5 seconds
    rollup.rollup_session(sid)
    day = __import__("datetime").datetime.fromtimestamp(1000.0).date().isoformat()
    assert _focused_ms(app_id, day) == 5000


def test_rollup_skips_idle_session():
    app_id = queries.get_or_create_app("foo.exe")
    sid = queries.start_session(app_id, ts=1000.0)
    queries.end_session(sid, ts=1005.0, was_idle=True)
    rollup.rollup_session(sid)
    day = __import__("datetime").datetime.fromtimestamp(1000.0).date().isoformat()
    assert _focused_ms(app_id, day) == 0


def test_idle_preserves_active_time():
    """The core regression: going idle mid-session keeps the pre-idle work time.

    A 20-minute session followed by crossing the idle threshold should credit
    the active minutes, ending the session at the moment of last input rather
    than discarding everything.
    """
    app_id = queries.get_or_create_app("foo.exe")
    start = 1000.0
    active_end = start + 20 * 60  # 20 min of real work before going idle
    sid = queries.start_session(app_id, ts=start)
    # This mirrors Tracker._flush_unlocked(end_ts=active_end) on idle.
    queries.end_session(sid, ts=active_end, was_idle=False)
    rollup.rollup_session(sid)
    day = __import__("datetime").datetime.fromtimestamp(start).date().isoformat()
    assert _focused_ms(app_id, day) == 20 * 60 * 1000


def test_flush_current_session_helper():
    app_id = queries.get_or_create_app("foo.exe")
    sid = queries.start_session(app_id, ts=1000.0)
    new_sid = rollup.flush_current_session(app_id, sid, now=1002.0)
    assert new_sid != sid
    # Old session rolled up (2s), new one open.
    row = db.fetchone("SELECT end_ts FROM usage_sessions WHERE session_id = ?", (new_sid,))
    assert row["end_ts"] is None
