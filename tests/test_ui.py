"""Offscreen smoke tests: every page builds, refreshes and survives a theme switch."""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from apptrackr.core.platform import DemoPlatform, NullPlatform  # noqa: E402
from apptrackr.core.tracker import Tracker  # noqa: E402
from apptrackr.data import db, demo, queries  # noqa: E402
from apptrackr.ui import fmt  # noqa: E402


@pytest.fixture
def qapp():
    from apptrackr.ui.main import prepare_app

    app = QApplication.instance() or QApplication([])
    prepare_app(app)
    return app


@pytest.fixture
def window(qapp):
    from apptrackr.ui.main import MainWindow

    demo.seed(days=20)
    tracker = Tracker(DemoPlatform())
    tracker.reload_settings()
    tracker.tick()
    win = MainWindow(tracker, None, demo=True)
    win.resize(1200, 780)
    win.show()
    qapp.processEvents()
    yield win
    tracker.stop()
    win._quitting = True
    win.close()
    win.deleteLater()
    qapp.processEvents()


def test_every_page_renders(window, qapp):
    for page in ("dashboard", "calendar", "apps", "rewards", "village", "settings"):
        window.show_page(page)
        window._tick()
        qapp.processEvents()
        assert window._stack.currentWidget() is window._views[page]
        assert not window.grab().isNull()


def test_pages_fit_minimum_window(window, qapp):
    """At the smallest window size, two-column rows stack instead of clipping on the right."""
    window.resize(window.minimumSize())
    window.open_app(queries.find_app_id("code.exe"))
    for page in ("dashboard", "calendar", "apps", "rewards", "village", "settings", "app"):
        if page != "app":
            window.show_page(page)
        view = window._views[page]
        for _ in range(3):  # layout requests settle over a few event-loop passes
            qapp.processEvents()
        assert view.widget().minimumSizeHint().width() <= view.viewport().width(), page


def test_app_detail_and_back_navigation(window, qapp):
    window.show_page("calendar")
    app_id = queries.find_app_id("code.exe")
    window.open_app(app_id)
    qapp.processEvents()
    assert window._views["app"].title.text() == "VS Code"
    window.go_back()
    assert window._current == "calendar"


def test_theme_switch_and_rewards_toggle(window, qapp):
    db.set_setting("ui_mode", "light")
    window.apply_theme()
    db.set_setting("ui_theme", "Purple")
    window.apply_theme()
    qapp.processEvents()
    db.set_setting("rewards_enabled", False)
    window.apply_rewards_visibility()
    assert not window._nav_buttons["rewards"].isVisibleTo(window)
    window.show_page("rewards")
    db.set_setting("rewards_enabled", True)
    window.apply_rewards_visibility()


def test_exclude_with_undo(window, qapp):
    app_id = queries.find_app_id("chrome.exe")
    window.show_page("apps")
    window.exclude_app(app_id)
    assert queries.get_app(app_id)["is_hidden"] == 1
    window.toast._run_action()
    assert queries.get_app(app_id)["is_hidden"] == 0


def test_focus_page_chest_and_village_harvest(window, qapp):
    from datetime import date

    from apptrackr.game import state as game_state
    from apptrackr.rewards import engine

    view = window._views["rewards"]
    window.show_page("rewards")
    assert view.flow_card.isVisible() and not view.chest_btn.isVisible()
    game_state.unlock_chest(date.today().isoformat())
    view.refresh()
    assert view.chest_btn.isVisible()
    credits = engine.get_profile()["credits"]
    view._open_chest()
    assert engine.get_profile()["credits"] > credits
    assert game_state.ready_chests() == []
    view._claim_all()
    assert engine.unclaimed_count() == 0

    village = window._views["village"]
    window.show_page("village")
    before = game_state.get_village()["inventory"]
    crop = game_state.harvest()
    assert crop["points"] > 0  # the demo village has focus time waiting
    village._collect()
    after = game_state.get_village()["inventory"]
    assert all(after[r] == before[r] + n for r, n in crop["resources"].items())
    assert game_state.harvest()["points"] < 1


def test_unsupported_platform_shows_state(qapp):
    from apptrackr.ui.main import MainWindow

    tracker = Tracker(NullPlatform())
    win = MainWindow(tracker, None)
    win.show_page("dashboard")
    win._tick()
    assert win._views["dashboard"].now.name.text() == "Tracking unavailable"
    assert "Windows" in win._status.accessibleName()
    win._quitting = True
    win.close()


def test_formatters():
    assert fmt.duration(59_000) == "59s"
    assert fmt.duration(65_000) == "1m 5s"
    assert fmt.duration(65_000, short=True) == "1m"
    assert fmt.duration(3_600_000 * 2 + 60_000 * 5) == "2h 5m"
    assert fmt.clock(3_725_000) == "1:02:05"
    assert fmt.reward({"wood": 5, "xp": 10}) == "+10 XP  +5 wood"
    assert fmt.percent_change(150, 100) == "+50%"
    assert fmt.percent_change(1, 0) is None


def test_tick_slider_commits_final_values(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from apptrackr.ui.widgets.controls import TickSlider

    slider = TickSlider([("Off", 0), ("15m", 15), ("30m", 30)])
    slider.resize(300, 44)
    slider.show()
    got = []
    slider.committed.connect(got.append)
    slider.set_stop_value(15)
    assert slider.stop_value() == 15 and got == []  # programmatic selection is silent
    slider.setFocus()
    QTest.keyClick(slider, Qt.Key.Key_Right)
    assert got == [30]
    slider.setSliderDown(True)
    slider.setValue(0)
    assert got == [30]  # nothing while dragging
    slider.setSliderDown(False)
    assert got == [30, 0]
    slider.set_stops([("Off", 0), ("20m", 20), ("30m", 30)])
    assert slider.index_of(20) == 1


def test_notification_kinds(window, qapp):
    settings = window._views["settings"]
    window.show_page("settings")
    qapp.processEvents()
    box = settings.notify_boxes["streaks"]
    assert box.isChecked()
    box.click()
    assert db.get_bool("notify_streaks", True) is False
    settings.notifications.click()  # master switch off disables the kinds
    assert not box.isEnabled()
    settings.notifications.click()
    assert box.isEnabled()

    class FakeTray:
        def __init__(self):
            self.shown = []

        def showMessage(self, title, *_args):  # noqa: N802 - Qt naming
            self.shown.append(title)

        def __getattr__(self, _name):
            return lambda *a, **k: None

    tray = FakeTray()
    window._tray = tray
    window.hide()
    window.notify("Streak", "x", kind="streaks")
    window.notify("Daily limit reached", "y", kind="limits")
    window._tray = None
    assert tray.shown == ["Daily limit reached"]


def test_palette_tiles_switch_theme(window, qapp):
    from apptrackr.ui import theme

    settings = window._views["settings"]
    window.show_page("settings")
    qapp.processEvents()
    settings.tiles["Midnight"].click()
    assert theme.current().name == "Midnight" and db.get_setting("ui_dark_palette") == "Midnight"
    settings.tiles["Sage"].click()
    assert theme.current().name == "Sage" and db.get_setting("ui_mode") == "light"
    assert settings.tiles["Midnight"].isChecked() and settings.tiles["Sage"].isChecked()
    assert settings.tiles["Sage"].active and not settings.tiles["Midnight"].active


def test_other_terms_card(window, qapp):
    dash = window._views["dashboard"]
    window.show_page("dashboard")
    window._tick()
    qapp.processEvents()
    card = dash.other_terms
    shown = [t for t in card.tiles if t.key]
    assert shown, "comparisons should render for demo data"
    keys = [t.key for t in card.tiles]
    card._shuffle()
    qapp.processEvents()
    assert [t.key for t in card.tiles] != keys or not card.shuffle.isEnabled()
    card.period._group.button(2).click()
    qapp.processEvents()
    assert card.current_period == "all" and db.get_setting("perspective_period") == "all"


def test_floating_timer_follows_the_app_in_front(window, qapp, monkeypatch):
    from apptrackr.game import focus
    from apptrackr.ui import motion

    motion.force(False)  # fades finish at once
    overlay = window._overlay
    monkeypatch.setattr(window, "_app_in_front", lambda: False)
    window._update_overlay()
    qapp.processEvents()
    assert overlay.isVisible()
    snap = window._tracker.snapshot()
    assert overlay._name == queries.get_app(snap.app_id)["name"]
    assert overlay._focus == (snap.app_id in focus.focus_app_ids())
    assert not overlay.grab().isNull()

    monkeypatch.setattr(window, "_app_in_front", lambda: True)  # AppTrackr itself is in front
    window._update_overlay()
    qapp.processEvents()
    assert not overlay.isVisible()

    monkeypatch.setattr(window, "_app_in_front", lambda: False)
    monkeypatch.setattr(window._tracker, "foreground_fullscreen", lambda: True)
    window._update_overlay()
    assert not overlay.isVisible()
    monkeypatch.setattr(window._tracker, "foreground_fullscreen", lambda: False)

    window.set_overlay_enabled(False)
    assert not overlay.isVisible() and not db.get_bool("overlay_enabled", True)
    window.set_overlay_enabled(True)
    assert overlay.isVisible()

    overlay.move(120, 140)
    overlay.save_position()
    assert db.get_setting("overlay_pos") == "120,140"
    overlay.hide_requested.emit()
    assert not overlay.isVisible() and not window._overlay_enabled
