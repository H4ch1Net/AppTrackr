"""Neon Village: buildings, inventory and the credit market."""

from __future__ import annotations

import json

from ..data import db
from . import economy

BUILDINGS = {
    "workshop": {
        "wood": 20,
        "stone": 10,
        "unlock_level": 1,
        "max_level": 5,
        "desc": f"+{economy.WORKSHOP_XP_PCT}% XP from rewards per level",
    },
    "storage": {
        "wood": 15,
        "stone": 15,
        "unlock_level": 1,
        "max_level": 5,
        "desc": f"+{economy.STORAGE_CAP_PER_LEVEL} resource capacity per level",
    },
    "house": {"wood": 25, "food": 10, "unlock_level": 2, "max_level": 5, "desc": "+1 villager per level"},
    "lab": {
        "stone": 20,
        "metal": 15,
        "blueprints": 1,
        "unlock_level": 3,
        "max_level": 3,
        "desc": f"+{economy.LAB_RESOURCE_PCT}% resources from rewards per level",
    },
    "tavern": {
        "wood": 30,
        "food": 20,
        "unlock_level": 4,
        "max_level": 3,
        "desc": f"+{economy.TAVERN_STREAK_PCT}% streak rewards per level",
    },
    "monument": {
        "stone": 50,
        "metal": 30,
        "blueprints": 3,
        "unlock_level": 5,
        "max_level": 1,
        "desc": "Prestige crown on your profile",
    },
}


def get_village() -> dict:
    row = db.fetchone("SELECT state_json FROM village_state WHERE profile_id = 1")
    state = json.loads(row["state_json"]) if row else {}
    state.setdefault("buildings", {})
    state.setdefault("villagers", 0)
    inv = state.setdefault("inventory", {})
    for r in economy.RESOURCES:
        inv.setdefault(r, 0)
    return state


def save_village(state: dict) -> None:
    db.execute("UPDATE village_state SET state_json = ? WHERE profile_id = 1", (json.dumps(state),))


def building_level(village: dict, name: str) -> int:
    return int(village.get("buildings", {}).get(name, {}).get("level", 0))


def resource_cap(village: dict | None = None) -> int:
    village = village or get_village()
    return economy.resource_cap(building_level(village, "storage"))


def build_cost(name: str, current_level: int) -> dict[str, int]:
    spec = BUILDINGS[name]
    mult = current_level + 1
    return {r: spec[r] * mult for r in economy.RESOURCES if spec.get(r)}


def _player_level() -> int:
    row = db.fetchone("SELECT level FROM player_profile WHERE profile_id = 1")
    return row["level"] if row else 1


def can_build(name: str) -> tuple[bool, str]:
    """Check whether a building can be built or upgraded. Returns (ok, reason)."""
    if name not in BUILDINGS:
        return False, "Unknown building"
    spec = BUILDINGS[name]
    if _player_level() < spec["unlock_level"]:
        return False, f"Unlocks at level {spec['unlock_level']}"
    village = get_village()
    level = building_level(village, name)
    if level >= spec["max_level"]:
        return False, "Max level"
    inv = village["inventory"]
    missing = [f"{need - inv.get(r, 0)} {r}" for r, need in build_cost(name, level).items() if inv.get(r, 0) < need]
    if missing:
        return False, "Need " + ", ".join(missing)
    return True, "Ready"


def build_or_upgrade(name: str) -> tuple[bool, str]:
    ok, reason = can_build(name)
    if not ok:
        return False, reason
    village = get_village()
    level = building_level(village, name)
    for r, need in build_cost(name, level).items():
        village["inventory"][r] -= need
    village["buildings"][name] = {"level": level + 1}
    if name == "house":
        village["villagers"] = village.get("villagers", 0) + 1
    save_village(village)
    db.commit()
    verb = "built" if level == 0 else f"upgraded to level {level + 1}"
    return True, f"{name.title()} {verb}"


def buy(resource: str) -> tuple[bool, str]:
    """Spend credits on a bundle of *resource* at the market."""
    if resource not in economy.MARKET:
        return False, "Not for sale"
    amount, price = economy.MARKET[resource]
    profile = db.fetchone("SELECT credits FROM player_profile WHERE profile_id = 1")
    credits = profile["credits"] if profile else 0
    if credits < price:
        return False, f"Need {price - credits} more credits"
    village = get_village()
    cap = resource_cap(village)
    have = village["inventory"].get(resource, 0)
    if have >= cap:
        return False, f"{resource.title()} storage is full"
    village["inventory"][resource] = min(cap, have + amount)
    save_village(village)
    db.execute("UPDATE player_profile SET credits = credits - ? WHERE profile_id = 1", (price,))
    db.commit()
    return True, f"Bought {amount} {resource}"


def get_bonuses() -> dict:
    village = get_village()
    return {
        "xp_bonus_pct": building_level(village, "workshop") * economy.WORKSHOP_XP_PCT,
        "resource_bonus_pct": building_level(village, "lab") * economy.LAB_RESOURCE_PCT,
        "streak_bonus_pct": building_level(village, "tavern") * economy.TAVERN_STREAK_PCT,
        "resource_cap": resource_cap(village),
        "villagers": village.get("villagers", 0),
        "has_monument": building_level(village, "monument") >= 1,
    }
