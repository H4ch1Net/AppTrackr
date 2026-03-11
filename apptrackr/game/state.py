"""Neon Village game state and economy."""

from __future__ import annotations

import json

from ..data import db

# Building definitions: name → {cost, unlock_level, bonus_description}
BUILDINGS = {
    "workshop":  {"wood": 20, "stone": 10, "unlock_level": 1, "max_level": 5,
                  "desc": "Produces bonus XP (+5% per level)"},
    "storage":   {"wood": 15, "stone": 15, "unlock_level": 1, "max_level": 5,
                  "desc": "Increases resource cap (+50 per level)"},
    "house":     {"wood": 25, "food": 10, "unlock_level": 2, "max_level": 5,
                  "desc": "Adds +1 villager per level"},
    "lab":       {"stone": 20, "metal": 15, "blueprints": 1, "unlock_level": 3, "max_level": 3,
                  "desc": "Unlocks advanced reward tiers"},
    "tavern":    {"wood": 30, "food": 20, "unlock_level": 4, "max_level": 3,
                  "desc": "Streak bonuses +10% per level"},
    "monument":  {"stone": 50, "metal": 30, "blueprints": 3, "unlock_level": 5, "max_level": 1,
                  "desc": "Prestige! Cosmetic crown effect"},
}


def get_village() -> dict:
    row = db.fetchone("SELECT state_json FROM village_state WHERE profile_id = 1")
    if row:
        return json.loads(row["state_json"])
    return {"buildings": {}, "villagers": 0, "inventory": {
        "wood": 0, "stone": 0, "metal": 0, "food": 0, "blueprints": 0
    }}


def _save_village(state: dict) -> None:
    db.execute("UPDATE village_state SET state_json = ? WHERE profile_id = 1",
               (json.dumps(state),))
    db.commit()


def can_build(building_name: str) -> tuple[bool, str]:
    """Check if player can build/upgrade a building. Returns (ok, reason)."""
    if building_name not in BUILDINGS:
        return False, "Unknown building"

    spec = BUILDINGS[building_name]
    profile = db.fetchone("SELECT level FROM player_profile WHERE profile_id = 1")
    if not profile or profile["level"] < spec["unlock_level"]:
        return False, f"Requires player level {spec['unlock_level']}"

    village = get_village()
    current_level = village["buildings"].get(building_name, {}).get("level", 0)
    if current_level >= spec["max_level"]:
        return False, "Already at max level"

    inv = village.get("inventory", {})
    cost_mult = current_level + 1  # Cost scales with level
    for resource in ("wood", "stone", "metal", "food", "blueprints"):
        needed = spec.get(resource, 0) * cost_mult
        if inv.get(resource, 0) < needed:
            return False, f"Not enough {resource} (need {needed}, have {inv.get(resource, 0)})"

    return True, "OK"


def build_or_upgrade(building_name: str) -> tuple[bool, str]:
    """Attempt to build or upgrade a building. Returns (success, message)."""
    ok, reason = can_build(building_name)
    if not ok:
        return False, reason

    spec = BUILDINGS[building_name]
    village = get_village()
    current_level = village["buildings"].get(building_name, {}).get("level", 0)
    cost_mult = current_level + 1

    # Deduct resources
    inv = village.get("inventory", {})
    for resource in ("wood", "stone", "metal", "food", "blueprints"):
        needed = spec.get(resource, 0) * cost_mult
        if needed > 0:
            inv[resource] = inv.get(resource, 0) - needed

    # Upgrade building
    village["buildings"][building_name] = {"level": current_level + 1}

    # House gives villagers
    if building_name == "house":
        village["villagers"] = village.get("villagers", 0) + 1

    village["inventory"] = inv
    _save_village(village)
    return True, f"{building_name.title()} upgraded to level {current_level + 1}!"


def get_bonuses() -> dict:
    """Calculate active bonuses from buildings."""
    village = get_village()
    buildings = village.get("buildings", {})
    bonuses = {
        "xp_bonus_pct": 0,
        "resource_cap_bonus": 0,
        "streak_bonus_pct": 0,
        "villagers": village.get("villagers", 0),
        "has_monument": False,
    }
    if "workshop" in buildings:
        bonuses["xp_bonus_pct"] = buildings["workshop"].get("level", 0) * 5
    if "storage" in buildings:
        bonuses["resource_cap_bonus"] = buildings["storage"].get("level", 0) * 50
    if "tavern" in buildings:
        bonuses["streak_bonus_pct"] = buildings["tavern"].get("level", 0) * 10
    if "monument" in buildings:
        bonuses["has_monument"] = buildings["monument"].get("level", 0) >= 1
    return bonuses
