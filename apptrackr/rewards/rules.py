"""Per-app reward rules. An app with enabled rules is a focus app."""

from __future__ import annotations

import json

from ..data import db

MINUTE = 60 * 1000

# (metric, threshold, reward, repeatable)
DEFAULT_RULES = [
    ("focused_ms", 30 * MINUTE, {"xp": 10, "wood": 5}, True),
    ("focused_ms", 60 * MINUTE, {"xp": 25, "stone": 10}, True),
    ("focused_ms", 120 * MINUTE, {"xp": 60, "blueprints": 1}, True),
    ("focused_ms", 300 * MINUTE, {"xp": 150, "metal": 20}, True),
    ("opens_count", 3, {"xp": 5, "food": 5}, False),
    ("opens_count", 10, {"xp": 20, "wood": 10}, False),
    ("clicks_count", 500, {"xp": 10, "stone": 5}, False),
    ("clicks_count", 2000, {"xp": 30, "metal": 10}, False),
]


def ensure_app_rules(app_id: int) -> None:
    """Create the default (disabled) rule set for an app if it has none."""
    row = db.fetchone("SELECT COUNT(*) AS n FROM reward_rules WHERE app_id = ?", (app_id,))
    if row and row["n"]:
        return
    db.executemany(
        "INSERT INTO reward_rules (app_id, metric, threshold, reward_json, repeatable, enabled) "
        "VALUES (?, ?, ?, ?, ?, 0)",
        [(app_id, m, t, json.dumps(r), int(rep)) for m, t, r, rep in DEFAULT_RULES],
    )
    db.commit()


def enable_app_rewards(app_id: int, enabled: bool = True) -> None:
    ensure_app_rules(app_id)
    db.execute("UPDATE reward_rules SET enabled = ? WHERE app_id = ?", (int(enabled), app_id))
    db.commit()


def app_rewards_enabled(app_id: int) -> bool:
    row = db.fetchone("SELECT COUNT(*) AS n FROM reward_rules WHERE app_id = ? AND enabled = 1", (app_id,))
    return bool(row and row["n"])


def earning_app_ids() -> set[int]:
    return {r["app_id"] for r in db.fetchall("SELECT DISTINCT app_id FROM reward_rules WHERE enabled = 1")}


def adopt_favorites_once() -> int:
    """On the first start of 1.2: with no focus apps chosen yet, favorites become focus apps.

    Favorites drove the streak before 1.2; this keeps a streak growing after the
    update. Runs once; returns how many apps were adopted.
    """
    if db.get_bool("focus_apps_adopted"):
        return 0
    adopted = 0
    if not earning_app_ids():
        rows = db.fetchall("SELECT app_id FROM apps WHERE is_favorite = 1 AND is_hidden = 0")
        for row in rows:
            enable_app_rewards(row["app_id"], True)
        adopted = len(rows)
    db.set_setting("focus_apps_adopted", True)
    return adopted
