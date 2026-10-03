"""Application-wide Qt signals and a helper for running work off the GUI thread."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)


class Bus(QObject):
    theme_changed = Signal()
    data_changed = Signal()  # app metadata, history or restore
    rewards_changed = Signal()
    toast = Signal(str, str)  # message, tone


bus = Bus()


class _Relay(QObject):
    done = Signal(object)
    failed = Signal(object)


_active: set[_Relay] = set()


def run_async(
    fn: Callable[[], Any],
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[BaseException], None] | None = None,
) -> None:
    """Run *fn* on a worker thread and deliver the result on the GUI thread."""
    relay = _Relay()
    _active.add(relay)

    def finish(callback, value):
        _active.discard(relay)
        if callback:
            callback(value)

    relay.done.connect(lambda v: finish(on_done, v))
    relay.failed.connect(lambda e: finish(on_error, e))

    def worker():
        try:
            result = fn()
        except BaseException as exc:  # delivered to the caller
            log.debug("Background task failed", exc_info=True)
            relay.failed.emit(exc)
        else:
            relay.done.emit(result)
        finally:
            from ..data import db

            db.close()

    threading.Thread(target=worker, daemon=True, name="ui-task").start()
