"""The focus village: buildings, production, harvests, the daily chest and the market.

The village works while you focus: every focus point earned in a focus app
produces resources at the rates its buildings set. Production waits in the
harvest until you collect it, up to what storage can hold.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime

from ..data import db
from . import economy, focus

# cost: resources for level 1; each further level costs `growth` times more.
BUILDINGS = {
    "lumberyard": {
        "cost": {"wood": 15},
        "growth": 1.55,
        "unlock_level": 1,
        "max_level": 30,
        "desc": "Cuts wood while you focus",
    },
    "quarry": {
        "cost": {"wood": 25},
        "growth": 1.55,
        "unlock_level": 1,
        "max_level": 30,
        "desc": "Breaks stone while you focus",
    },
    "storage": {
        "cost": {"wood": 30, "stone": 20},
        "growth": 1.6,
        "unlock_level": 1,
        "max_level": 20,
        "desc": "Holds more of every resource",
    },
    "farm": {
        "cost": {"wood": 20, "stone": 10},
        "growth": 1.55,
        "unlock_level": 2,
        "max_level": 30,
        "desc": "Grows food while you focus",
    },
    "house": {
        "cost": {"wood": 40, "food": 20},
        "growth": 1.7,
        "unlock_level": 2,
        "max_level": 10,
        "desc": f"Each villager adds {economy.VILLAGER_PCT}% to all production",
    },
    "workshop": {
        "cost": {"wood": 30, "stone": 20},
        "growth": 1.6,
        "unlock_level": 2,
        "max_level": 10,
        "desc": f"+{economy.WORKSHOP_XP_PCT}% XP from focus per level",
    },
    "mine": {
        "cost": {"wood": 40, "stone": 30},
        "growth": 1.6,
        "unlock_level": 3,
        "max_level": 30,
        "desc": "Digs metal while you focus",
    },
    "lab": {
        "cost": {"stone": 60, "metal": 25},
        "growth": 1.8,
        "unlock_level": 4,
        "max_level": 10,
        "desc": "Draws blueprints while you focus",
    },
    "tavern": {
        "cost": {"wood": 80, "food": 50},
        "growth": 2.0,
        "unlock_level": 5,
        "max_level": 5,
        "desc": f"Flow survives {economy.TAVERN_GRACE_SEC // 60} more minute away per level",
    },
    "monument": {
        "cost": {"stone": 400, "metal": 200, "blueprints": 5},
        "growth": 1.0,
        "unlock_level": 10,
        "max_level": 1,
        "desc": f"A crown for your profile and +{economy.MONUMENT_PCT}% production",
    },
}


def get_village() -> dict:
    row = db.fetchone("SELECT state_json FROM village_state WHERE profile_id = 1")
    state = json.loads(row["state_json"]) if row else {}
    state.setdefault("buildings", {})
    state.setdefault("villagers", 0)
    state.setdefault("chests", {})
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
    factor = spec["growth"] ** current_level
    return {r: int(round(amount * factor)) for r, amount in spec["cost"].items()}


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
    cost = build_cost(name, level)
    cap = resource_cap(village)
    if any(need > cap for need in cost.values()):
        return False, "Needs a bigger storage"
    missing = [f"{need - inv.get(r, 0)} {r}" for r, need in cost.items() if inv.get(r, 0) < need]
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
    label = name.title() if name != "lumberyard" else "Lumberyard"
    return True, f"{label} {'built' if level == 0 else f'upgraded to level {level + 1}'}"


def get_bonuses(village: dict | None = None) -> dict:
    village = village or get_village()
    villagers = village.get("villagers", 0)
    monument = building_level(village, "monument") >= 1
    return {
        "xp_bonus_pct": building_level(village, "workshop") * economy.WORKSHOP_XP_PCT,
        "production_pct": villagers * economy.VILLAGER_PCT + (economy.MONUMENT_PCT if monument else 0),
        "grace_sec": focus.grace_sec(building_level(village, "tavern")),
        "resource_cap": resource_cap(village),
        "villagers": villagers,
        "has_monument": monument,
    }


def production_rates(village: dict | None = None) -> dict[str, float]:
    """Resources produced per focus point."""
    village = village or get_village()
    boost = 1 + get_bonuses(village)["production_pct"] / 100
    rates = {}
    for res, (building, per_level, free) in economy.PRODUCTION.items():
        level = building_level(village, building) + free
        if level:
            rates[res] = per_level * level * boost
    return rates


# ---------------------------------------------------------------------------
# Harvest
# ---------------------------------------------------------------------------


def _start_of_today() -> float:
    today = date.today()
    return datetime(today.year, today.month, today.day).timestamp()


def harvest(now: float | None = None, village: dict | None = None) -> dict:
    """What collecting now would bring: focus since the last collection, turned into XP and resources."""
    now = now or time.time()
    village = village or get_village()
    since = float(village.get("collected_until") or _start_of_today())
    points, focus_ms = focus.points_between(since, now, building_level(village, "tavern"))
    carry = village.get("carry", {})
    cap = resource_cap(village)
    resources, full = {}, []
    for res, rate in production_rates(village).items():
        made = points * rate + carry.get(res, 0.0)
        room = max(0, cap - village["inventory"].get(res, 0))
        amount = min(int(made), room)
        if amount:
            resources[res] = amount
        if int(made) >= room and rate:
            full.append(res)
    xp = points * economy.XP_PER_POINT * (1 + get_bonuses(village)["xp_bonus_pct"] / 100)
    return {
        "since": since,
        "until": now,
        "focus_ms": focus_ms,
        "points": points,
        "xp": int(xp + carry.get("xp", 0.0)),
        "resources": resources,
        "full": full,
    }


def collect(now: float | None = None) -> dict:
    """Bank the harvest. Returns what was applied (resources, xp, credits, level_up)."""
    from ..rewards import engine

    now = now or time.time()
    village = get_village()
    crop = harvest(now, village)
    rates = production_rates(village)
    carry = village.get("carry", {})
    new_carry = {}
    for res, rate in rates.items():
        made = crop["points"] * rate + carry.get(res, 0.0)
        if res not in crop["full"]:
            new_carry[res] = made - int(made)  # fractions roll over to the next harvest
    for res, amount in crop["resources"].items():
        village["inventory"][res] += amount
    xp_made = crop["points"] * economy.XP_PER_POINT * (1 + get_bonuses(village)["xp_bonus_pct"] / 100)
    new_carry["xp"] = xp_made + carry.get("xp", 0.0) - crop["xp"]
    village["carry"] = new_carry
    village["collected_until"] = now
    save_village(village)
    applied = dict(crop["resources"])
    applied.update(engine.add_xp(crop["xp"]))
    db.commit()
    applied["points"] = crop["points"]
    applied["focus_ms"] = crop["focus_ms"]
    return applied


# ---------------------------------------------------------------------------
# Daily chest
# ---------------------------------------------------------------------------


def chest_state(day: str | None = None) -> str:
    """'ready', 'claimed' or 'locked' for *day* (today by default)."""
    day = day or date.today().isoformat()
    return get_village().get("chests", {}).get(day, "locked")


def unlock_chest(day: str) -> None:
    village = get_village()
    chests = village.setdefault("chests", {})
    if chests.get(day) is None:
        chests[day] = "ready"
        # Keep a short history only.
        for old in sorted(chests)[:-14]:
            chests.pop(old, None)
        save_village(village)
        db.commit()


def open_chest(day: str | None = None) -> dict | None:
    """Open a ready chest. Returns what it held, or None."""
    from ..rewards import engine

    day = day or date.today().isoformat()
    village = get_village()
    if village.get("chests", {}).get(day) != "ready":
        return None
    reward = economy.chest_for(engine.get_profile()["streak"])
    village["chests"][day] = "claimed"
    save_village(village)
    applied = engine.apply_reward(reward)
    db.commit()
    return applied


def ready_chests() -> list[str]:
    return sorted(day for day, status in get_village().get("chests", {}).items() if status == "ready")


# ---------------------------------------------------------------------------
# Market
# ---------------------------------------------------------------------------


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
