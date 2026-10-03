from apptrackr.data import db, queries
from apptrackr.game import economy, state
from apptrackr.rewards import engine, rules


def _use(app_id, minutes):
    db.execute(
        "INSERT INTO daily_rollup (day, app_id, focused_ms) VALUES (?, ?, ?) "
        "ON CONFLICT(day, app_id) DO UPDATE SET focused_ms = excluded.focused_ms",
        (queries.today_str(), app_id, minutes * 60_000),
    )
    db.commit()


def test_rules_are_created_disabled_and_can_be_enabled():
    app_id = queries.get_or_create_app("code.exe")
    rules.ensure_app_rules(app_id)
    assert not rules.app_rewards_enabled(app_id)
    rules.enable_app_rewards(app_id)
    assert rules.app_rewards_enabled(app_id)
    assert rules.earning_app_ids() == {app_id}


def test_repeatable_milestones_grant_once_per_crossing():
    app_id = queries.get_or_create_app("code.exe")
    rules.enable_app_rewards(app_id)
    _use(app_id, 65)
    first = engine.evaluate()
    assert len(first) == 3  # 2x 30m + 1x 60m
    assert engine.evaluate() == []
    _use(app_id, 95)
    assert len(engine.evaluate()) == 1


def test_disabled_rewards_grant_nothing():
    app_id = queries.get_or_create_app("code.exe")
    rules.enable_app_rewards(app_id)
    _use(app_id, 65)
    db.set_setting("rewards_enabled", False)
    assert engine.evaluate() == []


def test_claim_applies_bonuses_caps_and_levels():
    app_id = queries.get_or_create_app("code.exe")
    rules.enable_app_rewards(app_id)
    village = state.get_village()
    village["buildings"]["workshop"] = {"level": 2}  # +10% xp
    village["inventory"]["wood"] = economy.BASE_RESOURCE_CAP - 2
    state.save_village(village)
    db.execute("UPDATE player_profile SET xp = 95 WHERE profile_id = 1")
    db.commit()
    _use(app_id, 30)
    engine.evaluate()
    applied = engine.claim_many()
    assert applied["xp"] == 11
    assert applied["wood"] == 2  # capped
    assert applied["level_up"] == 2
    assert applied["credits"] == economy.CREDITS_PER_LEVEL * 2
    profile = engine.get_profile()
    assert profile["level"] == 2 and profile["xp"] == 106
    assert engine.unclaimed_count() == 0


def test_streak_grows_once_per_day_and_pays_tiers():
    from datetime import date, timedelta

    app_id = queries.get_or_create_app("code.exe")
    queries.set_favorite(app_id, True)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    db.execute("UPDATE player_profile SET streak_days = 2, last_streak_day = ? WHERE profile_id = 1", (yesterday,))
    db.commit()
    assert engine.update_streak() is None  # goal not met yet
    result = engine.update_streak(extra_ms=economy.STREAK_GOAL_MS)
    assert result["streak"] == 3
    assert result["reward"]["xp"] == economy.STREAK_REWARDS[3]["xp"]
    assert engine.update_streak(extra_ms=economy.STREAK_GOAL_MS) is None


def test_broken_streak_reads_as_zero():
    db.execute("UPDATE player_profile SET streak_days = 5, last_streak_day = '2000-01-01' WHERE profile_id = 1")
    assert engine.get_profile()["streak"] == 0


def test_building_and_market():
    ok, reason = state.can_build("workshop")
    assert not ok and reason.startswith("Need")
    village = state.get_village()
    village["inventory"].update({"wood": 20, "stone": 10})
    state.save_village(village)
    assert state.build_or_upgrade("workshop") == (True, "Workshop built")
    assert state.build_cost("workshop", 1) == {"wood": 40, "stone": 20}
    assert state.can_build("lab")[1] == "Unlocks at level 3"

    assert not state.buy("wood")[0]
    db.execute("UPDATE player_profile SET credits = 20 WHERE profile_id = 1")
    assert state.buy("wood") == (True, "Bought 10 wood")
    assert state.get_village()["inventory"]["wood"] == 10
    assert engine.get_profile()["credits"] == 15


def test_next_milestone_sums_coinciding_rewards():
    app_id = queries.get_or_create_app("code.exe")
    rules.enable_app_rewards(app_id)
    _use(app_id, 95)
    (item,) = engine.next_milestones()
    assert item["next"]["target_ms"] == 120 * 60_000
    assert item["next"]["reward"]["xp"] == 10 + 25 + 60
