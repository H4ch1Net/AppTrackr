"""Upgrading from older releases keeps every record and keeps tracking.

The fixture is a database written by AppTrackr v1.0.2's own code (see
tests/fixtures/make_v1_fixture.py), so these tests exercise the real upgrade.
"""

import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from apptrackr import __version__, paths
from apptrackr.data import db, queries

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[1]


def _load_v1(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "data.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript((FIXTURES / "v1_0_2.sql").read_text(encoding="utf-8"))
    conn.close()
    return path


def _snapshot(path: Path) -> dict:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    q = lambda sql: [dict(r) for r in conn.execute(sql)]  # noqa: E731
    snap = {
        "apps": {r["exe_name"]: r for r in q("SELECT * FROM apps")},
        "sessions": q("SELECT * FROM usage_sessions ORDER BY session_id"),
        "rollup": q("SELECT * FROM daily_rollup"),
        "rules": q("SELECT * FROM reward_rules ORDER BY rule_id"),
        "events": q("SELECT * FROM reward_events ORDER BY event_id"),
        "profile": q("SELECT * FROM player_profile")[0],
        "village": json.loads(q("SELECT state_json FROM village_state")[0]["state_json"]),
        "settings": {r["key"]: r["value"] for r in q("SELECT * FROM settings")},
        "user_version": conn.execute("PRAGMA user_version").fetchone()[0],
    }
    conn.close()
    return snap


@pytest.fixture
def upgraded(tmp_path):
    """A v1.0.2 database opened by this version, plus snapshots from before and after."""
    folder = tmp_path / "AppTrackr"
    path = _load_v1(folder)
    before = _snapshot(path)
    paths.set_data_dir(folder)
    db.configure(path)
    db.init_db()
    db.close()
    return folder, before, _snapshot(path)


def _app_totals(snap: dict, field: str = "focused_ms") -> dict[str, int]:
    names = {a["app_id"]: exe for exe, a in snap["apps"].items()}
    totals: dict[str, int] = {}
    for row in snap["rollup"]:
        exe = names[row["app_id"]]
        totals[exe] = totals.get(exe, 0) + row[field]
    return totals


def test_fixture_is_a_v1_database():
    snap = _snapshot(_load_v1(Path(__import__("tempfile").mkdtemp()) / "AppTrackr"))
    assert snap["user_version"] == 0
    assert "is_hidden" not in next(iter(snap["apps"].values()))
    assert any(s["end_ts"] is None for s in snap["sessions"])  # v1.0 was closed mid-session
    assert any(s["was_idle"] for s in snap["sessions"])


def test_schema_is_upgraded_and_backed_up(upgraded):
    folder, before, after = upgraded
    assert after["user_version"] == db.SCHEMA_VERSION
    assert {"is_hidden", "daily_limit_ms"} <= set(next(iter(after["apps"].values())))
    backups = list(folder.glob("data-backup-schema0-*.sqlite"))
    assert len(backups) == 1
    assert _snapshot(backups[0]) == before  # the backup is the untouched v1.0 database


def test_apps_and_preferences_survive(upgraded):
    _folder, before, after = upgraded
    # The Steam helper process is folded into Steam; every other app is kept as it was.
    assert set(after["apps"]) == set(before["apps"]) - {"steamwebhelper.exe"}
    for exe in ("code.exe", "chrome.exe", "discord.exe"):
        for field in ("display_name", "icon_path", "is_favorite", "category"):
            assert after["apps"][exe][field] == before["apps"][exe][field]


def test_focused_time_is_kept_and_recovered(upgraded):
    _folder, before, after = upgraded
    idle_ms = int(before["settings"]["idle_threshold_sec"]) * 1000
    alias = {"steamwebhelper.exe": "steam.exe"}
    names = {a["app_id"]: exe for exe, a in before["apps"].items()}
    expected: dict[str, int] = {}
    for s in before["sessions"]:
        if s["end_ts"] is None:
            continue
        ms = s["duration_ms"] - (idle_ms if s["was_idle"] else 0)
        exe = alias.get(names[s["app_id"]], names[s["app_id"]])
        expected[exe] = expected.get(exe, 0) + max(0, ms)
    assert _app_totals(after) == expected

    old = _app_totals(before)
    old["steam.exe"] += old.pop("steamwebhelper.exe")
    for exe, ms in old.items():
        assert _app_totals(after)[exe] >= ms  # nothing v1.0 counted is lost
    assert sum(_app_totals(after).values()) > sum(old.values())  # idle-ended sessions are recovered


def test_opens_clicks_and_sessions_survive(upgraded):
    _folder, before, after = upgraded
    for field in ("opens_count", "clicks_count"):
        old = _app_totals(before, field)
        old["steam.exe"] = old.get("steam.exe", 0) + old.pop("steamwebhelper.exe", 0)
        assert _app_totals(after, field) == old
    closed = [s for s in before["sessions"] if s["end_ts"] is not None]
    assert len(after["sessions"]) == len(closed)


def test_rewards_village_and_settings_survive(upgraded):
    _folder, before, after = upgraded
    assert len(after["rules"]) == len(before["rules"])
    assert [(e["event_id"], e["claimed"]) for e in after["events"]] == [
        (e["event_id"], e["claimed"]) for e in before["events"]
    ]
    assert after["profile"] == before["profile"]
    assert after["village"] == before["village"]
    for key, value in before["settings"].items():
        assert after["settings"][key] == value


def test_upgraded_data_works_in_this_version(upgraded):
    folder, before, _after = upgraded
    db.configure(folder / "data.sqlite")
    from apptrackr.game import state as game_state
    from apptrackr.rewards import engine
    from apptrackr.ui import theme

    assert game_state.building_level(game_state.get_village(), "workshop") == 1
    # Upgrading the day after the last streak day: the running streak carries over.
    db.execute("UPDATE player_profile SET last_streak_day = ?", ((date.today() - timedelta(days=1)).isoformat(),))
    db.commit()
    assert engine.get_profile()["streak"] == before["profile"]["streak_days"]
    pending = engine.unclaimed_rewards()
    assert len(pending) == sum(1 for e in before["events"] if not e["claimed"])
    xp = engine.get_profile()["xp"]
    applied = engine.claim_reward(pending[0]["event_id"])
    assert engine.get_profile()["xp"] == xp + applied.get("xp", 0)
    # 1.x earning apps are the focus apps now, and the old village keeps working.
    from apptrackr.game import focus
    from apptrackr.rewards import rules

    assert focus.focus_app_ids() == {queries.find_app_id("code.exe")}
    assert rules.adopt_favorites_once() == 0
    inventory = dict(game_state.get_village()["inventory"])
    game_state.collect()
    village = game_state.get_village()
    assert all(village["inventory"][r] >= n for r, n in inventory.items())
    assert game_state.building_level(village, "workshop") == 1
    assert theme.configure(accent=db.get_setting("ui_theme")).accent == theme.build("Graphite", "Purple").accent
    assert db.get_int("idle_threshold_sec") == 600 and db.get_bool("minimize_to_tray", True) is False
    theme.configure("dark", theme.DEFAULT_ACCENT)


def test_tracking_continues_after_upgrade(upgraded):
    folder, _before, _after = upgraded
    db.configure(folder / "data.sqlite")
    from test_tracker import FakePlatform

    from apptrackr.core.tracker import Tracker

    start = datetime(2026, 10, 5, 12, 0).timestamp()
    clock = type("Clock", (), {"t": start, "__call__": lambda self: self.t})()
    platform = FakePlatform()
    tracker = Tracker(platform, clock=clock)
    tracker.reload_settings()
    platform.exe = "chrome.exe"
    tracker.tick()
    for _ in range(24):
        clock.t += 5
        tracker.tick()
    tracker.stop()
    app_id = queries.find_app_id("chrome.exe")
    assert queries.app_usage_on("2026-10-05", app_id) == 120_000
    assert queries.get_app(app_id)["category"] == "Work"  # same app row, not a new one


def test_second_start_does_nothing(upgraded):
    folder, _before, after = upgraded
    db.configure(folder / "data.sqlite")
    db.init_db()
    db.close()
    assert _snapshot(folder / "data.sqlite") == after
    assert len(list(folder.glob("data-backup-*.sqlite"))) == 1


def test_failed_migration_leaves_data_untouched(tmp_path, monkeypatch):
    folder = tmp_path / "AppTrackr"
    path = _load_v1(folder)
    before = _snapshot(path)

    def broken(conn):
        conn.execute("ALTER TABLE apps ADD COLUMN is_hidden INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE daily_rollup SET focused_ms = 0")
        raise RuntimeError("simulated crash halfway through an upgrade")

    monkeypatch.setattr(db, "_MIGRATIONS", [(1, broken)])
    paths.set_data_dir(folder)
    db.configure(path)
    with pytest.raises(RuntimeError):
        db.init_db()
    db.close()
    after = _snapshot(path)
    assert after["user_version"] == 0
    assert after["apps"] == before["apps"] and after["rollup"] == before["rollup"]


def test_v1_updater_finds_this_release():
    """v1.0.x checks releases with this logic (copied verbatim from v1.0.2's updater/check.py)."""

    def parse_version(v):
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))

    def v1_check(data, current="1.0.0"):
        remote_version = data.get("tag_name", "").lstrip("v")
        if parse_version(remote_version) > parse_version(current):
            for asset in data.get("assets", []):
                if asset.get("name", "").endswith(".exe"):
                    return {"version": remote_version, "url": asset["browser_download_url"]}
        return None

    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), "v1.0 can only parse plain x.y.z tags"
    workflow = (ROOT / ".github" / "workflows" / "release-windows.yml").read_text(encoding="utf-8")
    uploads = re.findall(r"(?:packaging/Output|dist)/(AppTrackr_[A-Za-z]+\.(?:exe|zip))", workflow)
    assert sorted(set(uploads)) == ["AppTrackr_Portable.zip", "AppTrackr_Setup.exe"]
    release = {
        "tag_name": f"v{__version__}",
        "assets": [{"name": n, "browser_download_url": f"https://example.invalid/{n}"} for n in sorted(set(uploads))],
    }
    assert v1_check(release) == {"version": __version__, "url": "https://example.invalid/AppTrackr_Setup.exe"}


def test_installer_upgrades_in_place():
    iss = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    assert re.search(r"^AppId=AppTrackr$", iss, re.M)  # v1.0's script had no AppId, so Inno used AppName
    assert "DefaultDirName={localappdata}\\AppTrackr" in iss
    assert "CloseApplications=force" in iss
    assert re.search(r"^Type: filesandordirs; Name: \"\{app\}\\_internal\"", iss, re.M)  # no stale libraries


def test_startup_entry_repair():
    from apptrackr.core.autostart import needs_repair

    ours = r"C:\Users\me\AppData\Local\AppTrackr\AppTrackr.exe"
    exists = lambda p: p.lower() == ours.lower()  # noqa: E731
    assert needs_repair(f'"{ours}"', ours, exists)  # v1.0 entry: no --minimized
    assert needs_repair(r'"D:\Downloads\AppTrackr.exe"', ours, lambda p: True)  # v1.0 portable copy
    assert not needs_repair(f'"{ours}" --minimized', ours, exists)
    assert needs_repair(r'"C:\Old\AppTrackr.exe" --minimized', ours, exists)  # points at a removed copy
    assert not needs_repair(r'"D:\Portable\AppTrackr.exe" --minimized', ours, lambda p: True)  # another 1.1+ copy


def test_newer_database_opens_untouched(tmp_path):
    folder = tmp_path / "AppTrackr"
    path = _load_v1(folder)
    paths.set_data_dir(folder)
    db.configure(path)
    db.init_db()
    db.execute(f"PRAGMA user_version = {db.SCHEMA_VERSION + 5}")  # as if a later version had migrated it
    db.commit()
    db.close()
    for backup in folder.glob("data-backup-*.sqlite"):
        backup.unlink()
    db.init_db()
    db.close()
    assert _snapshot(path)["user_version"] == db.SCHEMA_VERSION + 5
    assert not list(folder.glob("data-backup-*.sqlite"))


def test_every_page_opens_on_upgraded_data(upgraded):
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    from apptrackr.core.platform import NullPlatform
    from apptrackr.core.tracker import Tracker
    from apptrackr.ui.main import MainWindow, prepare_app

    folder, _before, _after = upgraded
    db.configure(folder / "data.sqlite")
    app = QApplication.instance() or QApplication([])
    prepare_app(app)
    tracker = Tracker(NullPlatform())
    win = MainWindow(tracker)
    win.show()
    for page in ("dashboard", "calendar", "apps", "rewards", "village", "settings"):
        win.show_page(page)
        app.processEvents()
        assert win._stack.currentWidget() is win._views[page]
    win.open_app(queries.find_app_id("code.exe"))
    app.processEvents()
    assert win._views["app"].title.text() == "VS Code"
    tracker.stop()
    win._quitting = True
    win.close()
    win.deleteLater()
    app.processEvents()
