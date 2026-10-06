"""Entry point: `python -m apptrackr`, the `apptrackr` script or the PyInstaller bundle.

Imports are absolute because PyInstaller runs this file as a top-level script.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import logging
import logging.handlers
import shutil
import sys
import tempfile
from pathlib import Path

from apptrackr import APP_NAME, APP_USER_MODEL_ID, __version__, paths

log = logging.getLogger("apptrackr")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="apptrackr", description="Track foreground app usage on Windows.")
    parser.add_argument("--minimized", action="store_true", help="start hidden in the system tray")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run with generated sample data in a temporary folder (nothing real is recorded)",
    )
    parser.add_argument("--data-dir", metavar="PATH", help="store data in PATH instead of the default location")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return parser.parse_args(argv)


def setup_logging(debug: bool) -> None:
    handlers: list[logging.Handler] = []
    if sys.stderr is not None:  # pythonw / windowed builds have no console
        handlers.append(logging.StreamHandler())
    try:
        paths.log_dir().mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.handlers.RotatingFileHandler(
                paths.log_dir() / "apptrackr.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
            )
        )
    except OSError:
        pass
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        handlers=handlers,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    def excepthook(exc_type, exc, tb):
        log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = excepthook


def _instance_key() -> str:
    """Socket name shared by every launch that uses the same data folder."""
    folder = hashlib.sha1(str(paths.data_dir().resolve()).encode()).hexdigest()[:10]
    return f"{APP_NAME}-{getpass.getuser()}-{folder}"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if args.self_test:
        return self_test()
    if args.demo:
        paths.set_data_dir(Path(tempfile.mkdtemp(prefix="apptrackr-demo-")))
    elif args.data_dir:
        paths.set_data_dir(args.data_dir)
    setup_logging(args.debug)

    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass

    from PySide6.QtCore import QLockFile, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("H4ch1Net")
    app.setQuitOnLastWindowClosed(False)

    # Single instance: a lock file decides who runs; a local socket lets a second
    # launch ask the running instance to show its window.
    key = _instance_key()
    paths.data_dir().mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(paths.data_dir() / "apptrackr.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(500):
        probe = QLocalSocket()
        probe.connectToServer(key)
        if probe.waitForConnected(1000):
            probe.write(b"show")
            probe.flush()
            probe.waitForBytesWritten(500)
        log.info("Already running; asked the existing window to show")
        return 0
    QLocalServer.removeServer(key)
    server = QLocalServer()
    if not server.listen(key):
        log.warning("Could not listen for other launches: %s", server.errorString())

    from apptrackr.core.clicks import ClickCounter
    from apptrackr.core.platform import create_platform
    from apptrackr.core.process_watch import ProcessWatcher
    from apptrackr.core.tracker import Tracker
    from apptrackr.data import db
    from apptrackr.ui.main import MainWindow, prepare_app

    try:
        db.init_db()
    except Exception:
        log.exception("Could not open or upgrade the database")
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(
            None,
            APP_NAME,
            "AppTrackr could not open or upgrade its data, so it did not start. Your data was not changed, "
            f"and a backup copy is kept next to it in:\n{paths.data_dir()}\n\n"
            f"Details are in the log:\n{paths.log_dir()}",
        )
        return 1
    if not args.demo:
        from apptrackr.core import autostart
        from apptrackr.rewards import rules

        autostart.repair()
        rules.adopt_favorites_once()
    if args.demo:
        from apptrackr.data import demo

        demo.seed()
        log.info("Demo mode: sample data in %s", paths.data_dir())

    prepare_app(app)

    tracker = Tracker(create_platform(demo=args.demo))
    tracker.start()
    watcher = ProcessWatcher()
    if tracker.supported and not args.demo:
        watcher.start()
    clicks = ClickCounter(tracker)
    clicks.set_enabled(db.get_bool("track_clicks") and not args.demo)

    window = MainWindow(tracker, clicks, demo=args.demo)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), window.bring_to_front()))
    QGuiApplication.styleHints().colorSchemeChanged.connect(
        lambda *_: db.get_setting("ui_mode", "dark") == "system" and window.apply_theme()
    )

    if not args.minimized or not window.has_tray():
        window.show()

    def shutdown():
        log.info("Shutting down")
        clicks.stop()
        watcher.stop()
        tracker.stop()
        server.close()
        lock.unlock()
        if args.demo:
            db.close()
            shutil.rmtree(paths.data_dir(), ignore_errors=True)

    app.aboutToQuit.connect(shutdown)
    # Windows sign-out and installers closing the app (Restart Manager) ask to save first.
    app.commitDataRequest.connect(lambda *_: tracker.flush())
    log.info("%s %s started (data: %s)", APP_NAME, __version__, paths.data_dir())
    return app.exec()


def self_test() -> int:
    """Build the whole UI offscreen against a throwaway database. Used to verify packaged builds."""
    import os

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    paths.set_data_dir(Path(tempfile.mkdtemp(prefix="apptrackr-selftest-")))
    from PySide6.QtWidgets import QApplication

    from apptrackr.core.platform import NullPlatform
    from apptrackr.core.tracker import Tracker
    from apptrackr.data import db, demo
    from apptrackr.ui import fonts
    from apptrackr.ui.main import MainWindow, prepare_app

    db.init_db()
    demo.seed(days=7)
    app = QApplication(sys.argv[:1])
    prepare_app(app)
    if fonts.load() != (fonts.SANS, fonts.MONO):
        print("self-test: bundled fonts did not load", file=sys.stderr)
        return 1
    window = MainWindow(Tracker(NullPlatform()))
    for page in ("dashboard", "calendar", "apps", "rewards", "village", "settings"):
        window.show_page(page)
    app.processEvents()
    return 0


if __name__ == "__main__":
    sys.exit(main())
