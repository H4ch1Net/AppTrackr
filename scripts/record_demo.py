"""Record a short animated GIF of AppTrackr's UI in motion, from demo data.

    pip install pillow
    python scripts/record_demo.py [--out docs/screenshots/demo.gif] [--frames-dir DIR]

Runs offscreen against a temporary database. Frames are grabbed in real time
while a scripted tour drives the window, then written as an optimized GIF.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(ROOT / "docs" / "screenshots" / "demo.gif"))
    parser.add_argument("--frames-dir", help="also save every frame as PNG here (for inspection)")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--scale", type=float, default=0.6, help="GIF scale factor")
    parser.add_argument("--fps", type=int, default=25, help="playback frame rate")
    parser.add_argument(
        "--slowdown", type=float, default=4.0, help="run animations this many times slower while capturing"
    )
    args = parser.parse_args()

    try:
        from PIL import Image
    except ImportError:
        print("Pillow is required: pip install pillow")
        return 1

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from screenshots import shift_clock_to_afternoon

    shift_clock_to_afternoon()

    from apptrackr import paths

    paths.set_data_dir(Path(tempfile.mkdtemp(prefix="apptrackr-demo-gif-")))

    from PySide6.QtCore import QBuffer, QByteArray, QElapsedTimer, QEventLoop, QIODevice, QTimer
    from PySide6.QtWidgets import QApplication

    from apptrackr.core.platform import DemoPlatform
    from apptrackr.core.tracker import Tracker
    from apptrackr.data import db, demo, queries
    from apptrackr.ui import motion
    from apptrackr.ui.main import MainWindow, prepare_app

    db.init_db()
    demo.seed()
    motion.force(True)
    motion.time_scale = args.slowdown
    app = QApplication(sys.argv[:1])
    prepare_app(app)

    tracker = Tracker(DemoPlatform())
    tracker.reload_settings()
    tracker.tick()
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
    window.show_page("calendar")  # start elsewhere so the dashboard entrance is visible
    window.show()

    frames: list[tuple[int, Image.Image]] = []
    clock = QElapsedTimer()
    clock.start()
    interval = int(1000 / args.fps * args.slowdown)

    def capture() -> None:
        pixmap = window.grab()
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.toImage().save(buf, "PNG")
        image = Image.open(io.BytesIO(bytes(data))).convert("RGB")
        if args.scale != 1:
            image = image.resize((int(image.width * args.scale), int(image.height * args.scale)), Image.LANCZOS)
        frames.append((clock.elapsed(), image))

    def wait(ms: int) -> None:
        """Wait *ms* of playback time (scaled by the slowdown while capturing)."""
        loop = QEventLoop()
        QTimer.singleShot(int(ms * args.slowdown), loop.quit)
        loop.exec()

    timer = QTimer()
    timer.timeout.connect(capture)

    wait(150)
    timer.start(interval)

    # Tour ------------------------------------------------------------------
    window.show_page("dashboard")
    wait(1700)
    window.show_page("calendar")
    wait(900)
    cal = window._views["calendar"]
    from datetime import date, timedelta

    target = date.today() - timedelta(days=1)
    cal.heatmap.set_selected(target)
    cal._on_day(target.isoformat())
    wait(900)
    cal._shift(-1)
    wait(1100)
    window.show_page("apps")
    wait(800)
    window._views["apps"].sort._group.button(2).click()
    wait(1000)
    window.open_app(queries.find_app_id("code.exe"))
    wait(1200)
    window.show_page("rewards")
    wait(700)
    window._views["rewards"]._claim_all()
    wait(1500)
    window.show_page("dashboard")
    wait(700)
    db.set_setting("ui_mode", "light")
    window.apply_theme()
    wait(1300)

    timer.stop()
    tracker.stop()

    if args.frames_dir:
        out_dir = Path(args.frames_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, (_t, image) in enumerate(frames):
            image.save(out_dir / f"frame_{i:03d}.png")

    # Merge frames that barely differ (idle moments where only the timer ticks) to keep the GIF small.
    from PIL import ImageChops, ImageStat

    times = [t for t, _ in frames] + [frames[-1][0] + 1500 * args.slowdown]
    kept: list[tuple[Image.Image, int]] = []
    for i, (_t, image) in enumerate(frames):
        duration = int((times[i + 1] - times[i]) / args.slowdown)
        if kept and sum(ImageStat.Stat(ImageChops.difference(kept[-1][0], image)).mean) < 0.6:
            kept[-1] = (kept[-1][0], kept[-1][1] + duration)
        else:
            kept.append((image, duration))
    images = [img.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for img, _ in kept]
    durations = [max(20, d) for _, d in kept]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(out, save_all=True, append_images=images[1:], duration=durations, loop=0, optimize=True, disposal=1)
    print(f"wrote {out} ({len(images)} frames, {out.stat().st_size / 1e6:.1f} MB)")
    window.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
