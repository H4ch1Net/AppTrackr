"""Progress: XP and levels, the daily focus goal and streak, and rewards from 1.x.

Focus points are earned in game.focus and banked by game.state.collect; this
module owns the profile they feed. Milestone rewards granted by AppTrackr 1.0
and 1.1 stay claimable here; no new ones are created.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from ..data import catalog, db
from ..game import economy
from ..game import state as game_state

log = logging.getLogger(__name__)


def enabled() -> bool:
    return db.get_bool("rewards_enabled", True)


# ---------------------------------------------------------------------------
# Profile, XP and levels
# ---------------------------------------------------------------------------


def get_profile() -> dict:
    row = db.fetchone("SELECT * FROM player_profile WHERE profile_id = 1")
    profile = dict(row) if row else {"xp": 0, "level": 1, "credits": 0, "streak_days": 0, "last_streak_day": None}
    profile["streak"] = current_streak(profile)
    return profile


def add_xp(xp: int, credits: int = 0) -> dict:
    """Add XP (and credits); level-ups pay credits too. Returns what was applied. Caller commits."""
    profile = get_profile()
    new_xp = profile["xp"] + max(0, int(xp))
    new_level = max(profile["level"], economy.level_for_xp(new_xp))
    for lvl in range(profile["level"] + 1, new_level + 1):
        credits += economy.CREDITS_PER_LEVEL * lvl
    db.execute(
        "UPDATE player_profile SET xp = ?, level = ?, credits = credits + ? WHERE profile_id = 1",
        (new_xp, new_level, credits),
    )
    applied: dict = {}
    if xp:
        applied["xp"] = int(xp)
    if credits:
        applied["credits"] = credits
    if new_level > profile["level"]:
        applied["level_up"] = new_level
    return applied


def apply_reward(reward: dict) -> dict:
    """Add a reward of XP, credits and resources (resources up to storage). Caller commits."""
    village = game_state.get_village()
    cap = game_state.resource_cap(village)
    applied: dict = {}
    for res in economy.RESOURCES:
        amount = int(reward.get(res, 0))
        if not amount:
            continue
        before = village["inventory"].get(res, 0)
        village["inventory"][res] = max(before, min(cap, before + amount))
        if village["inventory"][res] > before:
            applied[res] = village["inventory"][res] - before
    game_state.save_village(village)
    applied.update(add_xp(int(reward.get("xp", 0)), int(reward.get("credits", 0))))
    return applied


# ---------------------------------------------------------------------------
# Daily focus goal and streak
# ---------------------------------------------------------------------------


def goal_ms() -> int:
    minutes = db.get_int("focus_goal_min", economy.DEFAULT_GOAL_MIN)
    return max(5, minutes) * 60_000


def focus_ms(day: str) -> int:
    """Time in focus apps on *day* (from the daily totals)."""
    row = db.fetchone(
        "SELECT COALESCE(SUM(d.focused_ms), 0) AS total FROM daily_rollup d "
        "WHERE d.day = ? AND d.app_id IN (SELECT DISTINCT r.app_id FROM reward_rules r "
        "JOIN apps a ON a.app_id = r.app_id WHERE r.enabled = 1 AND a.is_hidden = 0)",
        (day,),
    )
    return row["total"] if row else 0


def current_streak(profile: dict) -> int:
    """Streak length as of today: a streak survives until a full day is missed."""
    last = profile.get("last_streak_day")
    if not last:
        return 0
    today = date.today()
    if last in (today.isoformat(), (today - timedelta(days=1)).isoformat()):
        return int(profile.get("streak_days") or 0)
    return 0


def update_streak(extra_ms: int = 0) -> dict | None:
    """Count today toward the streak once the focus goal is met, and unlock today's chest.

    *extra_ms* is live focus time not yet saved. Returns {"streak": n} when the
    streak grew, else None.
    """
    today = date.today().isoformat()
    profile = get_profile()
    if profile.get("last_streak_day") == today:
        return None
    if focus_ms(today) + extra_ms < goal_ms():
        return None
    streak = profile["streak"] + 1
    db.execute(
        "UPDATE player_profile SET streak_days = ?, last_streak_day = ? WHERE profile_id = 1",
        (streak, today),
    )
    db.commit()
    if enabled():
        game_state.unlock_chest(today)
    return {"streak": streak}


# ---------------------------------------------------------------------------
# Rewards granted by 1.0 and 1.1 (milestones); claimable, never created again
# ---------------------------------------------------------------------------


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


def unclaimed_count() -> int:
    row = db.fetchone("SELECT COUNT(*) AS n FROM reward_events WHERE claimed = 0")
    return row["n"] if row else 0


def claim_reward(event_id: int) -> dict | None:
    row = db.fetchone("SELECT * FROM reward_events WHERE event_id = ? AND claimed = 0", (event_id,))
    if not row:
        return None
    applied = apply_reward(json.loads(row["granted_json"]))
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


def attention_count() -> int:
    """Things waiting for the player: a chest to open, a harvest to collect, old rewards."""
    if not enabled():
        return 0
    count = len(game_state.ready_chests()) + unclaimed_count()
    if sum(game_state.harvest()["resources"].values()) >= 10:
        count += 1
    return count
