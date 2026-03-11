"""Reward rules configuration (defaults and helpers)."""

from __future__ import annotations

import json
from ..data import db


DEFAULT_RULES = [
    # (metric, threshold, reward_json, repeatable)
    ("focused_ms", 30 * 60 * 1000, {"xp": 10, "wood": 5}, True),
    ("focused_ms", 60 * 60 * 1000, {"xp": 25, "stone": 10}, True),
    ("focused_ms", 2 * 60 * 60 * 1000, {"xp": 60, "blueprints": 1}, True),
    ("focused_ms", 5 * 60 * 60 * 1000, {"xp": 150, "metal": 20}, True),
    ("opens_count", 10, {"xp": 5, "food": 5}, False),
    ("opens_count", 50, {"xp": 20, "wood": 10}, False),
    ("clicks_count", 500, {"xp": 10, "stone": 5}, False),
    ("clicks_count", 2000, {"xp": 30, "metal": 10}, False),
]


def create_default_rules(app_id: int) -> None:
    """Seed default reward rules for a given app."""
    for metric, threshold, reward, repeatable in DEFAULT_RULES:
        existing = db.fetchone(
            "SELECT 1 FROM reward_rules WHERE app_id = ? AND metric = ? AND threshold = ?",
            (app_id, metric, threshold),
        )
        if not existing:
            db.execute(
                "INSERT INTO reward_rules (app_id, metric, threshold, reward_json, repeatable, enabled) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (app_id, metric, threshold, json.dumps(reward), int(repeatable), 0),
            )
    db.commit()


def list_rules(app_id: int | None = None) -> list[dict]:
    if app_id is not None:
        rows = db.fetchall("SELECT * FROM reward_rules WHERE app_id = ?", (app_id,))
    else:
        rows = db.fetchall("SELECT * FROM reward_rules")
    return [dict(r) for r in rows]


def add_rule(app_id: int, metric: str, threshold: int, reward: dict,
             repeatable: bool = False) -> int:
    cur = db.execute(
        "INSERT INTO reward_rules (app_id, metric, threshold, reward_json, repeatable) "
        "VALUES (?, ?, ?, ?, ?)",
        (app_id, metric, threshold, json.dumps(reward), int(repeatable)),
    )
    db.commit()
    return cur.lastrowid  # type: ignore[return-value]


def toggle_rule(rule_id: int, enabled: bool) -> None:
    db.execute("UPDATE reward_rules SET enabled = ? WHERE rule_id = ?",
               (int(enabled), rule_id))
    db.commit()


def delete_rule(rule_id: int) -> None:
    db.execute("DELETE FROM reward_rules WHERE rule_id = ?", (rule_id,))
    db.commit()


def enable_app_rewards(app_id: int, enabled: bool = True) -> None:
    """Enable or disable all reward rules for a specific app."""
    db.execute("UPDATE reward_rules SET enabled = ? WHERE app_id = ?",
               (int(enabled), app_id))
    db.commit()


def app_rewards_enabled(app_id: int) -> bool:
    """Check if an app has any enabled reward rules."""
    row = db.fetchone(
        "SELECT COUNT(*) as cnt FROM reward_rules WHERE app_id = ? AND enabled = 1",
        (app_id,)
    )
    return row and row["cnt"] > 0


def ensure_app_rules(app_id: int) -> None:
    """Ensure an app has default reward rules created."""
    existing = db.fetchone(
        "SELECT COUNT(*) as cnt FROM reward_rules WHERE app_id = ?",
        (app_id,)
    )
    if not existing or existing["cnt"] == 0:
        create_default_rules(app_id)
