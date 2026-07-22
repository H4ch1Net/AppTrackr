"""Tests for the reward rule engine, claiming, and streaks."""

from __future__ import annotations

import json

from apptrackr.data import db, queries
from apptrackr.rewards import engine, rules


def _add_rule(app_id, metric, threshold, reward, repeatable=False, enabled=True):
    cur = db.execute(
        "INSERT INTO reward_rules (app_id, metric, threshold, reward_json, repeatable, enabled) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (app_id, metric, threshold, json.dumps(reward), int(repeatable), int(enabled)),
    )
    db.commit()
    return cur.lastrowid


def test_non_repeatable_grants_once():
    app_id = queries.get_or_create_app("foo.exe")
    day = queries.today_str()
    queries.add_focused_time(day, app_id, 60 * 60 * 1000)
    _add_rule(app_id, "focused_ms", 30 * 60 * 1000, {"xp": 10}, repeatable=False)

    assert len(engine.evaluate(day)) == 1
    assert engine.evaluate(day) == []  # no double grant


def test_repeatable_grants_per_threshold_crossing():
    app_id = queries.get_or_create_app("foo.exe")
    day = queries.today_str()
    queries.add_focused_time(day, app_id, 95 * 60 * 1000)  # 95 min
    _add_rule(app_id, "focused_ms", 30 * 60 * 1000, {"xp": 10}, repeatable=True)

    granted = engine.evaluate(day)
    assert len(granted) == 3  # 30, 60, 90 min crossed

    queries.add_focused_time(day, app_id, 30 * 60 * 1000)  # now 125 min
    assert len(engine.evaluate(day)) == 1  # only the 120-min crossing is new


def test_disabled_rules_do_not_fire():
    app_id = queries.get_or_create_app("foo.exe")
    day = queries.today_str()
    queries.add_focused_time(day, app_id, 60 * 60 * 1000)
    _add_rule(app_id, "focused_ms", 30 * 60 * 1000, {"xp": 10}, enabled=False)
    assert engine.evaluate(day) == []


def test_rewards_globally_disabled():
    app_id = queries.get_or_create_app("foo.exe")
    day = queries.today_str()
    queries.add_focused_time(day, app_id, 60 * 60 * 1000)
    _add_rule(app_id, "focused_ms", 30 * 60 * 1000, {"xp": 10})
    db.set_setting("rewards_enabled", "0")
    assert engine.evaluate(day) == []


def test_claim_applies_xp_credits_and_levels_up():
    app_id = queries.get_or_create_app("foo.exe")
    day = queries.today_str()
    queries.add_focused_time(day, app_id, 60 * 60 * 1000)
    _add_rule(app_id, "focused_ms", 30 * 60 * 1000, {"xp": 250, "credits": 5, "wood": 3})
    engine.evaluate(day)

    unclaimed = engine.unclaimed_rewards()
    assert len(unclaimed) == 1
    engine.claim_reward(unclaimed[0]["event_id"])

    profile = engine.get_profile()
    assert profile["xp"] == 250
    assert profile["credits"] == 5
    assert profile["level"] == 3  # 1 + 250 // 100

    village = json.loads(db.fetchone("SELECT state_json FROM village_state WHERE profile_id=1")["state_json"])
    assert village["inventory"]["wood"] == 3
    assert engine.unclaimed_rewards() == []


def test_claim_all():
    app_id = queries.get_or_create_app("foo.exe")
    day = queries.today_str()
    queries.add_focused_time(day, app_id, 95 * 60 * 1000)
    _add_rule(app_id, "focused_ms", 30 * 60 * 1000, {"xp": 10}, repeatable=True)
    engine.evaluate(day)
    results = engine.claim_all()
    assert len(results) == 3
    assert engine.get_profile()["xp"] == 30


class TestStreak:
    def test_streak_requires_favorite_time(self):
        app_id = queries.get_or_create_app("foo.exe")
        day = queries.today_str()
        queries.add_focused_time(day, app_id, 60 * 60 * 1000)  # not a favorite
        assert engine.update_streak() == 0

    def test_streak_increments_for_favorite(self):
        app_id = queries.get_or_create_app("foo.exe")
        queries.set_favorite(app_id, True)
        day = queries.today_str()
        queries.add_focused_time(day, app_id, 40 * 60 * 1000)
        assert engine.update_streak() == 1
        # Idempotent within the same day.
        assert engine.update_streak() == 1


class TestDefaultRules:
    def test_ensure_app_rules_seeds_once(self):
        app_id = queries.get_or_create_app("foo.exe")
        rules.ensure_app_rules(app_id)
        first = len(rules.list_rules(app_id))
        assert first == len(rules.DEFAULT_RULES)
        rules.ensure_app_rules(app_id)
        assert len(rules.list_rules(app_id)) == first

    def test_enable_disable_app_rewards(self):
        app_id = queries.get_or_create_app("foo.exe")
        rules.ensure_app_rules(app_id)
        rules.enable_app_rewards(app_id, True)
        assert rules.app_rewards_enabled(app_id) is True
        rules.enable_app_rewards(app_id, False)
        assert rules.app_rewards_enabled(app_id) is False
