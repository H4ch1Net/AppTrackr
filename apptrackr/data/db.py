"""SQLite database manager for AppTrackr."""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

_SCHEMA = Path(__file__).with_name("schema.sql")

_local = threading.local()


def _default_data_dir() -> Path:
    """Resolve the data directory, honouring an optional override.

    ``APPTRACKR_DATA_DIR`` lets users relocate their data (portable installs,
    testing, multiple profiles) without touching the registry or APPDATA.
    """
    override = os.environ.get("APPTRACKR_DATA_DIR", "").strip()
    if override:
        return Path(override)
    return Path(os.environ.get("APPDATA", Path.home())) / "AppTrackr"


_data_dir = _default_data_dir()


def get_data_dir() -> Path:
    return _data_dir


def set_data_dir(path: str | Path) -> None:
    """Point the database at a different directory, closing any open handle.

    Mainly used by tests and for switching profiles at runtime.
    """
    global _data_dir
    close_connection()
    _data_dir = Path(path)


def _db_path() -> Path:
    return _data_dir / "data.sqlite"


def close_connection() -> None:
    """Close the calling thread's cached connection, if any."""
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        finally:
            _local.conn = None


def get_connection() -> sqlite3.Connection:
    """Return a thread-local SQLite connection (created once per thread)."""
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is None:
        _data_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
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
