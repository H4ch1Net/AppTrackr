"""Render README screenshots from demo data.

    python scripts/screenshots.py [--out docs/screenshots] [--width 1280 --height 800]

Runs offscreen (no window appears) with a temporary database, so it never
touches your real data. The demo clock is shifted to mid-afternoon so the
"today" charts have content whatever time you run it.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def shift_clock_to_afternoon(hour: int = 16) -> None:
    """Pick a fixed UTC offset so local time is about *hour*:30 (POSIX only)."""
    if not hasattr(time, "tzset"):
        return
    now = datetime.now(timezone.utc)
    offset = (round(hour + 0.5 - now.hour - now.minute / 60) + 12) % 24 - 12
    os.environ["TZ"] = f"DEMO{-offset}"  # POSIX TZ offsets are west-positive
    time.tzset()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(ROOT / "docs" / "screenshots"))
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--show", action="store_true", help="use the real display instead of offscreen")
    args = parser.parse_args()

    if not args.show:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    shift_clock_to_afternoon()

    from apptrackr import paths

    paths.set_data_dir(Path(tempfile.mkdtemp(prefix="apptrackr-shots-")))

    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from apptrackr.core.platform import DemoPlatform
    from apptrackr.core.tracker import Tracker
    from apptrackr.data import db, demo, queries
    from apptrackr.ui import motion
    from apptrackr.ui.main import MainWindow, prepare_app

    db.init_db()
    demo.seed()
    motion.force(False)  # capture final states, not mid-transition frames
    app = QApplication(sys.argv[:1])
    prepare_app(app)

    tracker = Tracker(DemoPlatform())
    tracker.reload_settings()
    tracker.tick()
    # Backdate the live session so the "Now" card shows a believable timer.
    backdate = 47 * 60 + 12
    tracker._session_start -= backdate
    tracker._committed_until -= backdate
    db.execute(
        "UPDATE usage_sessions SET start_ts = ? WHERE session_id = ?", (tracker._session_start, tracker._session_id)
    )
    tracker._checkpoint(time.time())

    window = MainWindow(tracker, None, demo=True)
    window.setWindowTitle("AppTrackr")
    window.resize(args.width, args.height)
    window.show()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    def settle(ms: int = 250) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def shot(name: str) -> None:
        window._tick()
        settle()
        window.toast.hide()
        window.grab().save(str(out / f"{name}.png"))
        print(f"wrote {out / name}.png")

    for page in ("dashboard", "calendar", "apps", "rewards", "village", "settings"):
        window.show_page(page)
        shot(page)

    window.show_page("apps")
    window.open_app(queries.find_app_id("code.exe"))
    shot("app-detail")

    def scroll_to(view, widget, offset: int = 24) -> None:
        y = widget.mapTo(view.widget(), widget.rect().topLeft()).y()
        view.verticalScrollBar().setValue(max(0, y - offset))

    dashboard = window._views["dashboard"]
    window.show_page("dashboard")
    scroll_to(dashboard, dashboard.other_terms, 380)
    shot("dashboard-perspective")
    dashboard.verticalScrollBar().setValue(0)

    settings = window._views["settings"]
    window.show_page("settings")
    scroll_to(settings, settings.mode.parentWidget().parentWidget(), 24)
    shot("settings-appearance")
    settings.verticalScrollBar().setValue(0)

    # Every palette, each with a different accent, as one montage.
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter

    from apptrackr.ui import fonts, theme

    pairs = (
        ("Graphite", "Orange"),
        ("Carbon", "Cyan"),
        ("Midnight", "Blue"),
        ("Paper", "Orange"),
        ("Porcelain", "Purple"),
        ("Sage", "Green"),
    )
    tw, th, gap, cap = 640, 400, 24, 34
    montage = QImage(3 * tw + 4 * gap, 2 * (th + cap) + 3 * gap, QImage.Format.Format_RGB32)
    montage.fill(QColor(theme.build("Graphite").window))
    painter = QPainter(montage)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    window.show_page("dashboard")
    for i, (palette, accent) in enumerate(pairs):
        kind = "dark" if palette in theme.DARK_PALETTES else "light"
        db.set_setting("ui_mode", kind)
        db.set_setting(f"ui_{kind}_palette", palette)
        db.set_setting("ui_theme", accent)
        window.apply_theme()
        window._tick()
        settle()
        window.toast.hide()
        image = (
            window.grab()
            .toImage()
            .scaled(tw, th, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )
        x, y = gap + (i % 3) * (tw + gap), gap + (i // 3) * (th + cap + gap)
        painter.drawImage(x, y, image)
        painter.setPen(QColor("#edebe4"))
        painter.setFont(fonts.mono(12, 500, 10))
        painter.drawText(
            QRectF(x, y + th + 8, tw, 20), Qt.AlignmentFlag.AlignLeft, f"{palette.upper()}  ·  {accent.upper()}"
        )
    painter.end()
    montage.save(str(out / "themes.png"))
    print(f"wrote {out / 'themes.png'}")

    db.set_setting("ui_dark_palette", theme.DEFAULT_DARK)
    db.set_setting("ui_light_palette", theme.DEFAULT_LIGHT)
    db.set_setting("ui_theme", theme.DEFAULT_ACCENT)
    db.set_setting("ui_mode", "light")
    window.apply_theme()
    window.show_page("dashboard")
    shot("dashboard-light")

    tracker.stop()
    window.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
