import json
import time
from datetime import date, timedelta

import pytest

from apptrackr.data import db, queries
from apptrackr.game import economy, focus, state
from apptrackr.rewards import engine, rules

MIN = 60.0


def _session(app_id, start, minutes):
    sid = queries.start_session(app_id, start)
    queries.update_session_end(sid, start + minutes * MIN)
    queries.add_focus_span(app_id, start, start + minutes * MIN)
    db.commit()


def _focus_app(exe="code.exe"):
    app_id = queries.get_or_create_app(exe)
    rules.enable_app_rewards(app_id)
    return app_id


def _set_collected(ts):
    village = state.get_village()
    village["collected_until"] = ts
    state.save_village(village)
    db.commit()


def test_rules_are_created_disabled_and_can_be_enabled():
    app_id = queries.get_or_create_app("code.exe")
    rules.ensure_app_rules(app_id)
    assert not rules.app_rewards_enabled(app_id)
    rules.enable_app_rewards(app_id)
    assert rules.app_rewards_enabled(app_id)
    assert rules.earning_app_ids() == focus.focus_app_ids() == {app_id}


def test_flow_tiers_multiply_later_minutes():
    # 30 straight minutes: 10 at x1, 15 at x1.5, 5 at x2
    fp, ms = focus.points([(0, 30 * MIN)], 180, 0, 30 * MIN)
    assert fp == pytest.approx(10 + 22.5 + 10)
    assert ms == 30 * 60_000
    assert focus.multiplier_at(0) == 1.0
    assert focus.multiplier_at(80) == 3.0


def test_short_breaks_keep_a_run_and_long_ones_end_it():
    spans = [(0, 20 * MIN), (22 * MIN, 30 * MIN)]  # 2 minutes away
    assert len(focus.runs(spans, 180)) == 1
    spans = [(0, 20 * MIN), (30 * MIN, 40 * MIN)]  # 10 minutes away
    assert len(focus.runs(spans, 180)) == 2
    assert len(focus.runs(spans, focus.grace_sec(tavern_level=10))) == 1
    # The second run starts over at x1.
    fp, _ = focus.points(spans, 180, 0, 40 * MIN)
    assert fp == pytest.approx(10 + 10 * 1.5 + 10)


def test_points_inside_a_window_keep_the_runs_tier():
    fp, ms = focus.points([(0, 60 * MIN)], 180, 50 * MIN, 60 * MIN)
    assert fp == pytest.approx(10 * 2.5)
    assert ms == 10 * 60_000


def test_harvest_turns_focus_into_xp_and_resources_with_carry():
    app_id = _focus_app()
    other = queries.get_or_create_app("game.exe")
    now = time.time()
    _set_collected(now - 3600)
    _session(app_id, now - 40 * MIN, 30)
    _session(other, now - 9 * MIN, 8)  # not a focus app: earns nothing
    crop = state.harvest(now)
    assert crop["points"] == pytest.approx(42.5)
    assert crop["focus_ms"] == 30 * 60_000
    assert crop["resources"] == {"wood": 10, "stone": 6, "food": 8}
    assert crop["xp"] == 10
    applied = state.collect(now)
    assert applied["wood"] == 10 and applied["xp"] == 10
    village = state.get_village()
    assert village["inventory"]["wood"] == 10
    assert village["carry"]["wood"] == pytest.approx(0.625)
    assert engine.get_profile()["xp"] == 10
    assert state.harvest(now)["points"] == 0  # nothing new since collecting


def test_harvest_respects_storage():
    app_id = _focus_app()
    now = time.time()
    _set_collected(now - 7200)
    village = state.get_village()
    village["inventory"]["wood"] = economy.resource_cap(0) - 3
    state.save_village(village)
    db.commit()
    _session(app_id, now - 100 * MIN, 90)
    crop = state.harvest(now)
    assert crop["resources"]["wood"] == 3
    assert "wood" in crop["full"]
    state.collect(now)
    assert state.get_village()["inventory"]["wood"] == economy.resource_cap(0)


def test_buildings_raise_production():
    village = state.get_village()
    base = state.production_rates(village)
    assert set(base) == {"wood", "stone", "food"}
    village["buildings"] = {"lumberyard": {"level": 3}, "mine": {"level": 1}}
    village["villagers"] = 5
    rates = state.production_rates(village)
    assert rates["wood"] == pytest.approx(0.25 * 4 * 1.2)
    assert rates["metal"] == pytest.approx(0.08 * 1.2)


def test_live_flow_includes_the_session_in_progress():
    app_id = _focus_app()
    now = time.time()
    flow = focus.current(now, live_app_id=app_id, live_since=now - 26 * MIN)
    assert flow.active
    assert flow.multiplier == 2.0 and flow.tier == "In the zone"
    assert flow.next_tier == "Deep work"
    assert flow.next_in_ms == pytest.approx(19 * 60_000, abs=1000)
    idle = focus.current(now, live_app_id=None)
    assert not idle.active and idle.run_ms == 0 and idle.multiplier == 1.0


def test_goal_grows_streak_once_a_day_and_unlocks_the_chest():
    _focus_app()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    db.execute("UPDATE player_profile SET streak_days = 6, last_streak_day = ? WHERE profile_id = 1", (yesterday,))
    db.set_setting("focus_goal_min", 60)
    assert engine.goal_ms() == 60 * 60_000
    assert engine.update_streak(extra_ms=59 * 60_000) is None
    assert state.chest_state() == "locked"
    assert engine.update_streak(extra_ms=60 * 60_000) == {"streak": 7}
    assert engine.update_streak(extra_ms=60 * 60_000) is None
    assert state.ready_chests() == [date.today().isoformat()]
    applied = state.open_chest()
    week = economy.chest_for(7)
    assert applied["blueprints"] == week["blueprints"] == 2
    assert applied["credits"] == week["credits"]
    assert state.chest_state() == "claimed"
    assert state.open_chest() is None


def test_broken_streak_reads_as_zero():
    db.execute("UPDATE player_profile SET streak_days = 5, last_streak_day = '2000-01-01' WHERE profile_id = 1")
    assert engine.get_profile()["streak"] == 0


def test_rewards_from_1x_can_still_be_claimed():
    app_id = _focus_app()
    rule = db.fetchone("SELECT rule_id FROM reward_rules WHERE app_id = ?", (app_id,))["rule_id"]
    village = state.get_village()
    village["buildings"]["workshop"] = {"level": 2}
    state.save_village(village)
    db.execute("UPDATE player_profile SET xp = 95 WHERE profile_id = 1")
    db.execute(
        "INSERT INTO reward_events (ts, app_id, rule_id, day, granted_json) VALUES (?, ?, ?, ?, ?)",
        (time.time(), app_id, rule, queries.today_str(), json.dumps({"xp": 10, "wood": 4})),
    )
    db.commit()
    assert engine.unclaimed_count() == 1
    applied = engine.claim_many()
    assert applied["xp"] == 10 and applied["wood"] == 4
    assert applied["level_up"] == 2
    assert applied["credits"] == economy.CREDITS_PER_LEVEL * 2
    assert engine.unclaimed_count() == 0


def test_building_unlocks_costs_and_market():
    ok, reason = state.can_build("lumberyard")
    assert not ok and reason.startswith("Need")
    village = state.get_village()
    village["inventory"].update({"wood": 15})
    state.save_village(village)
    assert state.build_or_upgrade("lumberyard") == (True, "Lumberyard built")
    assert state.build_cost("lumberyard", 1) == {"wood": 23}
    assert state.can_build("mine")[1] == "Unlocks at level 3"
    assert state.can_build("monument")[1] == "Unlocks at level 10"

    db.execute("UPDATE player_profile SET level = 2 WHERE profile_id = 1")
    village = state.get_village()
    village["inventory"].update({"wood": 400, "food": 400})
    state.save_village(village)
    assert state.build_or_upgrade("house")[0]
    assert state.get_village()["villagers"] == 1

    db.execute("UPDATE player_profile SET credits = 4 WHERE profile_id = 1")
    assert not state.buy("stone")[0]
    db.execute("UPDATE player_profile SET credits = 20 WHERE profile_id = 1")
    amount, price = economy.MARKET["stone"]
    assert state.buy("stone") == (True, f"Bought {amount} stone")
    assert engine.get_profile()["credits"] == 20 - price


def test_storage_gates_expensive_buildings():
    db.execute("UPDATE player_profile SET level = 10 WHERE profile_id = 1")
    village = state.get_village()
    village["inventory"].update({"stone": 200, "metal": 200, "blueprints": 5})
    state.save_village(village)
    assert state.can_build("monument") == (False, "Needs a bigger storage")


def test_attention_counts_chests_harvests_and_old_rewards():
    app_id = _focus_app()
    assert engine.attention_count() == 0
    now = time.time()
    _set_collected(now - 7200)
    _session(app_id, now - 70 * MIN, 60)
    assert engine.attention_count() == 1
    state.unlock_chest(date.today().isoformat())
    assert engine.attention_count() == 2
    db.set_setting("rewards_enabled", False)
    assert engine.attention_count() == 0


def test_favorites_become_focus_apps_once_after_updating():
    fav = queries.get_or_create_app("figma.exe")
    queries.set_favorite(fav, True)
    assert rules.adopt_favorites_once() == 1
    assert focus.focus_app_ids() == {fav}
    rules.enable_app_rewards(fav, False)
    assert rules.adopt_favorites_once() == 0  # only once: removing it later sticks


def test_chosen_focus_apps_are_not_overridden_by_favorites():
    chosen = _focus_app()
    queries.set_favorite(queries.get_or_create_app("game.exe"), True)
    assert rules.adopt_favorites_once() == 0
    assert focus.focus_app_ids() == {chosen}
