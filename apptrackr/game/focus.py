"""Flow: unbroken runs of time in focus apps, and the focus points they earn.

A run continues while the gaps between focus-app sessions stay within the
grace period (a quick look at chat or docs does not end it). Time outside
focus apps never earns points; inside a run, each minute earns the multiplier
of the tier the run has reached.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

from ..data import db
from . import economy

LOOKBACK_SEC = (economy.FLOW_TIERS[-1][0] + 60) * 60  # enough history to know a run's tier


@dataclass(frozen=True)
class Flow:
    active: bool  # the foreground app is a focus app right now
    run_ms: int  # length of the current (or last) run, wall clock
    multiplier: float
    tier: str
    next_tier: str | None
    next_in_ms: int  # time until the next tier, 0 at the top
    today_focus_ms: int


def multiplier_at(run_minutes: float) -> float:
    return economy.FLOW_TIERS[economy.tier_index(run_minutes)][1]


def _weighted_minutes(e0: float, e1: float) -> float:
    """Integral of the multiplier between e0 and e1 seconds into a run, in minutes."""
    total = 0.0
    tiers = economy.FLOW_TIERS
    for i, (start, mult, _name) in enumerate(tiers):
        lo = start * 60
        hi = tiers[i + 1][0] * 60 if i + 1 < len(tiers) else float("inf")
        a, b = max(e0, lo), min(e1, hi)
        if b > a:
            total += (b - a) * mult
    return total / 60


def runs(spans: list[tuple[float, float]], grace_sec: float) -> list[list[tuple[float, float]]]:
    """Group sorted (start, end) focus spans into runs."""
    out: list[list[tuple[float, float]]] = []
    last_end = None
    for start, end in sorted(spans):
        if end <= start:
            continue
        if last_end is None or start - last_end > grace_sec:
            out.append([])
        out[-1].append((start, end))
        last_end = max(end, last_end or end)
    return out


def points(spans: list[tuple[float, float]], grace_sec: float, since: float, until: float) -> tuple[float, int]:
    """Focus points and focused milliseconds earned between *since* and *until*."""
    fp = 0.0
    focus_ms = 0
    for run in runs(spans, grace_sec):
        run_start = run[0][0]
        for start, end in run:
            a, b = max(start, since), min(end, until)
            if b <= a:
                continue
            fp += _weighted_minutes(a - run_start, b - run_start)
            focus_ms += int((b - a) * 1000)
    return fp, focus_ms


def focus_app_ids() -> set[int]:
    rows = db.fetchall(
        "SELECT DISTINCT r.app_id FROM reward_rules r JOIN apps a ON a.app_id = r.app_id "
        "WHERE r.enabled = 1 AND a.is_hidden = 0"
    )
    return {r["app_id"] for r in rows}


def load_spans(since: float, until: float, app_ids: set[int] | None = None) -> list[tuple[float, float]]:
    """Focus-app sessions overlapping [since, until], clipped to it."""
    app_ids = focus_app_ids() if app_ids is None else app_ids
    if not app_ids:
        return []
    marks = ",".join("?" * len(app_ids))
    rows = db.fetchall(
        f"SELECT start_ts, end_ts FROM usage_sessions WHERE app_id IN ({marks}) "
        "AND end_ts IS NOT NULL AND end_ts > ? AND start_ts < ? ORDER BY start_ts",
        (*app_ids, since, until),
    )
    return [(max(r["start_ts"], since), min(r["end_ts"], until)) for r in rows]


def grace_sec(tavern_level: int = 0) -> float:
    return economy.FLOW_GRACE_SEC + economy.TAVERN_GRACE_SEC * tavern_level


def points_between(since: float, until: float, tavern_level: int = 0) -> tuple[float, int]:
    """Focus points earned in [since, until], reading sessions from the database."""
    spans = load_spans(since - LOOKBACK_SEC, until)
    return points(spans, grace_sec(tavern_level), since, until)


def _day_start(ts: float) -> float:
    d = datetime.fromtimestamp(ts)
    return datetime(d.year, d.month, d.day).timestamp()


def current(
    now: float | None = None,
    live_app_id: int | None = None,
    live_since: float | None = None,
    tavern_level: int = 0,
) -> Flow:
    """The flow state right now. *live_app_id*/*live_since* extend the stored sessions with
    the session still in progress (the tracker writes it every 30 seconds)."""
    now = now or time.time()
    ids = focus_app_ids()
    spans = load_spans(now - max(LOOKBACK_SEC, now - _day_start(now)), now, ids)
    active = live_app_id in ids
    if active and live_since is not None:
        spans.append((live_since, now))
    grace = grace_sec(tavern_level)
    all_runs = runs(spans, grace)
    today = _day_start(now)
    today_ms = 0
    for start, end in _merge(spans):
        if end > today:
            today_ms += int((end - max(start, today)) * 1000)
    run = all_runs[-1] if all_runs else []
    in_run = bool(run) and now - max(e for _s, e in run) <= grace
    run_ms = int((min(now, max(e for _s, e in run)) - run[0][0]) * 1000) if run and in_run else 0
    minutes = run_ms / 60000
    index = economy.tier_index(minutes)
    _start, mult, name = economy.FLOW_TIERS[index]
    nxt = economy.FLOW_TIERS[index + 1] if index + 1 < len(economy.FLOW_TIERS) else None
    return Flow(
        active=active,
        run_ms=run_ms,
        multiplier=mult if in_run else 1.0,
        tier=name if in_run else economy.FLOW_TIERS[0][2],
        next_tier=nxt[2] if nxt else None,
        next_in_ms=max(0, int(nxt[0] * 60000 - run_ms)) if nxt else 0,
        today_focus_ms=today_ms,
    )


def _merge(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out
