"""Motion system: helpers finish cleanly, respect reduced motion and leave no effects behind."""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget  # noqa: E402

from apptrackr.data import db, demo, queries  # noqa: E402
from apptrackr.ui import motion  # noqa: E402


@pytest.fixture
def qapp():
    from apptrackr.ui.main import prepare_app

    app = QApplication.instance() or QApplication([])
    prepare_app(app)
    return app


def settle(ms=700):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_setting_overrides_system_preference(qapp):
    assert motion.enabled() == motion.system_allows_animation()
    motion.set_enabled(False)
    assert db.get_setting("animations") == "0" and not motion.enabled()
    motion.set_enabled(True)
    assert motion.enabled()
    motion.set_enabled(None)
    assert motion.enabled() == motion.system_allows_animation()


def test_reduced_motion_applies_end_state_immediately(qapp):
    motion.force(False)
    seen, done = [], []
    w = QWidget()
    motion.tween(w, 0.0, 1.0, motion.SLOW, seen.append, on_done=lambda: done.append(True))
    assert seen == [1.0] and done == [True]
    motion.fade(w, 0.0, 1.0)
    assert w.graphicsEffect() is None


def test_tween_runs_to_completion_and_retargets(qapp):
    motion.force(True)
    w = QWidget()
    seen = []
    motion.tween(w, 0.0, 10.0, motion.FAST, seen.append, key="x")
    assert seen[0] == 0.0  # first frame applied immediately
    motion.tween(w, seen[-1], 20.0, motion.FAST, seen.append, key="x")
    settle(400)
    assert seen[-1] == pytest.approx(20.0)
    assert motion.running(w, "x") is None


def test_fade_and_collapse_clean_up(qapp):
    motion.force(True)
    host = QWidget()
    lay = QVBoxLayout(host)
    row = QLabel("row")
    lay.addWidget(row)
    host.show()
    motion.fade(row, 0.0, 1.0)
    assert row.graphicsEffect() is not None
    settle()
    assert row.graphicsEffect() is None
    removed = []
    motion.collapse(row, lambda: removed.append(True))
    settle()
    assert removed == [True] and row.maximumHeight() == 0


def test_stat_tile_counts_to_value(qapp):
    from apptrackr.ui.widgets.components import StatTile

    motion.force(True)
    tile = StatTile("Today", "clock")
    tile.show()
    tile.set_number(120, lambda v: str(int(round(v))))
    assert tile.value.text() != "120"  # counting up from zero
    settle()
    assert tile.value.text() == "120"
    tile.set_number(121, lambda v: str(int(round(v))))  # small change: no animation
    assert tile.value.text() == "121"


def test_window_animations_settle(qapp):
    from apptrackr.core.platform import DemoPlatform
    from apptrackr.core.tracker import Tracker
    from apptrackr.ui.main import MainWindow

    motion.force(True)
    demo.seed(days=20)
    tracker = Tracker(DemoPlatform())
    tracker.reload_settings()
    tracker.tick()
    win = MainWindow(tracker, None, demo=True)
    win.resize(1200, 780)
    win.show()
    for page in ("calendar", "apps", "rewards", "village", "dashboard"):
        win.show_page(page)
        settle(120)  # switch again before animations finish
    win._views["apps"].sort._group.button(2).click()
    win.open_app(queries.find_app_id("code.exe"))
    db.set_setting("ui_mode", "light")
    win.apply_theme()
    win.show_page("rewards")
    win._views["rewards"]._claim_all()
    settle(1500)

    from apptrackr.rewards import engine

    assert engine.unclaimed_count() == 0
    for view in win._views.values():
        assert view.graphicsEffect() is None
    sort = win._views["apps"].sort
    assert sort._thumb.geometry() == sort._group.checkedButton().geometry()
    checked = win._nav_buttons["rewards"]
    assert abs(win._indicator.geometry().center().y() - checked.geometry().center().y()) <= 1
    overlays = [
        c for c in win.centralWidget().children() if isinstance(c, QLabel) and c.pixmap() and not c.pixmap().isNull()
    ]
    assert overlays == []  # theme crossfade overlay removed
    tracker.stop()
    win._quitting = True
    win.close()
