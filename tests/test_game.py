"""Tests for the Neon Village building economy."""

from __future__ import annotations

import json

from apptrackr.data import db
from apptrackr.game import state, economy


def _set_level(level: int) -> None:
    db.execute("UPDATE player_profile SET level = ? WHERE profile_id = 1", (level,))
    db.commit()


def _set_inventory(**resources) -> None:
    village = state.get_village()
    village["inventory"].update(resources)
    db.execute(
        "UPDATE village_state SET state_json = ? WHERE profile_id = 1",
        (json.dumps(village),),
    )
    db.commit()


def test_can_build_requires_unlock_level():
    _set_inventory(stone=100, metal=100, blueprints=100)
    ok, reason = state.can_build("lab")  # needs level 3
    assert ok is False
    assert "level 3" in reason


def test_can_build_requires_resources():
    _set_level(1)
    _set_inventory(wood=0, stone=0)
    ok, reason = state.can_build("workshop")
    assert ok is False
    assert "Not enough" in reason


def test_build_deducts_resources_and_levels_building():
    _set_level(1)
    _set_inventory(wood=100, stone=100)
    ok, msg = state.build_or_upgrade("workshop")
    assert ok is True
    village = state.get_village()
    assert village["buildings"]["workshop"]["level"] == 1
    assert village["inventory"]["wood"] == 80  # 100 - 20
    assert village["inventory"]["stone"] == 90  # 100 - 10


def test_upgrade_cost_scales_with_level():
    _set_level(1)
    _set_inventory(wood=100, stone=100)
    state.build_or_upgrade("workshop")  # level 1: 20 wood / 10 stone
    state.build_or_upgrade("workshop")  # level 2 costs x2: 40 wood / 20 stone
    village = state.get_village()
    assert village["buildings"]["workshop"]["level"] == 2
    assert village["inventory"]["wood"] == 40  # 100 - 20 - 40
    assert village["inventory"]["stone"] == 70  # 100 - 10 - 20


def test_house_adds_villager():
    _set_level(2)
    _set_inventory(wood=100, food=100)
    state.build_or_upgrade("house")
    assert state.get_village()["villagers"] == 1


def test_cannot_exceed_max_level():
    _set_level(5)
    _set_inventory(stone=999, metal=999, blueprints=999)
    ok, _ = state.build_or_upgrade("monument")  # max_level 1
    assert ok is True
    ok, reason = state.can_build("monument")
    assert ok is False
    assert "max level" in reason.lower()


def test_bonuses_reflect_buildings():
    _set_level(1)
    _set_inventory(wood=999, stone=999)
    state.build_or_upgrade("workshop")
    bonuses = state.get_bonuses()
    assert bonuses["xp_bonus_pct"] == 5


def test_unknown_building():
    ok, reason = state.can_build("castle")
    assert ok is False
    assert reason == "Unknown building"


def test_xp_curve():
    assert economy.xp_for_level(1) == 100
    assert economy.xp_for_level(5) == 500
