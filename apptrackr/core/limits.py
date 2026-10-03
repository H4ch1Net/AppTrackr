"""Daily per-app time limits."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..data import queries


@dataclass
class LimitMonitor:
    """Reports each app at most once per day when it passes its daily limit."""

    _notified: set[tuple[str, int]] = field(default_factory=set)

    def check(self, live_app_id: int | None = None, live_ms: int = 0) -> list[dict]:
        day = queries.today_str()
        self._notified = {key for key in self._notified if key[0] == day}
        reached = []
        for app in queries.apps_with_limits():
            key = (day, app["app_id"])
            if key in self._notified:
                continue
            used = queries.app_usage_on(day, app["app_id"])
            if app["app_id"] == live_app_id:
                used += live_ms
            if used >= app["daily_limit_ms"]:
                self._notified.add(key)
                reached.append(app | {"used_ms": used})
        return reached
