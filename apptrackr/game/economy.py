"""Balance values for the focus village.

Focus points are the currency of everything: one minute in a focus app earns
one point times the current flow multiplier. Points turn into XP and, through
the village's buildings, into resources.
"""

from __future__ import annotations

XP_PER_LEVEL = 100
CREDITS_PER_LEVEL = 10  # granted per level reached, times the level number
XP_PER_POINT = 0.25  # about a level every three hours of good focus

RESOURCES = ("wood", "stone", "metal", "food", "blueprints")

# Flow: an unbroken run of focus-app time. (minutes into the run, multiplier, name)
FLOW_TIERS = (
    (0, 1.0, "Warming up"),
    (10, 1.5, "Focused"),
    (25, 2.0, "In the zone"),
    (45, 2.5, "Deep work"),
    (75, 3.0, "Flow"),
)
FLOW_GRACE_SEC = 180  # time away from focus apps that does not end a run
TAVERN_GRACE_SEC = 60  # extra grace per tavern level

# Resources produced per focus point: (producer building, amount per level, free levels)
PRODUCTION = {
    "wood": ("lumberyard", 0.25, 1),
    "stone": ("quarry", 0.15, 1),
    "food": ("farm", 0.20, 1),
    "metal": ("mine", 0.08, 0),
    "blueprints": ("lab", 0.0025, 0),
}
VILLAGER_PCT = 4  # production bonus per villager
MONUMENT_PCT = 15  # production bonus once the monument stands
WORKSHOP_XP_PCT = 5  # XP bonus per workshop level

BASE_RESOURCE_CAP = 200
STORAGE_GROWTH = 1.6

# Daily focus goal (minutes in focus apps), streaks and the chest it opens.
DEFAULT_GOAL_MIN = 120
GOAL_CHOICES = (30, 60, 90, 120, 180, 240, 360)


def chest_for(streak: int) -> dict:
    """What the daily chest holds on day *streak* of a goal streak."""
    reward = {"xp": 25, "credits": 20 + 5 * min(max(streak, 1), 10), "blueprints": 1}
    if streak and streak % 7 == 0:
        reward["blueprints"] += 1
        reward["credits"] += 50
    return reward


# Credits needed to buy a bundle of resources at the market.
MARKET = {
    "wood": (25, 5),
    "food": (25, 5),
    "stone": (20, 8),
    "metal": (10, 10),
    "blueprints": (1, 40),
}


def level_for_xp(xp: int) -> int:
    return 1 + max(0, xp) // XP_PER_LEVEL


def level_progress(xp: int) -> tuple[int, int]:
    """(XP earned inside the current level, XP the level requires)."""
    return max(0, xp) % XP_PER_LEVEL, XP_PER_LEVEL


def resource_cap(storage_level: int) -> int:
    return int(round(BASE_RESOURCE_CAP * STORAGE_GROWTH**storage_level, -1))


def tier_index(run_minutes: float) -> int:
    index = 0
    for i, (start, _mult, _name) in enumerate(FLOW_TIERS):
        if run_minutes >= start:
            index = i
    return index
