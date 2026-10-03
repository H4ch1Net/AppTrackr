"""Read and write helpers for apps, sessions and daily aggregates."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from . import catalog, db
from .spans import split_by_day, split_by_hour

CATEGORIES = ("Work", "Study", "Development", "Communication", "Games", "Social", "Entertainment", "Tools")

SORT_FOCUSED = "focused"
SORT_LEAST = "least"
SORT_OPENS = "opens"
SORT_CLICKS = "clicks"

_ORDER_SQL = {
    SORT_FOCUSED: "focused_ms DESC",
    SORT_LEAST: "focused_ms ASC",
    SORT_OPENS: "opens_count DESC, focused_ms DESC",
    SORT_CLICKS: "clicks_count DESC, focused_ms DESC",
}


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------


def today_str() -> str:
    return date.today().isoformat()


def days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def week_start() -> str:
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------


def find_app_id(exe_name: str) -> int | None:
    row = db.fetchone("SELECT app_id FROM apps WHERE exe_name = ?", (catalog.canonical_exe(exe_name),))
    return row["app_id"] if row else None


def get_or_create_app(exe_name: str, icon_path: str | None = None) -> int:
    """Return the app_id for *exe_name*, creating the row on first sight."""
    exe = catalog.canonical_exe(exe_name)
    row = db.fetchone("SELECT app_id, display_name, icon_path FROM apps WHERE exe_name = ?", (exe,))
    if row:
        needs_name = not (row["display_name"] or "").strip()
        needs_icon = bool(icon_path) and not row["icon_path"]
        if needs_name or needs_icon:
            db.execute(
                "UPDATE apps SET display_name = COALESCE(display_name, ?), "
                "icon_path = COALESCE(icon_path, ?) WHERE app_id = ?",
                (catalog.friendly_name(exe), icon_path, row["app_id"]),
            )
            db.commit()
        return row["app_id"]
    cur = db.execute(
        "INSERT INTO apps (exe_name, display_name, icon_path) VALUES (?, ?, ?)",
        (exe, catalog.friendly_name(exe), icon_path),
    )
    db.commit()
    return int(cur.lastrowid)


def get_app(app_id: int) -> dict | None:
    row = db.fetchone("SELECT * FROM apps WHERE app_id = ?", (app_id,))
    if not row:
        return None
    app = dict(row)
    app["name"] = catalog.display_name(app)
    return app


def list_apps(include_hidden: bool = False) -> list[dict]:
    sql = "SELECT * FROM apps" + ("" if include_hidden else " WHERE is_hidden = 0")
    apps = []
    for r in db.fetchall(sql):
        app = dict(r)
        if not catalog.is_listable(app["exe_name"]):
            continue
        app["name"] = catalog.display_name(app)
        apps.append(app)
    apps.sort(key=lambda a: a["name"].lower())
    return apps


def hidden_apps() -> list[dict]:
    rows = db.fetchall("SELECT * FROM apps WHERE is_hidden = 1")
    apps = [dict(r) | {"name": catalog.display_name(dict(r))} for r in rows]
    return sorted(apps, key=lambda a: a["name"].lower())


def hidden_exes() -> set[str]:
    return {r["exe_name"] for r in db.fetchall("SELECT exe_name FROM apps WHERE is_hidden = 1")}


def set_favorite(app_id: int, is_fav: bool) -> None:
    db.execute("UPDATE apps SET is_favorite = ? WHERE app_id = ?", (int(is_fav), app_id))
    db.commit()


def set_category(app_id: int, category: str | None) -> None:
    db.execute("UPDATE apps SET category = ? WHERE app_id = ?", (category or None, app_id))
    db.commit()


def set_display_name(app_id: int, name: str | None) -> None:
    db.execute("UPDATE apps SET display_name = ? WHERE app_id = ?", ((name or "").strip() or None, app_id))
    db.commit()


def set_hidden(app_id: int, hidden: bool) -> None:
    db.execute("UPDATE apps SET is_hidden = ? WHERE app_id = ?", (int(hidden), app_id))
    db.commit()


def set_daily_limit(app_id: int, limit_ms: int | None) -> None:
    db.execute("UPDATE apps SET daily_limit_ms = ? WHERE app_id = ?", (limit_ms or None, app_id))
    db.commit()


def apps_with_limits() -> list[dict]:
    rows = db.fetchall("SELECT * FROM apps WHERE daily_limit_ms IS NOT NULL AND daily_limit_ms > 0 AND is_hidden = 0")
    return [dict(r) | {"name": catalog.display_name(dict(r))} for r in rows]


# ---------------------------------------------------------------------------
# Sessions and aggregates (written by the tracker)
# ---------------------------------------------------------------------------


def start_session(app_id: int, ts: float) -> int:
    cur = db.execute(
        "INSERT INTO usage_sessions (app_id, start_ts, end_ts, duration_ms) VALUES (?, ?, ?, 0)",
        (app_id, ts, ts),
    )
    db.commit()
    return int(cur.lastrowid)


def update_session_end(session_id: int, end_ts: float, was_idle: bool = False) -> None:
    db.execute(
        "UPDATE usage_sessions SET end_ts = ?, duration_ms = MAX(0, CAST((? - start_ts) * 1000 AS INTEGER)), "
        "was_idle = ? WHERE session_id = ?",
        (end_ts, end_ts, int(was_idle), session_id),
    )


def add_focus_span(app_id: int, start_ts: float, end_ts: float) -> None:
    """Credit [start_ts, end_ts) of focus to *app_id*, split across local days."""
    for day, ms in split_by_day(start_ts, end_ts):
        db.execute(
            "INSERT INTO daily_rollup (day, app_id, focused_ms) VALUES (?, ?, ?) "
            "ON CONFLICT(day, app_id) DO UPDATE SET focused_ms = focused_ms + excluded.focused_ms",
            (day, app_id, ms),
        )


def increment_opens(day: str, app_id: int, count: int = 1) -> None:
    db.execute(
        "INSERT INTO daily_rollup (day, app_id, opens_count) VALUES (?, ?, ?) "
        "ON CONFLICT(day, app_id) DO UPDATE SET opens_count = opens_count + excluded.opens_count",
        (day, app_id, count),
    )
    db.commit()


def increment_clicks(day: str, app_id: int, count: int = 1) -> None:
    db.execute(
        "INSERT INTO daily_rollup (day, app_id, clicks_count) VALUES (?, ?, ?) "
        "ON CONFLICT(day, app_id) DO UPDATE SET clicks_count = clicks_count + excluded.clicks_count",
        (day, app_id, count),
    )
    db.commit()


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


def _visible(rows) -> list[dict]:
    out = []
    for r in rows:
        app = dict(r)
        if not catalog.is_listable(app.get("exe_name", "")):
            continue
        app["name"] = catalog.display_name(app)
        out.append(app)
    return out


def top_apps(
    start_day: str,
    end_day: str,
    sort: str = SORT_FOCUSED,
    limit: int | None = 20,
    category: str | None = None,
    favorites_only: bool = False,
    search: str = "",
) -> list[dict]:
    """Aggregate usage per app for an inclusive day range."""
    where = ["r.day BETWEEN ? AND ?", "a.is_hidden = 0"]
    params: list = [start_day, end_day]
    if category:
        where.append("a.category = ?")
        params.append(category)
    if favorites_only:
        where.append("a.is_favorite = 1")
    having = {
        SORT_OPENS: "SUM(r.opens_count) > 0",
        SORT_CLICKS: "SUM(r.clicks_count) > 0",
    }.get(sort, "SUM(r.focused_ms) > 0")
    rows = db.fetchall(
        "SELECT a.app_id, a.exe_name, a.display_name, a.icon_path, a.is_favorite, a.category, "
        "       a.daily_limit_ms, SUM(r.focused_ms) AS focused_ms, SUM(r.opens_count) AS opens_count, "
        "       SUM(r.clicks_count) AS clicks_count, COUNT(DISTINCT CASE WHEN r.focused_ms > 0 "
        "       THEN r.day END) AS active_days "
        "FROM daily_rollup r JOIN apps a ON a.app_id = r.app_id "
        f"WHERE {' AND '.join(where)} GROUP BY a.app_id HAVING {having} "
        f"ORDER BY {_ORDER_SQL.get(sort, _ORDER_SQL[SORT_FOCUSED])}",
        tuple(params),
    )
    apps = _visible(rows)
    if search:
        q = search.strip().lower()
        apps = [a for a in apps if q in a["name"].lower() or q in a["exe_name"]]
    return apps[:limit] if limit else apps


def total_ms(start_day: str, end_day: str) -> int:
    return sum(a["focused_ms"] for a in top_apps(start_day, end_day, limit=None))


def daily_totals(start_day: str, end_day: str) -> dict[str, int]:
    """Focused milliseconds per day for an inclusive range (days without data omitted)."""
    rows = db.fetchall(
        "SELECT r.day, a.exe_name, SUM(r.focused_ms) AS ms FROM daily_rollup r "
        "JOIN apps a ON a.app_id = r.app_id WHERE r.day BETWEEN ? AND ? AND a.is_hidden = 0 "
        "GROUP BY r.day, a.exe_name",
        (start_day, end_day),
    )
    totals: dict[str, int] = {}
    for r in rows:
        if r["ms"] and catalog.is_listable(r["exe_name"]):
            totals[r["day"]] = totals.get(r["day"], 0) + r["ms"]
    return totals


def hourly_totals(day: str, app_id: int | None = None) -> list[int]:
    """Focused milliseconds for each hour (0-23) of *day*, built from sessions."""
    d = date.fromisoformat(day)
    start = datetime.combine(d, datetime.min.time()).timestamp()
    end = datetime.combine(d + timedelta(days=1), datetime.min.time()).timestamp()
    sql = (
        "SELECT s.start_ts, s.end_ts, a.exe_name FROM usage_sessions s JOIN apps a ON a.app_id = s.app_id "
        "WHERE s.end_ts > ? AND s.start_ts < ? AND a.is_hidden = 0"
    )
    params: tuple = (start, end)
    if app_id is not None:
        sql += " AND s.app_id = ?"
        params += (app_id,)
    hours = [0] * 24
    for s in db.fetchall(sql, params):
        if not catalog.is_listable(s["exe_name"]):
            continue
        for hour_dt, ms in split_by_hour(max(s["start_ts"], start), min(s["end_ts"], end)):
            hours[hour_dt.hour] += ms
    return hours


def app_daily_history(app_id: int, days: int = 30) -> list[dict]:
    """One entry per day for the last *days* days (including today), zero-filled."""
    start = date.today() - timedelta(days=days - 1)
    rows = db.fetchall(
        "SELECT day, focused_ms, opens_count, clicks_count FROM daily_rollup WHERE app_id = ? AND day >= ?",
        (app_id, start.isoformat()),
    )
    by_day = {r["day"]: dict(r) for r in rows}
    history = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        history.append(by_day.get(d, {"day": d, "focused_ms": 0, "opens_count": 0, "clicks_count": 0}))
    return history


def app_summary(app_id: int) -> dict:
    row = db.fetchone(
        "SELECT MIN(day) AS first_day, MAX(CASE WHEN focused_ms > 0 THEN day END) AS last_day, "
        "COALESCE(SUM(focused_ms), 0) AS total_ms, "
        "COUNT(CASE WHEN focused_ms > 0 THEN 1 END) AS active_days "
        "FROM daily_rollup WHERE app_id = ?",
        (app_id,),
    )
    longest = db.fetchone("SELECT COALESCE(MAX(duration_ms), 0) AS ms FROM usage_sessions WHERE app_id = ?", (app_id,))
    summary = dict(row) if row else {"first_day": None, "last_day": None, "total_ms": 0, "active_days": 0}
    summary["longest_session_ms"] = longest["ms"] if longest else 0
    return summary


def recent_sessions(app_id: int, limit: int = 25, min_ms: int = 1000) -> list[dict]:
    rows = db.fetchall(
        "SELECT session_id, start_ts, end_ts, duration_ms, was_idle FROM usage_sessions "
        "WHERE app_id = ? AND duration_ms >= ? ORDER BY start_ts DESC LIMIT ?",
        (app_id, min_ms, limit),
    )
    return [dict(r) for r in rows]


def app_usage_on(day: str, app_id: int) -> int:
    row = db.fetchone("SELECT focused_ms FROM daily_rollup WHERE day = ? AND app_id = ?", (day, app_id))
    return row["focused_ms"] if row else 0


def first_tracked_day() -> str | None:
    row = db.fetchone("SELECT MIN(day) AS d FROM daily_rollup WHERE focused_ms > 0")
    return row["d"] if row else None
