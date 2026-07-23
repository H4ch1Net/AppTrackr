"""Global daily goals – the zero-setup, always-on rewards loop.

Unlike per-app reward *rules* (an optional power-user feature), daily goals are
defined in code, enabled out of the box, and measured against your *total* usage
across every app. They give the game an immediate, self-driving loop: just use
your computer and resources flow in, which you spend building up the village,
which in turn boosts future rewards.
"""

from __future__ import annotations

import logging
from datetime import date

from ..data import db
from . import engine

log = logging.getLogger(__name__)

_MIN = 60 * 1000
_HOUR = 60 * _MIN

# (key, metric, threshold, reward). Thresholds are cumulative daily totals, so
# each goal fires once per day the moment your combined usage crosses it. Kept
# deliberately reachable for a casual day at the computer.
DAILY_GOALS = [
    ("focus_15m", "focused_ms", 15 * _MIN, {"xp": 10, "wood": 5, "food": 3}),
    ("focus_30m", "focused_ms", 30 * _MIN, {"xp": 15, "wood": 8, "stone": 4}),
    ("focus_1h", "focused_ms", 1 * _HOUR, {"xp": 25, "stone": 10, "food": 5}),
    ("focus_2h", "focused_ms", 2 * _HOUR, {"xp": 40, "metal": 8, "blueprints": 1}),
    ("focus_4h", "focused_ms", 4 * _HOUR, {"xp": 75, "metal": 15, "blueprints": 2, "credits": 25}),
    ("opens_15", "opens_count", 15, {"xp": 10, "wood": 6}),
    ("opens_40", "opens_count", 40, {"xp": 20, "stone": 8, "food": 4}),
]

# Resources produced per villager, per day, once claimed.
VILLAGER_INCOME = {"wood": 2, "food": 1}


def _day_totals(day: str) -> dict:
    row = db.fetchone(
        "SELECT COALESCE(SUM(focused_ms), 0) AS focused_ms, "
        "       COALESCE(SUM(opens_count), 0) AS opens_count "
        "FROM daily_rollup WHERE day = ?",
        (day,),
    )
    return {
        "focused_ms": row["focused_ms"] if row else 0,
        "opens_count": row["opens_count"] if row else 0,
    }


def evaluate_daily_goals(day: str | None = None) -> list[dict]:
    """Grant + auto-apply any daily goals reached today. Returns granted goals."""
    day = day or date.today().isoformat()
    if db.get_setting("rewards_enabled", "1") != "1":
        return []

    totals = _day_totals(day)
    granted: list[dict] = []

    for key, metric, threshold, reward in DAILY_GOALS:
        if totals.get(metric, 0) < threshold:
            continue
        if engine.goal_claimed(day, key):
            continue
        applied = engine.apply_reward(reward)
        engine.record_goal(day, key, applied)
        granted.append({"key": key, "reward": applied})

    granted += _grant_villager_income(day)

    if granted:
        log.info("Granted %d daily goal(s) for %s", len(granted), day)
    return granted


def _grant_villager_income(day: str) -> list[dict]:
    """Pay out passive resources from villagers once per day."""
    key = "villager_income"
    if engine.goal_claimed(day, key):
        return []
    try:
        from ..game import state as game_state
        villagers = game_state.get_village().get("villagers", 0)
    except Exception:  # pragma: no cover - defensive
        villagers = 0
    if villagers <= 0:
        return []

    reward = {res: amount * villagers for res, amount in VILLAGER_INCOME.items()}
    applied = engine.apply_reward(reward)
    engine.record_goal(day, key, applied)
    return [{"key": key, "reward": applied}]


def daily_summary(day: str | None = None) -> dict:
    """Progress snapshot for the UI: totals, per-goal status, and next goal."""
    day = day or date.today().isoformat()
    totals = _day_totals(day)
    goals = []
    next_goal = None
    for key, metric, threshold, reward in DAILY_GOALS:
        current = totals.get(metric, 0)
        done = current >= threshold
        goals.append(
            {
                "key": key,
                "metric": metric,
                "threshold": threshold,
                "current": current,
                "done": done,
                "reward": reward,
            }
        )
        if not done and next_goal is None:
            next_goal = goals[-1]
    return {"totals": totals, "goals": goals, "next_goal": next_goal}
