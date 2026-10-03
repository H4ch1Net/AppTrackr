"""SQLite access layer: per-thread connections, schema migrations and settings."""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable

from .. import paths

log = logging.getLogger(__name__)

_SCHEMA = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 1

_local = threading.local()
_generation = 0
_gen_lock = threading.Lock()
_path_override: Path | None = None


def configure(path: str | Path | None) -> None:
    """Point the data layer at a different database file.

    Every thread reconnects lazily on its next query.
    """
    global _path_override, _generation
    with _gen_lock:
        _path_override = Path(path) if path else None
        _generation += 1


def db_path() -> Path:
    return _path_override or paths.db_path()


def get_connection() -> sqlite3.Connection:
    """Return this thread's connection, reconnecting after configure()."""
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is not None and getattr(_local, "gen", -1) == _generation:
        return conn
    if conn is not None:
        conn.close()
    target = db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    _local.conn = conn
    _local.gen = _generation
    return conn


def close() -> None:
    """Close the calling thread's connection, if any."""
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def init_db() -> None:
    """Create the schema on first run and migrate older databases."""
    conn = get_connection()
    fresh = not _table_exists(conn, "apps")
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if fresh:
        version = SCHEMA_VERSION
    for target, migrate in _MIGRATIONS:
        if version < target:
            log.info("Migrating database to schema v%d", target)
            migrate(conn)
            version = target
    conn.execute(f"PRAGMA user_version = {int(version)}")
    conn.commit()


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


def _migrate_v1(conn: sqlite3.Connection) -> None:
    """v1.0 -> v1.1.

    Adds per-app exclusion and daily limits, and rebuilds focused time from the
    raw sessions. v1.0 dropped whole sessions that ended in idle and charged
    sessions that crossed midnight to the start day; the rebuild recovers both.
    """
    from .spans import split_by_day

    cols = _columns(conn, "apps")
    if "is_hidden" not in cols:
        conn.execute("ALTER TABLE apps ADD COLUMN is_hidden INTEGER NOT NULL DEFAULT 0")
    if "daily_limit_ms" not in cols:
        conn.execute("ALTER TABLE apps ADD COLUMN daily_limit_ms INTEGER")
    _merge_alias_apps(conn)

    row = conn.execute("SELECT value FROM settings WHERE key = 'idle_threshold_sec'").fetchone()
    idle_ms = int(row["value"]) * 1000 if row and str(row["value"]).isdigit() else 300_000

    totals: dict[tuple[str, int], int] = {}
    sessions = conn.execute(
        "SELECT app_id, start_ts, duration_ms, was_idle FROM usage_sessions "
        "WHERE end_ts IS NOT NULL AND duration_ms > 0"
    ).fetchall()
    for s in sessions:
        ms = s["duration_ms"] - (idle_ms if s["was_idle"] else 0)
        if ms <= 0:
            continue
        for day, part in split_by_day(s["start_ts"], s["start_ts"] + ms / 1000):
            key = (day, s["app_id"])
            totals[key] = totals.get(key, 0) + part

    conn.execute("UPDATE daily_rollup SET focused_ms = 0")
    conn.executemany(
        "INSERT INTO daily_rollup (day, app_id, focused_ms) VALUES (?, ?, ?) "
        "ON CONFLICT(day, app_id) DO UPDATE SET focused_ms = excluded.focused_ms",
        [(day, app_id, ms) for (day, app_id), ms in totals.items()],
    )
    conn.execute("DELETE FROM usage_sessions WHERE end_ts IS NULL")


def _merge_alias_apps(conn: sqlite3.Connection) -> None:
    """Fold rows for helper executables (e.g. steamwebhelper.exe) into their app."""
    from .catalog import EXE_ALIASES

    for alias, canonical in EXE_ALIASES.items():
        old = conn.execute("SELECT app_id FROM apps WHERE exe_name = ?", (alias,)).fetchone()
        if not old:
            continue
        new = conn.execute("SELECT app_id FROM apps WHERE exe_name = ?", (canonical,)).fetchone()
        if not new:
            conn.execute(
                "UPDATE apps SET exe_name = ?, display_name = NULL WHERE app_id = ?", (canonical, old["app_id"])
            )
            continue
        old_id, new_id = old["app_id"], new["app_id"]
        conn.execute(
            "INSERT INTO daily_rollup (day, app_id, focused_ms, opens_count, clicks_count) "
            "SELECT day, ?, focused_ms, opens_count, clicks_count FROM daily_rollup WHERE app_id = ? "
            "ON CONFLICT(day, app_id) DO UPDATE SET focused_ms = focused_ms + excluded.focused_ms, "
            "opens_count = opens_count + excluded.opens_count, clicks_count = clicks_count + excluded.clicks_count",
            (new_id, old_id),
        )
        conn.execute("DELETE FROM daily_rollup WHERE app_id = ?", (old_id,))
        if conn.execute("SELECT 1 FROM reward_rules WHERE app_id = ?", (new_id,)).fetchone():
            # Keep the alias's rules for its reward history, but don't pay out twice.
            conn.execute("UPDATE reward_rules SET enabled = 0 WHERE app_id = ?", (old_id,))
        for table in ("usage_sessions", "focus_events", "reward_rules", "reward_events"):
            if _table_exists(conn, table):
                conn.execute(f"UPDATE {table} SET app_id = ? WHERE app_id = ?", (new_id, old_id))
        conn.execute("DELETE FROM apps WHERE app_id = ?", (old_id,))


_MIGRATIONS: list[tuple[int, Callable[[sqlite3.Connection], None]]] = [
    (1, _migrate_v1),
]


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def execute(sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
    return get_connection().execute(sql, params)


def executemany(sql: str, seq: list[tuple[Any, ...]]) -> sqlite3.Cursor:
    return get_connection().executemany(sql, seq)


def commit() -> None:
    get_connection().commit()


def fetchone(sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    return execute(sql, params).fetchone()


def fetchall(sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    return execute(sql, params).fetchall()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def get_setting(key: str, default: str = "") -> str:
    row = fetchone("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def get_bool(key: str, default: bool = False) -> bool:
    return get_setting(key, "1" if default else "0") == "1"


def get_int(key: str, default: int = 0) -> int:
    try:
        return int(get_setting(key, str(default)))
    except ValueError:
        return default


def set_setting(key: str, value: str | int | bool) -> None:
    if isinstance(value, bool):
        value = "1" if value else "0"
    execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    commit()
