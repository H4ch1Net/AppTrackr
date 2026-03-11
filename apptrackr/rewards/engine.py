"""Reward evaluation engine – checks milestones and issues rewards."""

from __future__ import annotations

import json
import logging
import time
from datetime import date, timedelta

from ..data import db

log = logging.getLogger(__name__)


def evaluate(day: str | None = None) -> list[dict]:
    """Evaluate all enabled rules against the rollup for *day*. Returns newly granted rewards."""
    day = day or date.today().isoformat()
    if db.get_setting("rewards_enabled", "1") != "1":
        return []

    rules = db.fetchall("SELECT * FROM reward_rules WHERE enabled = 1")
    granted: list[dict] = []

    for rule in rules:
        app_id = rule["app_id"]
        metric = rule["metric"]
        threshold = rule["threshold"]

        # Get current metric value from rollup
        row = db.fetchone(
            f"SELECT COALESCE({metric}, 0) AS val FROM daily_rollup WHERE day = ? AND app_id = ?",
            (day, app_id),
        )
        if not row:
            continue
        current_val = row["val"]
        if current_val < threshold:
            continue

        # Check if already granted today for this rule
        if rule["repeatable"]:
            # For repeatable rules, count how many times threshold has been crossed
            times_earned = current_val // threshold
            times_granted = db.fetchone(
                "SELECT COUNT(*) AS cnt FROM reward_events WHERE rule_id = ? AND day = ?",
                (rule["rule_id"], day),
            )
            already = times_granted["cnt"] if times_granted else 0
            times_to_grant = times_earned - already
        else:
            existing = db.fetchone(
                "SELECT 1 FROM reward_events WHERE rule_id = ? AND app_id = ?",
                (rule["rule_id"], app_id),
            )
            if existing:
                continue
            times_to_grant = 1

        reward_json = rule["reward_json"]
        for _ in range(max(0, times_to_grant)):
            db.execute(
                "INSERT INTO reward_events (ts, app_id, rule_id, day, granted_json) VALUES (?, ?, ?, ?, ?)",
                (time.time(), app_id, rule["rule_id"], day, reward_json),
            )
            granted.append({"app_id": app_id, "rule_id": rule["rule_id"], "reward": json.loads(reward_json)})

    if granted:
        db.commit()
        log.info("Granted %d reward(s) for %s", len(granted), day)
    return granted


def unclaimed_rewards() -> list[dict]:
    rows = db.fetchall(
        "SELECT re.*, a.display_name, a.exe_name FROM reward_events re "
        "JOIN apps a ON a.app_id = re.app_id WHERE re.claimed = 0 ORDER BY re.ts DESC"
    )
    return [dict(r) for r in rows]


def claim_reward(event_id: int) -> dict | None:
    """Claim a reward event and apply it to the player profile."""
    row = db.fetchone("SELECT * FROM reward_events WHERE event_id = ? AND claimed = 0", (event_id,))
    if not row:
        return None

    reward = json.loads(row["granted_json"])

    # Apply XP/credits
    if "xp" in reward:
        db.execute("UPDATE player_profile SET xp = xp + ? WHERE profile_id = 1", (reward["xp"],))
        # Level up every 100 XP
        profile = db.fetchone("SELECT xp, level FROM player_profile WHERE profile_id = 1")
        if profile:
            new_level = 1 + profile["xp"] // 100
            if new_level > profile["level"]:
                db.execute("UPDATE player_profile SET level = ? WHERE profile_id = 1", (new_level,))

    if "credits" in reward:
        db.execute("UPDATE player_profile SET credits = credits + ? WHERE profile_id = 1", (reward["credits"],))

    # Apply resources to village inventory
    resource_keys = {"wood", "stone", "metal", "food", "blueprints"}
    village = db.fetchone("SELECT state_json FROM village_state WHERE profile_id = 1")
    if village:
        state = json.loads(village["state_json"])
        inv = state.get("inventory", {})
        for key in resource_keys:
            if key in reward:
                inv[key] = inv.get(key, 0) + reward[key]
        state["inventory"] = inv
        db.execute("UPDATE village_state SET state_json = ? WHERE profile_id = 1", (json.dumps(state),))

    db.execute("UPDATE reward_events SET claimed = 1 WHERE event_id = ?", (event_id,))
    db.commit()
    return reward


def claim_all() -> list[dict]:
    unclaimed = unclaimed_rewards()
    results = []
    for r in unclaimed:
        result = claim_reward(r["event_id"])
        if result:
            results.append(result)
    return results


def update_streak() -> int:
    """Update daily streak. Call once per day. Returns new streak count."""
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    profile = db.fetchone("SELECT * FROM player_profile WHERE profile_id = 1")
    if not profile:
        return 0

    if profile["last_streak_day"] == today:
        return profile["streak_days"]

    # Check if user tracked any favorite app for 30+ min today
    row = db.fetchone(
        "SELECT COALESCE(SUM(r.focused_ms), 0) AS total "
        "FROM daily_rollup r JOIN apps a ON a.app_id = r.app_id "
        "WHERE r.day = ? AND a.is_favorite = 1",
        (today,),
    )
    if not row or row["total"] < 30 * 60 * 1000:
        return profile["streak_days"]

    if profile["last_streak_day"] == yesterday:
        new_streak = profile["streak_days"] + 1
    else:
        new_streak = 1

    db.execute(
        "UPDATE player_profile SET streak_days = ?, last_streak_day = ? WHERE profile_id = 1",
        (new_streak, today),
    )
    db.commit()
    return new_streak


def get_profile() -> dict:
    row = db.fetchone("SELECT * FROM player_profile WHERE profile_id = 1")
    return dict(row) if row else {}
