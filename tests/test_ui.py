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


def test_claim_from_rewards_page(window, qapp):
    view = window._views["rewards"]
    window.show_page("rewards")
    view._claim_all()
    from apptrackr.rewards import engine

    assert engine.unclaimed_count() == 0


def test_unsupported_platform_shows_state(qapp):
    from apptrackr.ui.main import MainWindow

    tracker = Tracker(NullPlatform())
    win = MainWindow(tracker, None)
    win.show_page("dashboard")
    win._tick()
    assert win._views["dashboard"].now.name.text() == "Tracking unavailable"
    assert "Windows" in win._status.text()
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
