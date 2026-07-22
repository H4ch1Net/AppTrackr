"""Tracker tests that run off-Windows.

These verify the module imports on any platform (a regression guard for the
lazy Win32 binding) and that its pure state helpers behave, plus that an
idle flush credits the active portion of a session.
"""

from __future__ import annotations

from apptrackr.core.tracker import Tracker
from apptrackr.data import db, queries


def test_import_and_construct():
    t = Tracker()
    assert t.paused is False
    assert t.current_exe is None
    assert t.session_elapsed_ms == 0


def test_pause_resume():
    t = Tracker()
    t.pause()
    assert t.paused is True
    t.resume()
    assert t.paused is False


def test_stop_without_start_is_safe():
    Tracker().stop()  # must not raise


def test_idle_flush_credits_active_time():
    """_flush_unlocked(end_ts=...) is what the idle path calls; ensure it keeps
    the pre-idle work rather than discarding the session."""
    t = Tracker()
    app_id = queries.get_or_create_app("foo.exe")
    start = 1000.0
    sid = queries.start_session(app_id, ts=start)
    t._state.current_app_id = app_id
    t._state.current_session_id = sid
    t._state.current_exe = "foo.exe"
    t._state.current_start = start

    active_end = start + 10 * 60  # 10 real minutes before idle
    t._flush_unlocked(end_ts=active_end)

    row = db.fetchone(
        "SELECT focused_ms FROM daily_rollup WHERE app_id = ?", (app_id,)
    )
    assert row["focused_ms"] == 10 * 60 * 1000
    assert t.current_app_id is None
