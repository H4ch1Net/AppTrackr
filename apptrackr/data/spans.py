"""Helpers for splitting time spans at local midnight."""

from __future__ import annotations

from datetime import datetime, timedelta
from datetime import time as dtime


def split_by_day(start_ts: float, end_ts: float) -> list[tuple[str, int]]:
    """Split [start_ts, end_ts) into (YYYY-MM-DD, milliseconds) parts per local day."""
    parts: list[tuple[str, int]] = []
    if end_ts <= start_ts:
        return parts
    cursor = start_ts
    while cursor < end_ts:
        day = datetime.fromtimestamp(cursor).date()
        next_midnight = datetime.combine(day + timedelta(days=1), dtime.min).timestamp()
        stop = min(end_ts, next_midnight)
        ms = int(round((stop - cursor) * 1000))
        if ms > 0:
            parts.append((day.isoformat(), ms))
        cursor = stop
    return parts


def split_by_hour(start_ts: float, end_ts: float) -> list[tuple[datetime, int]]:
    """Split a span into (local hour start, milliseconds) parts."""
    parts: list[tuple[datetime, int]] = []
    cursor = start_ts
    while cursor < end_ts:
        dt = datetime.fromtimestamp(cursor).replace(minute=0, second=0, microsecond=0)
        stop = min(end_ts, (dt + timedelta(hours=1)).timestamp())
        ms = int(round((stop - cursor) * 1000))
        if ms > 0:
            parts.append((dt, ms))
        cursor = stop
    return parts
