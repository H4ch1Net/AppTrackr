from datetime import datetime, timedelta

from apptrackr.core.platform import ForegroundApp
from apptrackr.core.tracker import STATUS_IDLE, STATUS_LOCKED, STATUS_PAUSED, STATUS_TRACKING, Tracker
from apptrackr.data import db, queries


class FakePlatform:
    supported = True

    def __init__(self):
        self.exe = None
        self.idle = 0.0
        self.locked = False

    def foreground_app(self):
        return ForegroundApp(1, self.exe, None) if self.exe else None

    def idle_seconds(self):
        return self.idle

    def is_locked(self):
        return self.locked


class Clock:
    def __init__(self, start):
        self.t = start

    def __call__(self):
        return self.t


def make(start=None):
    start = start or datetime(2026, 3, 10, 12, 0).timestamp()
    platform, clock = FakePlatform(), Clock(start)
    tracker = Tracker(platform, clock=clock)
    tracker.reload_settings()
    return tracker, platform, clock


def focused(exe, day="2026-03-10"):
    app_id = queries.find_app_id(exe)
    return queries.app_usage_on(day, app_id) if app_id else 0


def test_switching_apps_records_time():
    tracker, platform, clock = make()
    platform.exe = "code.exe"
    tracker.tick()
    clock.t += 120
    platform.exe = "chrome.exe"
    tracker.tick()
    clock.t += 60
    tracker.stop()
    assert focused("code.exe") == 120_000
    assert focused("chrome.exe") == 60_000


def test_checkpoints_make_totals_live():
    tracker, platform, clock = make()
    platform.exe = "code.exe"
    tracker.tick()
    clock.t += Tracker.CHECKPOINT_SEC + 1
    tracker.tick()
    assert focused("code.exe") == (Tracker.CHECKPOINT_SEC + 1) * 1000
    assert tracker.snapshot().status == STATUS_TRACKING


def test_idle_session_is_counted_up_to_last_input():
    tracker, platform, clock = make()
    platform.exe = "code.exe"
    tracker.tick()
    # Work for 10 minutes with checkpoints, then go idle past the threshold.
    for _ in range(20):
        clock.t += 30
        tracker.tick()
    for _ in range(11):
        clock.t += 30
        platform.idle += 30
        tracker.tick()
    assert tracker.snapshot().status == STATUS_IDLE
    assert focused("code.exe") == 600_000


def test_lock_stops_tracking():
    tracker, platform, clock = make()
    platform.exe = "code.exe"
    tracker.tick()
    clock.t += 45
    platform.locked = True
    tracker.tick()
    assert tracker.snapshot().status == STATUS_LOCKED
    clock.t += 600
    tracker.tick()
    assert focused("code.exe") == 45_000


def test_midnight_split():
    start = datetime(2026, 3, 10, 23, 59).timestamp()
    tracker, platform, clock = make(start)
    platform.exe = "code.exe"
    tracker.tick()
    clock.t += 180
    tracker.stop()
    assert focused("code.exe", "2026-03-10") == 60_000
    assert focused("code.exe", "2026-03-11") == 120_000


def test_system_and_excluded_apps_are_ignored():
    tracker, platform, clock = make()
    platform.exe = "code.exe"
    tracker.tick()
    clock.t += 30
    platform.exe = "explorer.exe"
    tracker.tick()
    clock.t += 300
    platform.exe = "code.exe"
    tracker.tick()
    clock.t += 30
    tracker.stop()
    assert focused("code.exe") == 60_000
    assert queries.find_app_id("explorer.exe") is None

    queries.set_hidden(queries.find_app_id("code.exe"), True)
    tracker.reload_settings()
    tracker.tick()
    clock.t += 100
    tracker.stop()
    assert focused("code.exe") == 60_000


def test_timed_pause_resumes():
    tracker, platform, clock = make()
    platform.exe = "code.exe"
    tracker.pause(minutes=15)
    tracker.tick()
    assert tracker.snapshot().status == STATUS_PAUSED
    clock.t += 15 * 60
    tracker.tick()
    assert not tracker.paused
    assert tracker.snapshot().app_id is not None


def test_helper_alias_folds_into_app():
    tracker, platform, clock = make()
    platform.exe = "steamwebhelper.exe"
    tracker.tick()
    clock.t += 10
    tracker.stop()
    assert focused("steam.exe") == 10_000


def test_session_rows_have_durations():
    tracker, platform, clock = make()
    platform.exe = "code.exe"
    tracker.tick()
    clock.t += 90
    tracker.stop()
    rows = db.fetchall("SELECT duration_ms FROM usage_sessions")
    assert [r["duration_ms"] for r in rows] == [90_000]
    hours = queries.hourly_totals("2026-03-10")
    assert hours[12] == 90_000 and sum(hours) == 90_000


def test_split_by_day_spans_multiple_days():
    from apptrackr.data.spans import split_by_day

    start = datetime(2026, 1, 1, 22, 0)
    parts = split_by_day(start.timestamp(), (start + timedelta(hours=28)).timestamp())
    assert [p[0] for p in parts] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert sum(p[1] for p in parts) == 28 * 3600 * 1000
