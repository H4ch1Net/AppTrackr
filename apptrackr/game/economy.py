"""Balance values for rewards and the village."""

from __future__ import annotations

XP_PER_LEVEL = 100
CREDITS_PER_LEVEL = 10  # granted per level reached, times the level number

RESOURCES = ("wood", "stone", "metal", "food", "blueprints")
BASE_RESOURCE_CAP = 100
STORAGE_CAP_PER_LEVEL = 50

WORKSHOP_XP_PCT = 5  # bonus XP per workshop level
LAB_RESOURCE_PCT = 10  # bonus resources per lab level
TAVERN_STREAK_PCT = 10  # bonus streak rewards per tavern level

STREAK_GOAL_MS = 30 * 60 * 1000  # favorite-app time needed for a streak day

STREAK_REWARDS = {
    3: {"xp": 20, "wood": 10, "food": 5},
    7: {"xp": 50, "stone": 15, "metal": 5},
    14: {"xp": 100, "metal": 20, "blueprints": 1},
    30: {"xp": 250, "blueprints": 2, "credits": 50},
}

# Credits needed to buy a bundle of resources at the market.
MARKET = {
    "wood": (10, 5),
    "food": (10, 5),
    "stone": (10, 8),
    "metal": (5, 10),
    "blueprints": (1, 40),
}


def level_for_xp(xp: int) -> int:
    return 1 + max(0, xp) // XP_PER_LEVEL


def xp_for_level(level: int) -> int:
    """Total XP needed to reach *level*."""
    return (max(1, level) - 1) * XP_PER_LEVEL


def level_progress(xp: int) -> tuple[int, int]:
    """(XP earned inside the current level, XP the level requires)."""
    return max(0, xp) % XP_PER_LEVEL, XP_PER_LEVEL


def resource_cap(storage_level: int) -> int:
    return BASE_RESOURCE_CAP + STORAGE_CAP_PER_LEVEL * storage_level
