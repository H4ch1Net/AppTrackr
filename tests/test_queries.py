"""Tests for name normalization, filtering, and the analytics query layer."""

from __future__ import annotations

import pytest

from apptrackr.data import queries


class TestNormalizeAppName:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("code.exe", "VS Code"),
            ("chrome.exe", "Google Chrome"),
            ("notepad++.exe", "Notepad++"),
            ("my_cool-app.exe", "My Cool App"),
            ("myCoolApp.exe", "My Cool App"),
            ("", "Unknown App"),
            ("   ", "Unknown App"),
        ],
    )
    def test_normalize(self, raw, expected):
        assert queries.normalize_app_name(raw) == expected

    def test_windows_path_is_stripped(self):
        assert queries.normalize_app_name(r"C:\Program Files\Foo\bar.exe") == "Bar"

    def test_posix_path_is_stripped(self):
        assert queries.normalize_app_name("/usr/bin/bar.exe") == "Bar"


class TestHiddenProcess:
    @pytest.mark.parametrize(
        "name",
        ["dwm.exe", "RuntimeBroker.exe", "chrome_helper.exe", "app_updater.exe", ""],
    )
    def test_hidden(self, name):
        assert queries.is_dashboard_hidden_process(name) is True

    @pytest.mark.parametrize("name", ["chrome.exe", "code.exe", "discord.exe"])
    def test_visible(self, name):
        assert queries.is_dashboard_hidden_process(name) is False


class TestAppCrud:
    def test_get_or_create_is_idempotent(self):
        a = queries.get_or_create_app("foo.exe")
        b = queries.get_or_create_app("foo.exe")
        assert a == b
        assert len(queries.list_apps()) == 1

    def test_display_name_backfilled(self):
        app_id = queries.get_or_create_app("code.exe")
        assert queries.get_app(app_id)["display_name"] == "VS Code"

    def test_icon_backfilled_but_not_overwritten(self):
        app_id = queries.get_or_create_app("foo.exe", icon_path="/a")
        queries.get_or_create_app("foo.exe", icon_path="/b")
        assert queries.get_app(app_id)["icon_path"] == "/a"

    def test_favorite_and_category(self):
        app_id = queries.get_or_create_app("foo.exe")
        queries.set_favorite(app_id, True)
        queries.set_category(app_id, "Work")
        app = queries.get_app(app_id)
        assert app["is_favorite"] == 1
        assert app["category"] == "Work"


class TestRollupAggregation:
    def test_today_total_and_top_apps(self):
        a = queries.get_or_create_app("a.exe")
        b = queries.get_or_create_app("b.exe")
        day = queries.today_str()
        queries.add_focused_time(day, a, 1000)
        queries.add_focused_time(day, a, 500)  # accumulates
        queries.add_focused_time(day, b, 3000)

        assert queries.today_total_ms() == 4500
        top = queries.top_apps_today()
        assert [r["exe_name"] for r in top] == ["b.exe", "a.exe"]
        assert top[1]["focused_ms"] == 1500

    def test_increment_opens_and_clicks(self):
        a = queries.get_or_create_app("a.exe")
        day = queries.today_str()
        queries.increment_opens(day, a)
        queries.increment_opens(day, a)
        queries.increment_clicks(day, a, 5)
        row = queries.top_apps_today()[0]
        assert row["opens_count"] == 2
        assert row["clicks_count"] == 5

    def test_dashboard_filters_system_processes(self):
        good = queries.get_or_create_app("chrome.exe")
        noise = queries.get_or_create_app("dwm.exe")
        day = queries.today_str()
        queries.add_focused_time(day, good, 1000)
        queries.add_focused_time(day, noise, 9999)
        names = [r["exe_name"] for r in queries.dashboard_top_apps_today()]
        assert "chrome.exe" in names
        assert "dwm.exe" not in names
