"""Tests for the zero-setup daily-goals loop, building bonuses, and streaks."""

from __future__ import annotations

import json

from apptrackr.data import db, queries
from apptrackr.game import state as game_state
from apptrackr.rewards import engine, goals


_MIN = 60 * 1000
_HOUR = 60 * _MIN


def _add_focus(minutes: int, app="foo.exe"):
    app_id = queries.get_or_create_app(app)
    queries.add_focused_time(queries.today_str(), app_id, minutes * _MIN)
    return app_id


def _inventory():
    row = db.fetchone("SELECT state_json FROM village_state WHERE profile_id = 1")
    return json.loads(row["state_json"])["inventory"]


class TestDailyGoals:
    def test_goals_fire_out_of_the_box(self):
        """No per-app setup: usage alone grants XP and resources."""
        _add_focus(16)  # crosses the 15-minute goal
        granted = goals.evaluate_daily_goals()
        keys = [g["key"] for g in granted]
        assert "focus_15m" in keys
        profile = engine.get_profile()
        assert profile["xp"] == 10
        assert _inventory()["wood"] == 5

    def test_goals_are_cumulative_across_apps(self):
        _add_focus(20, "a.exe")
        _add_focus(20, "b.exe")  # 40 min total -> 15m + 30m goals
        granted = {g["key"] for g in goals.evaluate_daily_goals()}
        assert "focus_15m" in granted
        assert "focus_30m" in granted
        assert "focus_1h" not in granted

    def test_goals_not_double_granted(self):
        _add_focus(70)
        first = goals.evaluate_daily_goals()
        assert first  # several goals
        assert goals.evaluate_daily_goals() == []  # idempotent same day

    def test_progress_then_more_goals(self):
        _add_focus(16)
        goals.evaluate_daily_goals()
        _add_focus(50)  # now 66 min total
        keys = {g["key"] for g in goals.evaluate_daily_goals()}
        assert keys == {"focus_30m", "focus_1h"}

    def test_disabled_globally(self):
        _add_focus(60)
        db.set_setting("rewards_enabled", "0")
        assert goals.evaluate_daily_goals() == []

    def test_opens_goal(self):
        app_id = queries.get_or_create_app("foo.exe")
        day = queries.today_str()
        for _ in range(15):
            queries.increment_opens(day, app_id)
        keys = {g["key"] for g in goals.evaluate_daily_goals()}
        assert "opens_15" in keys

    def test_daily_summary_reports_next_goal(self):
        _add_focus(16)
        summary = goals.daily_summary()
        assert summary["totals"]["focused_ms"] == 16 * _MIN
        done = [g for g in summary["goals"] if g["done"]]
        assert any(g["key"] == "focus_15m" for g in done)
        assert summary["next_goal"]["key"] == "focus_30m"


class TestBuildingBonuses:
    def _build_workshop(self):
        db.execute("UPDATE player_profile SET level = 5 WHERE profile_id = 1")
        village = game_state.get_village()
        village["inventory"].update({"wood": 999, "stone": 999})
        db.execute("UPDATE village_state SET state_json = ? WHERE profile_id = 1", (json.dumps(village),))
        db.commit()
        game_state.build_or_upgrade("workshop")  # level 1 -> +5% xp

    def test_workshop_boosts_xp(self):
        self._build_workshop()
        applied = engine.apply_reward({"xp": 100})
        assert applied["xp"] == 105

    def test_storage_cap_clamps_resources(self):
        # Without storage, resources clamp at the base cap.
        applied = engine.apply_reward({"wood": engine.BASE_RESOURCE_CAP + 500})
        assert _inventory()["wood"] == engine.BASE_RESOURCE_CAP

    def test_storage_raises_cap(self):
        db.execute("UPDATE player_profile SET level = 5 WHERE profile_id = 1")
        village = game_state.get_village()
        village["inventory"].update({"wood": 999, "stone": 999})
        db.execute("UPDATE village_state SET state_json = ? WHERE profile_id = 1", (json.dumps(village),))
        db.commit()
        game_state.build_or_upgrade("storage")  # +50 cap
        bonuses = game_state.get_bonuses()
        assert bonuses["resource_cap_bonus"] == 50


class TestVillagerIncome:
    def test_income_scales_with_villagers(self):
        # Two houses -> 2 villagers -> daily income.
        db.execute("UPDATE player_profile SET level = 5 WHERE profile_id = 1")
        village = game_state.get_village()
        village["villagers"] = 2
        village["inventory"] = {"wood": 0, "stone": 0, "metal": 0, "food": 0, "blueprints": 0}
        db.execute("UPDATE village_state SET state_json = ? WHERE profile_id = 1", (json.dumps(village),))
        db.commit()

        granted = goals.evaluate_daily_goals()
        income = [g for g in granted if g["key"] == "villager_income"]
        assert income
        inv = _inventory()
        assert inv["wood"] == 2 * goals.VILLAGER_INCOME["wood"]
        assert inv["food"] == 2 * goals.VILLAGER_INCOME["food"]

    def test_income_paid_once_per_day(self):
        village = game_state.get_village()
        village["villagers"] = 1
        db.execute("UPDATE village_state SET state_json = ? WHERE profile_id = 1", (json.dumps(village),))
        db.commit()
        goals.evaluate_daily_goals()
        wood_after_first = _inventory()["wood"]
        goals.evaluate_daily_goals()
        assert _inventory()["wood"] == wood_after_first

    def test_no_villagers_no_income(self):
        assert goals._grant_villager_income(queries.today_str()) == []


class TestStreakRewards:
    def test_streak_tiers_granted_once(self):
        db.execute("UPDATE player_profile SET streak_days = 7 WHERE profile_id = 1")
        db.commit()
        granted = engine.grant_streak_rewards()
        tiers = sorted(g["tier"] for g in granted)
        assert tiers == [3, 7]  # both tiers up to current streak
        assert engine.grant_streak_rewards() == []  # not re-granted

    def test_higher_streak_unlocks_more(self):
        db.execute("UPDATE player_profile SET streak_days = 3 WHERE profile_id = 1")
        db.commit()
        assert [g["tier"] for g in engine.grant_streak_rewards()] == [3]
        db.execute("UPDATE player_profile SET streak_days = 14 WHERE profile_id = 1")
        db.commit()
        assert sorted(g["tier"] for g in engine.grant_streak_rewards()) == [7, 14]

    def test_streak_disabled_globally(self):
        db.execute("UPDATE player_profile SET streak_days = 30 WHERE profile_id = 1")
        db.set_setting("rewards_enabled", "0")
        db.commit()
        assert engine.grant_streak_rewards() == []


class TestAutoClaim:
    def _seed_rule(self, app_id):
        db.execute(
            "INSERT INTO reward_rules (app_id, metric, threshold, reward_json, repeatable, enabled) "
            "VALUES (?, 'focused_ms', ?, ?, 0, 1)",
            (app_id, 30 * _MIN, json.dumps({"xp": 10})),
        )
        db.commit()

    def test_auto_claim_on_by_default(self):
        app_id = _add_focus(60)
        self._seed_rule(app_id)
        engine.evaluate()
        engine.auto_claim_if_enabled()
        assert engine.unclaimed_rewards() == []
        assert engine.get_profile()["xp"] == 10

    def test_auto_claim_off_leaves_pending(self):
        app_id = _add_focus(60)
        self._seed_rule(app_id)
        db.set_setting("auto_claim_rewards", "0")
        engine.evaluate()
        assert engine.auto_claim_if_enabled() == []
        assert len(engine.unclaimed_rewards()) == 1
