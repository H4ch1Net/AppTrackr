"""Text formatting for durations, dates and rewards."""

from __future__ import annotations

from datetime import date, datetime

RESOURCE_LABELS = {
    "xp": "XP",
    "credits": "credits",
    "wood": "wood",
    "stone": "stone",
    "metal": "metal",
    "food": "food",
    "blueprints": "blueprints",
}
_REWARD_ORDER = ("xp", "credits", "wood", "stone", "metal", "food", "blueprints")


def duration(ms: int | float, short: bool = False) -> str:
    """'2h 15m', '45m', '30s'. With short=True seconds are dropped above a minute."""
    seconds = max(0, int(ms // 1000))
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m" if short or not seconds or minutes >= 10 else f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if minutes else f"{hours}h"


def clock(ms: int | float) -> str:
    """Live timer format: '1:04:09' or '4:09'."""
    seconds = max(0, int(ms // 1000))
    hours, rem = divmod(seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def axis(ms: int | float) -> str:
    """Compact engraved axis label: 0, 15M, 1H, 1H30, 12H."""
    minutes = int(ms // 60000)
    if minutes == 0:
        return "0"
    if minutes < 60:
        return f"{minutes}M"
    hours, rest = divmod(minutes, 60)
    return f"{hours}H{rest:02d}" if rest else f"{hours}H"


def percent_change(current: float, previous: float) -> str | None:
    if previous <= 0:
        return None
    change = (current - previous) / previous * 100
    return f"{change:+.0f}%"


def long_date(d: date | str) -> str:
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return f"{d:%A}, {d:%B} {d.day}"


def short_date(d: date | str) -> str:
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return f"{d:%b} {d.day}"


def relative_day(d: date | str | None) -> str:
    if not d:
        return "Never"
    d = date.fromisoformat(d) if isinstance(d, str) else d
    delta = (date.today() - d).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    if delta < 7:
        return f"{delta} days ago"
    return short_date(d) if d.year == date.today().year else f"{short_date(d)}, {d.year}"


def time_of_day(ts: float) -> str:
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%H:%M")


def reward(reward: dict, sep: str = "  ") -> str:
    parts = []
    for key in _REWARD_ORDER:
        if reward.get(key):
            parts.append(f"+{reward[key]} {RESOURCE_LABELS[key]}")
    if reward.get("level_up"):
        parts.append(f"Level {reward['level_up']}")
    return sep.join(parts)


def count(n: int) -> str:
    return f"{n:,}"
