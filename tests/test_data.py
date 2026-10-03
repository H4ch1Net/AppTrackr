import json
import sqlite3

import pytest

from apptrackr.core.limits import LimitMonitor
from apptrackr.core.process_watch import ProcessWatcher
from apptrackr.data import catalog, db, demo, export, queries


def test_friendly_names():
    assert catalog.friendly_name("Code.exe") == "VS Code"
    assert catalog.friendly_name("my_cool-tool.exe") == "My Cool Tool"
    assert catalog.friendly_name("C:/Apps/obs64.exe") == "OBS Studio"
    assert catalog.display_name({"exe_name": "foo.exe", "display_name": "foo.exe"}) == "Foo"
    assert catalog.display_name({"exe_name": "foo.exe", "display_name": "Bar"}) == "Bar"


def test_noise_filters():
    assert not catalog.is_trackable("explorer.exe")
    assert not catalog.is_trackable("GoogleCrashHandler.exe")
    assert catalog.is_trackable("steamwebhelper.exe")  # aliased to steam.exe
    assert catalog.is_trackable("code.exe")


def test_top_apps_filters_and_sorts():
    demo.seed(days=14)
    today = queries.today_str()
    start = queries.days_ago(13)
    apps = queries.top_apps(start, today, limit=None)
    assert apps == sorted(apps, key=lambda a: -a["focused_ms"])
    assert all(a["exe_name"] not in demo.HIDDEN for a in apps)
    dev = queries.top_apps(start, today, category="Development", limit=None)
    assert dev and all(a["category"] == "Development" for a in dev)
    favs = queries.top_apps(start, today, favorites_only=True, limit=None)
    assert {a["exe_name"] for a in favs} <= {"code.exe", "obsidian.exe"}
    found = queries.top_apps(start, today, search="chrome", limit=None)
    assert [a["exe_name"] for a in found] == ["chrome.exe"]
    assert queries.total_ms(start, today) == sum(queries.daily_totals(start, today).values())


def test_history_is_zero_filled():
    app_id = queries.get_or_create_app("code.exe")
    history = queries.app_daily_history(app_id, days=7)
    assert len(history) == 7
    assert history[-1]["day"] == queries.today_str()


def test_launch_counting_counts_transitions_once():
    watcher = ProcessWatcher()
    app_id = queries.get_or_create_app("chrome.exe")
    watcher.check({"svchost.exe"}, now=0)
    watcher.check({"svchost.exe", "chrome.exe"}, now=5)
    watcher.check({"svchost.exe", "chrome.exe"}, now=10)
    watcher.check({"svchost.exe"}, now=15)
    watcher.check({"svchost.exe", "chrome.exe"}, now=20)
    row = db.fetchone("SELECT opens_count FROM daily_rollup WHERE app_id = ?", (app_id,))
    assert row["opens_count"] == 2
    assert queries.find_app_id("svchost.exe") is None


def test_launch_of_new_app_waits_for_first_focus():
    watcher = ProcessWatcher()
    watcher.check(set(), now=0)
    watcher.check({"figma.exe"}, now=5)
    assert queries.find_app_id("figma.exe") is None
    app_id = queries.get_or_create_app("figma.exe")  # tracker saw it in focus
    watcher.check({"figma.exe"}, now=10)
    row = db.fetchone("SELECT opens_count FROM daily_rollup WHERE app_id = ?", (app_id,))
    assert row["opens_count"] == 1


def test_limit_monitor_reports_once():
    app_id = queries.get_or_create_app("discord.exe")
    queries.set_daily_limit(app_id, 60_000)
    monitor = LimitMonitor()
    assert monitor.check() == []
    assert [a["app_id"] for a in monitor.check(live_app_id=app_id, live_ms=61_000)] == [app_id]
    assert monitor.check(live_app_id=app_id, live_ms=120_000) == []


def test_export_formats(tmp_path):
    demo.seed(days=3)
    n = export.export_csv(tmp_path / "out.csv")
    lines = (tmp_path / "out.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("day,exe_name,app")
    assert len(lines) == n + 1
    assert export.export_json(tmp_path / "out.json") == n
    assert len(json.loads((tmp_path / "out.json").read_text())) == n


def test_backup_and_restore_roundtrip(tmp_path):
    queries.get_or_create_app("code.exe")
    export.backup_db(tmp_path / "backup.sqlite")
    queries.get_or_create_app("chrome.exe")
    export.restore_db(tmp_path / "backup.sqlite")
    assert queries.find_app_id("code.exe") is not None
    assert queries.find_app_id("chrome.exe") is None


def test_restore_rejects_foreign_files(tmp_path):
    bogus = tmp_path / "bogus.sqlite"
    bogus.write_text("not a database")
    with pytest.raises(export.RestoreError):
        export.restore_db(bogus)
    other = tmp_path / "other.sqlite"
    sqlite3.connect(other).execute("CREATE TABLE t (x)").connection.close()
    with pytest.raises(export.RestoreError):
        export.restore_db(other)


def test_v1_migration_recovers_idle_sessions(tmp_path):
    legacy = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(legacy)
    conn.executescript("""
        CREATE TABLE apps (app_id INTEGER PRIMARY KEY AUTOINCREMENT, exe_name TEXT NOT NULL UNIQUE,
            display_name TEXT, icon_path TEXT, is_favorite INTEGER NOT NULL DEFAULT 0, category TEXT);
        CREATE TABLE usage_sessions (session_id INTEGER PRIMARY KEY AUTOINCREMENT, app_id INTEGER NOT NULL,
            start_ts REAL NOT NULL, end_ts REAL, duration_ms INTEGER, was_idle INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE daily_rollup (day TEXT NOT NULL, app_id INTEGER NOT NULL, focused_ms INTEGER NOT NULL DEFAULT 0,
            opens_count INTEGER NOT NULL DEFAULT 0, clicks_count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, app_id));
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO settings VALUES ('idle_threshold_sec', '300');
        INSERT INTO apps (exe_name) VALUES ('code.exe');
    """)
    from datetime import datetime

    start = datetime(2026, 2, 1, 10, 0).timestamp()
    # A 40 minute session that ended in idle (35 real minutes) was never counted by v1.0.
    conn.execute(
        "INSERT INTO usage_sessions (app_id, start_ts, end_ts, duration_ms, was_idle) VALUES (1, ?, ?, ?, 1)",
        (start, start + 2400, 2_400_000),
    )
    conn.execute(
        "INSERT INTO usage_sessions (app_id, start_ts, end_ts, duration_ms, was_idle) VALUES (1, ?, ?, ?, 0)",
        (start + 3600, start + 4200, 600_000),
    )
    conn.execute("INSERT INTO daily_rollup (day, app_id, focused_ms, opens_count) VALUES ('2026-02-01', 1, 600000, 7)")
    conn.commit()
    conn.close()

    db.configure(legacy)
    db.init_db()
    row = db.fetchone("SELECT focused_ms, opens_count FROM daily_rollup WHERE day = '2026-02-01'")
    assert row["focused_ms"] == 2_100_000 + 600_000
    assert row["opens_count"] == 7
    assert db.fetchone("PRAGMA user_version")[0] == db.SCHEMA_VERSION
    assert "is_hidden" in {r["name"] for r in db.fetchall("PRAGMA table_info(apps)")}
