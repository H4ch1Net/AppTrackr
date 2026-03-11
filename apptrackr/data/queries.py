"""Query helpers for AppTrackr analytics."""

from __future__ import annotations

import time
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from . import db


_DASHBOARD_HIDDEN_EXES = {
    "system",
    "registry",
    "idle",
    "dwm.exe",
    "taskhostw.exe",
    "runtimebroker.exe",
    "searchhost.exe",
    "searchindexer.exe",
    "shellexperiencehost.exe",
    "startmenuexperiencehost.exe",
    "textinputhost.exe",
    "applicationframehost.exe",
    "widgetservice.exe",
    "widgets.exe",
    "conhost.exe",
}


_HELPER_EXE_SUBSTRINGS = (
    "helper",
    "crashpad",
    "updater",
)


_NAME_OVERRIDES = {
    "code.exe": "VS Code",
    "claude.exe": "Claude",
    "steam.exe": "Steam",
    "steamwebhelper.exe": "Steam",
    "discord.exe": "Discord",
    "chrome.exe": "Google Chrome",
    "firefox.exe": "Firefox",
    "msedge.exe": "Microsoft Edge",
    "teams.exe": "Microsoft Teams",
    "notepad.exe": "Notepad",
    "notepad++.exe": "Notepad++",
}


def normalize_app_name(exe_name: str) -> str:
    """Convert exe/process names into readable app labels."""
    key = (exe_name or "").strip().lower()
    if not key:
        return "Unknown App"
    if key in _NAME_OVERRIDES:
        return _NAME_OVERRIDES[key]

    raw = Path(key).name
    if raw.endswith(".exe"):
        raw = raw[:-4]

    raw = raw.replace("_", " ").replace("-", " ")
    raw = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()

    if not raw:
        return "Unknown App"
    return " ".join(part.capitalize() for part in raw.split(" "))


def is_dashboard_hidden_process(exe_name: str) -> bool:
    """Return True for process names we don't want in Dashboard Top Apps."""
    name = (exe_name or "").lower().strip()
    if not name:
        return True
    if name in _DASHBOARD_HIDDEN_EXES:
        return True
    return any(token in name for token in _HELPER_EXE_SUBSTRINGS)


# ---------------------------------------------------------------------------
# App CRUD
# ---------------------------------------------------------------------------

def get_or_create_app(
    exe_name: str,
    display_name: str | None = None,
    icon_path: str | None = None,
) -> int:
    """Return app_id for *exe_name*, creating the row if needed."""
    exe_name = (exe_name or "").strip().lower()
    preferred_name = (display_name or normalize_app_name(exe_name)).strip()

    row = db.fetchone(
        "SELECT app_id, display_name, icon_path FROM apps WHERE exe_name = ?",
        (exe_name,),
    )
    if row:
        # Backfill friendly display name and icon for older rows.
        current_display = (row["display_name"] or "").strip()
        needs_display = (not current_display) or (current_display.lower() == exe_name)
        current_icon = row["icon_path"]
        if needs_display or (icon_path and not current_icon):
            db.execute(
                "UPDATE apps SET display_name = COALESCE(?, display_name), "
                "icon_path = COALESCE(icon_path, ?) WHERE app_id = ?",
                (preferred_name if needs_display else None, icon_path, row["app_id"]),
            )
            db.commit()
        return row["app_id"]

    cur = db.execute(
        "INSERT INTO apps (exe_name, display_name, icon_path) VALUES (?, ?, ?)",
        (exe_name, preferred_name, icon_path),
    )
    db.commit()
    return cur.lastrowid  # type: ignore[return-value]


def get_app(app_id: int) -> dict | None:
    row = db.fetchone("SELECT * FROM apps WHERE app_id = ?", (app_id,))
    return dict(row) if row else None


def list_apps() -> list[dict]:
    return [dict(r) for r in db.fetchall("SELECT * FROM apps ORDER BY display_name")]


def set_favorite(app_id: int, is_fav: bool) -> None:
    db.execute("UPDATE apps SET is_favorite = ? WHERE app_id = ?", (int(is_fav), app_id))
    db.commit()


def set_category(app_id: int, category: str | None) -> None:
    db.execute("UPDATE apps SET category = ? WHERE app_id = ?", (category, app_id))
    db.commit()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def start_session(app_id: int, ts: float | None = None) -> int:
    ts = ts or time.time()
    cur = db.execute(
        "INSERT INTO usage_sessions (app_id, start_ts) VALUES (?, ?)",
        (app_id, ts),
    )
    db.commit()
    return cur.lastrowid  # type: ignore[return-value]


def end_session(session_id: int, ts: float | None = None, was_idle: bool = False) -> None:
    ts = ts or time.time()
    db.execute(
        "UPDATE usage_sessions SET end_ts = ?, duration_ms = CAST((? - start_ts) * 1000 AS INTEGER), was_idle = ? "
        "WHERE session_id = ?",
        (ts, ts, int(was_idle), session_id),
    )
    db.commit()


# ---------------------------------------------------------------------------
# Focus events (debug / window-title tracking)
# ---------------------------------------------------------------------------

def log_focus_event(app_id: int, event_type: str, title_hash: str | None = None) -> None:
    db.execute(
        "INSERT INTO focus_events (ts, app_id, window_title_hash, event_type) VALUES (?, ?, ?, ?)",
        (time.time(), app_id, title_hash, event_type),
    )
    db.commit()


# ---------------------------------------------------------------------------
# Daily rollup
# ---------------------------------------------------------------------------

def add_focused_time(day: str, app_id: int, ms: int) -> None:
    db.execute(
        "INSERT INTO daily_rollup (day, app_id, focused_ms) VALUES (?, ?, ?) "
        "ON CONFLICT(day, app_id) DO UPDATE SET focused_ms = focused_ms + ?",
        (day, app_id, ms, ms),
    )
    db.commit()


def increment_opens(day: str, app_id: int) -> None:
    db.execute(
        "INSERT INTO daily_rollup (day, app_id, opens_count) VALUES (?, ?, 1) "
        "ON CONFLICT(day, app_id) DO UPDATE SET opens_count = opens_count + 1",
        (day, app_id),
    )
    db.commit()


def increment_clicks(day: str, app_id: int, count: int = 1) -> None:
    db.execute(
        "INSERT INTO daily_rollup (day, app_id, clicks_count) VALUES (?, ?, ?) "
        "ON CONFLICT(day, app_id) DO UPDATE SET clicks_count = clicks_count + ?",
        (day, app_id, count, count),
    )
    db.commit()


# ---------------------------------------------------------------------------
# Analytic queries
# ---------------------------------------------------------------------------

def today_str() -> str:
    return date.today().isoformat()


def today_total_ms() -> int:
    row = db.fetchone(
        "SELECT COALESCE(SUM(focused_ms), 0) AS total FROM daily_rollup WHERE day = ?",
        (today_str(),),
    )
    return row["total"] if row else 0


def top_apps_today(limit: int = 10) -> list[dict]:
    rows = db.fetchall(
        "SELECT a.app_id, a.exe_name, a.display_name, a.icon_path, a.is_favorite, "
        "       r.focused_ms, r.opens_count, r.clicks_count "
        "FROM daily_rollup r JOIN apps a ON a.app_id = r.app_id "
        "WHERE r.day = ? ORDER BY r.focused_ms DESC LIMIT ?",
        (today_str(), limit),
    )
    return [dict(r) for r in rows]


def dashboard_top_apps_today(limit: int = 10) -> list[dict]:
    """Top apps for dashboard with system/helper processes filtered out."""
    rows = top_apps_today(limit=200)
    filtered = [r for r in rows if not is_dashboard_hidden_process(r.get("exe_name", ""))]
    return filtered[:limit]


def top_apps_range(start_day: str, end_day: str, limit: int = 20) -> list[dict]:
    rows = db.fetchall(
        "SELECT a.app_id, a.exe_name, a.display_name, a.icon_path, a.is_favorite, "
        "       SUM(r.focused_ms) AS focused_ms, SUM(r.opens_count) AS opens_count, "
        "       SUM(r.clicks_count) AS clicks_count "
        "FROM daily_rollup r JOIN apps a ON a.app_id = r.app_id "
        "WHERE r.day BETWEEN ? AND ? GROUP BY a.app_id ORDER BY focused_ms DESC LIMIT ?",
        (start_day, end_day, limit),
    )
    return [dict(r) for r in rows]


def week_range() -> tuple[str, str]:
    today = date.today()
    start = today - timedelta(days=today.weekday())
    return start.isoformat(), today.isoformat()


def weekly_totals(limit: int = 20) -> list[dict]:
    s, e = week_range()
    return top_apps_range(s, e, limit)


def daily_totals_range(start_day: str, end_day: str) -> list[dict]:
    """Total focused_ms per day (for calendar heatmap)."""
    rows = db.fetchall(
        "SELECT day, SUM(focused_ms) AS total_ms FROM daily_rollup "
        "WHERE day BETWEEN ? AND ? GROUP BY day ORDER BY day",
        (start_day, end_day),
    )
    return [dict(r) for r in rows]


def day_breakdown(day: str) -> list[dict]:
    rows = db.fetchall(
        "SELECT a.app_id, a.exe_name, a.display_name, a.icon_path, "
        "       r.focused_ms, r.opens_count, r.clicks_count "
        "FROM daily_rollup r JOIN apps a ON a.app_id = r.app_id "
        "WHERE r.day = ? ORDER BY r.focused_ms DESC",
        (day,),
    )
    return [dict(r) for r in rows]


def app_daily_history(app_id: int, days: int = 30) -> list[dict]:
    start = (date.today() - timedelta(days=days)).isoformat()
    rows = db.fetchall(
        "SELECT day, focused_ms, opens_count, clicks_count FROM daily_rollup "
        "WHERE app_id = ? AND day >= ? ORDER BY day",
        (app_id, start),
    )
    return [dict(r) for r in rows]


def most_used(days: int = 7, limit: int = 20) -> list[dict]:
    start = (date.today() - timedelta(days=days)).isoformat()
    return top_apps_range(start, today_str(), limit)


def least_used(days: int = 7, limit: int = 20) -> list[dict]:
    start = (date.today() - timedelta(days=days)).isoformat()
    rows = db.fetchall(
        "SELECT a.app_id, a.exe_name, a.display_name, a.icon_path, a.is_favorite, "
        "       SUM(r.focused_ms) AS focused_ms, SUM(r.opens_count) AS opens_count "
        "FROM daily_rollup r JOIN apps a ON a.app_id = r.app_id "
        "WHERE r.day BETWEEN ? AND ? GROUP BY a.app_id ORDER BY focused_ms ASC LIMIT ?",
        (start, today_str(), limit),
    )
    return [dict(r) for r in rows]


def most_opened(days: int = 7, limit: int = 20) -> list[dict]:
    start = (date.today() - timedelta(days=days)).isoformat()
    rows = db.fetchall(
        "SELECT a.app_id, a.exe_name, a.display_name, a.icon_path, a.is_favorite, "
        "       SUM(r.opens_count) AS opens_count, SUM(r.focused_ms) AS focused_ms "
        "FROM daily_rollup r JOIN apps a ON a.app_id = r.app_id "
        "WHERE r.day BETWEEN ? AND ? GROUP BY a.app_id ORDER BY opens_count DESC LIMIT ?",
        (start, today_str(), limit),
    )
    return [dict(r) for r in rows]


def most_clicked(days: int = 7, limit: int = 20) -> list[dict]:
    start = (date.today() - timedelta(days=days)).isoformat()
    rows = db.fetchall(
        "SELECT a.app_id, a.exe_name, a.display_name, a.icon_path, a.is_favorite, "
        "       SUM(r.clicks_count) AS clicks_count, SUM(r.focused_ms) AS focused_ms "
        "FROM daily_rollup r JOIN apps a ON a.app_id = r.app_id "
        "WHERE r.day BETWEEN ? AND ? AND r.clicks_count > 0 "
        "GROUP BY a.app_id ORDER BY clicks_count DESC LIMIT ?",
        (start, today_str(), limit),
    )
    return [dict(r) for r in rows]
