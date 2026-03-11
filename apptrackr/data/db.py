"""SQLite database manager for AppTrackr."""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

_DB_DIR = Path(os.environ.get("APPDATA", Path.home())) / "AppTrackr"
_DB_PATH = _DB_DIR / "data.sqlite"
_SCHEMA = Path(__file__).with_name("schema.sql")

_local = threading.local()


def _db_path() -> Path:
    return _DB_PATH


def get_connection() -> sqlite3.Connection:
    """Return a thread-local SQLite connection (created once per thread)."""
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is None:
        _DB_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = get_connection()
    schema_sql = _SCHEMA.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()


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
# Settings helpers
# ---------------------------------------------------------------------------

def get_setting(key: str, default: str = "") -> str:
    row = fetchone("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    commit()
