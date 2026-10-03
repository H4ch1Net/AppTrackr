"""Reward evaluation: milestones per app, claiming, levels and streaks."""

from __future__ import annotations

import json
import logging
import time
from datetime import date, timedelta

from ..data import catalog, db
from ..game import economy
from ..game import state as game_state

log = logging.getLogger(__name__)


def enabled() -> bool:
    return db.get_bool("rewards_enabled", True)


def evaluate(day: str | None = None) -> list[dict]:
    """Grant rewards for milestones reached on *day*. Returns the new grants."""
    if not enabled():
        return []
    day = day or date.today().isoformat()
    granted: list[dict] = []
    rules = db.fetchall(
        "SELECT r.* FROM reward_rules r JOIN apps a ON a.app_id = r.app_id WHERE r.enabled = 1 AND a.is_hidden = 0"
    )
    for rule in rules:
        metric = rule["metric"]
        if metric not in ("focused_ms", "opens_count", "clicks_count"):
            continue
        row = db.fetchone(
            f"SELECT {metric} AS val FROM daily_rollup WHERE day = ? AND app_id = ?",
            (day, rule["app_id"]),
        )
        value = row["val"] if row else 0
        if value < rule["threshold"]:
            continue
        if rule["repeatable"]:
            earned = value // rule["threshold"]
            done = db.fetchone(
                "SELECT COUNT(*) AS n FROM reward_events WHERE rule_id = ? AND day = ?",
                (rule["rule_id"], day),
            )["n"]
            count = earned - done
        else:
            exists = db.fetchone("SELECT 1 FROM reward_events WHERE rule_id = ?", (rule["rule_id"],))
            count = 0 if exists else 1
        for _ in range(max(0, count)):
            db.execute(
                "INSERT INTO reward_events (ts, app_id, rule_id, day, granted_json) VALUES (?, ?, ?, ?, ?)",
                (time.time(), rule["app_id"], rule["rule_id"], day, rule["reward_json"]),
            )
            granted.append(
                {"app_id": rule["app_id"], "rule_id": rule["rule_id"], "reward": json.loads(rule["reward_json"])}
            )
    if granted:
        db.commit()
        log.info("Granted %d reward(s) for %s", len(granted), day)
    return granted


def evaluate_recent() -> list[dict]:
    """Evaluate today and yesterday, so milestones hit just before midnight are kept."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    return evaluate(yesterday) + evaluate()


def unclaimed_rewards() -> list[dict]:
    rows = db.fetchall(
        "SELECT re.*, a.display_name, a.exe_name, r.metric, r.threshold FROM reward_events re "
        "JOIN apps a ON a.app_id = re.app_id JOIN reward_rules r ON r.rule_id = re.rule_id "
        "WHERE re.claimed = 0 ORDER BY re.ts DESC"
    )
    out = []
    for r in rows:
        item = dict(r)
        item["name"] = catalog.display_name(item)
        item["reward"] = json.loads(item["granted_json"])
        out.append(item)
    return out


def unclaimed_by_app() -> list[dict]:
    """Pending rewards grouped per app, with summed amounts."""
    groups: dict[int, dict] = {}
    for item in unclaimed_rewards():
        group = groups.setdefault(
            item["app_id"],
            {
                "app_id": item["app_id"],
                "name": item["name"],
                "exe_name": item["exe_name"],
                "event_ids": [],
                "reward": {},
            },
        )
        group["event_ids"].append(item["event_id"])
        for key, value in item["reward"].items():
            group["reward"][key] = group["reward"].get(key, 0) + value
    return sorted(groups.values(), key=lambda g: -len(g["event_ids"]))


def unclaimed_count() -> int:
    row = db.fetchone("SELECT COUNT(*) AS n FROM reward_events WHERE claimed = 0")
    return row["n"] if row else 0


def _apply(reward: dict, bonus_pct: int = 0) -> dict:
    """Add a reward to the profile and village. Returns what was actually applied."""
    bonuses = game_state.get_bonuses()
    applied: dict = {}

    xp = int(reward.get("xp", 0))
    if xp:
        xp = round(xp * (100 + bonuses["xp_bonus_pct"] + bonus_pct) / 100)
        applied["xp"] = xp

    village = game_state.get_village()
    cap = game_state.resource_cap(village)
    inv = village["inventory"]
    for res in economy.RESOURCES:
        amount = int(reward.get(res, 0))
        if not amount:
            continue
        amount = round(amount * (100 + bonuses["resource_bonus_pct"] + bonus_pct) / 100)
        before = inv.get(res, 0)
        inv[res] = max(before, min(cap, before + amount))
        if inv[res] > before:
            applied[res] = inv[res] - before
    game_state.save_village(village)

    profile = get_profile()
    credits = int(reward.get("credits", 0))
    new_xp = profile["xp"] + xp
    new_level = max(profile["level"], economy.level_for_xp(new_xp))
    for lvl in range(profile["level"] + 1, new_level + 1):
        credits += economy.CREDITS_PER_LEVEL * lvl
    if new_level > profile["level"]:
        applied["level_up"] = new_level
    if credits:
        applied["credits"] = credits
    db.execute(
        "UPDATE player_profile SET xp = ?, level = ?, credits = credits + ? WHERE profile_id = 1",
        (new_xp, new_level, credits),
    )
    return applied


def claim_reward(event_id: int) -> dict | None:
    row = db.fetchone("SELECT * FROM reward_events WHERE event_id = ? AND claimed = 0", (event_id,))
    if not row:
        return None
    applied = _apply(json.loads(row["granted_json"]))
    db.execute("UPDATE reward_events SET claimed = 1 WHERE event_id = ?", (event_id,))
    db.commit()
    return applied


def claim_many(event_ids: list[int] | None = None) -> dict:
    """Claim the given pending rewards (all when None). Returns the summed amounts applied."""
    if event_ids is None:
        event_ids = [item["event_id"] for item in unclaimed_rewards()]
    total: dict = {}
    for event_id in event_ids:
        applied = claim_reward(event_id) or {}
        for key, value in applied.items():
            if key == "level_up":
                total[key] = max(total.get(key, 0), value)
            else:
                total[key] = total.get(key, 0) + value
    return total


# ---------------------------------------------------------------------------
# Profile and streaks
# ---------------------------------------------------------------------------


def get_profile() -> dict:
    row = db.fetchone("SELECT * FROM player_profile WHERE profile_id = 1")
    profile = dict(row) if row else {"xp": 0, "level": 1, "credits": 0, "streak_days": 0, "last_streak_day": None}
    profile["streak"] = current_streak(profile)
    return profile


def current_streak(profile: dict) -> int:
    """Streak length as of today: a streak survives until a full day is missed."""
    last = profile.get("last_streak_day")
    if not last:
        return 0
    today = date.today()
    if last in (today.isoformat(), (today - timedelta(days=1)).isoformat()):
        return int(profile.get("streak_days") or 0)
    return 0


def favorites_ms(day: str) -> int:
    row = db.fetchone(
        "SELECT COALESCE(SUM(r.focused_ms), 0) AS total FROM daily_rollup r "
        "JOIN apps a ON a.app_id = r.app_id WHERE r.day = ? AND a.is_favorite = 1 AND a.is_hidden = 0",
        (day,),
    )
    return row["total"] if row else 0


def update_streak(extra_ms: int = 0) -> dict | None:
    """Extend the streak once today's favorite-app goal is met.

    Returns {"streak": n, "reward": {...}} when the streak grew, else None.
    """
    today = date.today().isoformat()
    profile = get_profile()
    if profile.get("last_streak_day") == today:
        return None
    if favorites_ms(today) + extra_ms < economy.STREAK_GOAL_MS:
        return None
    streak = profile["streak"] + 1
    db.execute(
        "UPDATE player_profile SET streak_days = ?, last_streak_day = ? WHERE profile_id = 1",
        (streak, today),
    )
    result: dict = {"streak": streak}
    tier = economy.STREAK_REWARDS.get(streak)
    if tier and enabled():
        bonus = game_state.get_bonuses()["streak_bonus_pct"]
        result["reward"] = _apply(tier, bonus_pct=bonus)
    db.commit()
    return result


# ---------------------------------------------------------------------------
# Progress toward the next milestone
# ---------------------------------------------------------------------------


def next_milestones(day: str | None = None) -> list[dict]:
    """For each app earning rewards: today's focus time and the next focus milestone."""
    day = day or date.today().isoformat()
    rows = db.fetchall(
        "SELECT r.app_id, r.threshold, r.reward_json, r.repeatable, a.exe_name, a.display_name, "
        "a.icon_path, COALESCE(d.focused_ms, 0) AS focused_ms "
        "FROM reward_rules r JOIN apps a ON a.app_id = r.app_id "
        "LEFT JOIN daily_rollup d ON d.app_id = r.app_id AND d.day = ? "
        "WHERE r.enabled = 1 AND r.metric = 'focused_ms' AND a.is_hidden = 0 ORDER BY r.threshold",
        (day,),
    )
    by_app: dict[int, dict] = {}
    for r in rows:
        app = by_app.setdefault(
            r["app_id"],
            {
                "app_id": r["app_id"],
                "name": catalog.display_name(dict(r)),
                "exe_name": r["exe_name"],
                "icon_path": r["icon_path"],
                "focused_ms": r["focused_ms"],
                "next": None,
            },
        )
        used = r["focused_ms"]
        target = r["threshold"]
        if r["repeatable"]:
            target = (used // r["threshold"] + 1) * r["threshold"]
        elif used >= target:
            continue
        reward = json.loads(r["reward_json"])
        nxt = app["next"]
        if nxt is None or target < nxt["target_ms"]:
            app["next"] = {"target_ms": target, "reward": reward}
        elif target == nxt["target_ms"]:
            for key, value in reward.items():
                nxt["reward"][key] = nxt["reward"].get(key, 0) + value
    return sorted(by_app.values(), key=lambda a: a["name"].lower())
