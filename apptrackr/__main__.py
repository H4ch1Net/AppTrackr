"""AppTrackr entry point."""

import sys
import logging

from PySide6.QtWidgets import QApplication

from apptrackr.data import db
from apptrackr.core.tracker import Tracker
from apptrackr.core.process_watch import ProcessWatcher
from apptrackr.core.events import ClickCounter
from apptrackr.ui.main import MainWindow
from apptrackr.ui import theme

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("apptrackr")


def main():
    # Init database
    db.init_db()

    # Start background services
    tracker = Tracker()
    tracker.start()

    watcher = ProcessWatcher()
    watcher.start()

    clicker = ClickCounter()
    clicker.start()

    # UI
    app = QApplication(sys.argv)
    app.setApplicationName("AppTrackr")
    
    # Load saved theme before applying stylesheet
    saved_theme = db.get_setting("ui_theme", "Cyan")
    theme.set_theme(saved_theme)
    app.setStyleSheet(theme.get_stylesheet())

    window = MainWindow(tracker)
    window.show()

    exit_code = app.exec()

    # Cleanup
    tracker.stop()
    watcher.stop()
    clicker.stop()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
