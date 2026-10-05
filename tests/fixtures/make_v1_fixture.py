"""Regenerate tests/fixtures/v1_0_2.sql: a database written by AppTrackr v1.0.2's own code.

    python tests/fixtures/make_v1_fixture.py

Checks out the v1.0.2 tag into a temp folder, drives its data, rewards and
village modules through a few days of use (normal, idle-ended, cross-midnight
and unfinished sessions; opens and clicks; claimed and pending rewards; a
building; changed settings) and dumps the result as SQL. Timestamps are fixed,
so the output only changes if this script does.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TAG = "v1.0.2"
BASE = 1772366400.0  # 2026-03-01 12:00 UTC
DAY = 86400.0


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="apptrackr-v1-"))
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", TAG], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=BytesIO(archive)) as tar:
        tar.extractall(work / "src", filter="data")
    os.environ["APPDATA"] = str(work / "appdata")  # v1.0 keeps data.sqlite under %APPDATA%\AppTrackr
    sys.path.insert(0, str(work / "src"))

    from apptrackr.data import db, queries, rollup  # v1.0.2 modules
    from apptrackr.game import state
    from apptrackr.rewards import engine, rules

    db.init_db()
    code = queries.get_or_create_app("code.exe", icon_path=r"C:\Programs\VS Code\Code.exe")
    chrome = queries.get_or_create_app("chrome.exe")
    discord = queries.get_or_create_app("discord.exe")
    helper = queries.get_or_create_app("steamwebhelper.exe")  # folded into steam.exe by the v1.1 migration
    steam = queries.get_or_create_app("steam.exe")
    queries.set_favorite(code, True)
    queries.set_category(code, "Development")
    queries.set_category(chrome, "Work")

    def session(app_id: int, start: float, minutes: float, idle: bool = False) -> None:
        sid = queries.start_session(app_id, start)
        queries.end_session(sid, start + minutes * 60, was_idle=idle)
        rollup.rollup_session(sid)

    for d in range(4):
        t = BASE + d * DAY
        session(code, t, 95)
        session(chrome, t + 6000, 40)
        session(discord, t + 9000, 25)
        session(code, t + 11000, 50, idle=True)  # v1.0 dropped idle-ended sessions entirely
        session(helper, t + 15000, 12)
        session(steam, t + 16000, 30)
        day = _day(t)
        for _ in range(4 + d):
            queries.increment_opens(day, code)
        queries.increment_opens(day, chrome)
        queries.increment_clicks(day, code, 650 + 100 * d)
    session(chrome, BASE + 3 * DAY + 41000, 120)  # crosses midnight in most time zones
    queries.start_session(discord, BASE + 3 * DAY + 50000)  # never ended: v1.0 was closed mid-session

    rules.create_default_rules(code)
    rules.enable_app_rewards(code, True)
    for d in range(4):
        engine.evaluate(_day(BASE + d * DAY))
    pending = [r["event_id"] for r in engine.unclaimed_rewards()]
    for event_id in pending[: len(pending) // 2]:
        engine.claim_reward(event_id)
    village = state.get_village()
    village["inventory"].update({"wood": village["inventory"].get("wood", 0) + 40, "stone": 30})
    state._save_village(village)
    ok, message = state.build_or_upgrade("workshop")
    assert ok, message
    db.execute("UPDATE player_profile SET streak_days = 4, last_streak_day = ?", (_day(BASE + 3 * DAY),))
    db.commit()

    for key, value in {
        "ui_theme": "Purple",
        "idle_threshold_sec": "600",
        "track_clicks": "1",
        "autostart": "1",
        "minimize_to_tray": "0",
        "update_url": "https://api.github.com/repos/H4ch1Net/AppTrackr/releases/latest",
        "last_update_check_day": "2026-03-04",
    }.items():
        db.set_setting(key, value)

    source = sqlite3.connect(str(db._db_path()))
    dump = "\n".join(source.iterdump()) + "\n"
    out = HERE / "v1_0_2.sql"
    out.write_text(
        f"-- Written by AppTrackr {TAG} code via tests/fixtures/make_v1_fixture.py. Do not edit.\n" + dump,
        encoding="utf-8",
    )
    print(f"wrote {out} ({len(dump.splitlines())} lines)")
    return 0


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts).date().isoformat()


if __name__ == "__main__":
    os.environ["TZ"] = "UTC"  # fixed day boundaries for the fixture
    if hasattr(time, "tzset"):
        time.tzset()
    sys.exit(main())
