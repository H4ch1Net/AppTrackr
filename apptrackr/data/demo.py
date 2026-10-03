"""Deterministic sample data for --demo, screenshots and tests."""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta

from . import db
from .spans import split_by_day

# exe, category, weekday weight, weekend weight, favorite
DEMO_APPS = [
    ("code.exe", "Development", 3.4, 0.9, True),
    ("chrome.exe", "Work", 2.2, 1.7, False),
    ("windowsterminal.exe", "Development", 1.1, 0.2, False),
    ("slack.exe", "Communication", 0.9, 0.1, False),
    ("figma.exe", "Work", 0.8, 0.1, False),
    ("obsidian.exe", "Study", 0.6, 0.7, True),
    ("discord.exe", "Social", 0.6, 1.3, False),
    ("spotify.exe", "Entertainment", 0.3, 0.5, False),
    ("olk.exe", "Communication", 0.5, 0.05, False),
    ("excel.exe", "Work", 0.4, 0.02, False),
    ("steam.exe", "Games", 0.05, 1.6, False),
    ("notion.exe", "Work", 0.35, 0.25, False),
    ("ms-teams.exe", "Communication", 0.4, 0.0, False),
]
HIDDEN = {"ms-teams.exe"}
LIMITS = {"discord.exe": 45 * 60 * 1000}
REWARD_APPS = ("code.exe", "obsidian.exe", "chrome.exe")


def _day_blocks(rng: random.Random, weekend: bool) -> list[tuple[float, float]]:
    """Active hour ranges for a day."""
    if weekend:
        blocks = [
            (10.5 + rng.random(), 13 + rng.random()),
            (15 + rng.random(), 17.5 + rng.random()),
            (20 + rng.random(), 23 + rng.random() * 0.6),
        ]
        return [b for b in blocks if rng.random() < 0.8]
    start = 8.4 + rng.random() * 1.0
    return [
        (start, 12.2 + rng.random() * 0.5),
        (13.1 + rng.random() * 0.4, 17.6 + rng.random() * 1.2),
        (20.3 + rng.random(), 22.0 + rng.random()),
    ]


def seed(days: int = 120, seed_value: int = 7, now: datetime | None = None) -> None:
    """Fill the configured database with sample history ending at *now*."""
    rng = random.Random(seed_value)
    now = now or datetime.now()
    db.init_db()

    app_ids: dict[str, int] = {}
    for exe, category, _wd, _we, fav in DEMO_APPS:
        cur = db.execute(
            "INSERT OR IGNORE INTO apps (exe_name, display_name, is_favorite, category, is_hidden, daily_limit_ms) "
            "VALUES (?, NULL, ?, ?, ?, ?)",
            (exe, int(fav), category, int(exe in HIDDEN), LIMITS.get(exe)),
        )
        row = db.fetchone("SELECT app_id FROM apps WHERE exe_name = ?", (exe,))
        app_ids[exe] = row["app_id"] if row else int(cur.lastrowid)

    sessions: list[tuple] = []
    rollup: dict[tuple[str, int], list[int]] = {}
    cutoff = now.timestamp() - 90

    for offset in range(days, -1, -1):
        d = now.date() - timedelta(days=offset)
        weekend = d.weekday() >= 5
        if rng.random() < (0.12 if weekend else 0.04):
            continue  # a day off
        weights = [(exe, we if weekend else wd) for exe, _c, wd, we, _f in DEMO_APPS]
        exes = [w[0] for w in weights]
        wts = [w[1] for w in weights]
        for start_h, end_h in _day_blocks(rng, weekend):
            t = datetime.combine(d, datetime.min.time()).timestamp() + start_h * 3600
            end = datetime.combine(d, datetime.min.time()).timestamp() + end_h * 3600
            while t < end and t < cutoff:
                exe = rng.choices(exes, wts)[0]
                length = min(rng.expovariate(1 / (14 * 60)) + 45, 75 * 60)
                stop = min(t + length, end, cutoff)
                if stop - t >= 5:
                    sessions.append((app_ids[exe], t, stop, int((stop - t) * 1000)))
                    for day, ms in split_by_day(t, stop):
                        rollup.setdefault((day, app_ids[exe]), [0, 0, 0])[0] += ms
                t = stop + rng.choice((2, 5, 10, 30, 60, 240))

    for vals in rollup.values():
        minutes = vals[0] / 60000
        vals[1] = max(1, min(6, int(minutes // 50) + rng.randint(0, 2)))
        vals[2] = int(minutes * rng.uniform(8, 30))

    db.executemany("INSERT INTO usage_sessions (app_id, start_ts, end_ts, duration_ms) VALUES (?, ?, ?, ?)", sessions)
    db.executemany(
        "INSERT INTO daily_rollup (day, app_id, focused_ms, opens_count, clicks_count) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(day, app_id) DO UPDATE SET focused_ms = excluded.focused_ms, "
        "opens_count = excluded.opens_count, clicks_count = excluded.clicks_count",
        [(day, app_id, *vals) for (day, app_id), vals in rollup.items()],
    )

    _seed_rewards(app_ids)
    for key, value in {"track_clicks": "1", "auto_update_check": "0"}.items():
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    db.commit()


def _seed_rewards(app_ids: dict[str, int]) -> None:
    from ..rewards import engine, rules

    for exe in REWARD_APPS:
        rules.enable_app_rewards(app_ids[exe], True)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    engine.evaluate(yesterday)
    db.execute("UPDATE reward_events SET claimed = 1")
    db.execute(
        "UPDATE player_profile SET xp = 1240, level = 13, credits = 85, streak_days = 9, "
        "last_streak_day = ? WHERE profile_id = 1",
        (yesterday,),
    )
    village = {
        "buildings": {"workshop": {"level": 3}, "storage": {"level": 2}, "house": {"level": 2}, "lab": {"level": 1}},
        "villagers": 2,
        "inventory": {"wood": 142, "stone": 96, "metal": 38, "food": 61, "blueprints": 3},
    }
    db.execute("UPDATE village_state SET state_json = ? WHERE profile_id = 1", (json.dumps(village),))
