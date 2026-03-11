"""Economy / balance tables for the Neon Village."""

# XP required per level (cumulative, so level N needs LEVEL_XP[N] total)
def xp_for_level(level: int) -> int:
    return level * 100

# Streak reward tiers
STREAK_REWARDS = {
    3:  {"xp": 20, "wood": 10, "food": 5},
    7:  {"xp": 50, "stone": 15, "metal": 5},
    14: {"xp": 100, "metal": 20, "blueprints": 1},
    30: {"xp": 250, "blueprints": 2, "credits": 50},
}
