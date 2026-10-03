"""Per-app reward rules."""

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
