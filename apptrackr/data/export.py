"""Export, backup and restore."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from . import catalog, db

_EXPORT_SQL = (
    "SELECT r.day, a.exe_name, a.display_name, a.category, r.focused_ms, r.opens_count, r.clicks_count "
    "FROM daily_rollup r JOIN apps a ON a.app_id = r.app_id "
    "WHERE a.is_hidden = 0 ORDER BY r.day, r.focused_ms DESC"
)
_FIELDS = ["day", "exe_name", "app", "category", "focused_ms", "focused_minutes", "opens_count", "clicks_count"]


def _export_rows() -> list[dict]:
    rows = []
    for r in db.fetchall(_EXPORT_SQL):
        if not catalog.is_listable(r["exe_name"]):
            continue
        rows.append(
            {
                "day": r["day"],
                "exe_name": r["exe_name"],
                "app": catalog.display_name(dict(r)),
                "category": r["category"] or "",
                "focused_ms": r["focused_ms"],
                "focused_minutes": round(r["focused_ms"] / 60000, 1),
                "opens_count": r["opens_count"],
                "clicks_count": r["clicks_count"],
            }
        )
    return rows


def export_csv(filepath: str | Path) -> int:
    """Write per-day, per-app usage as CSV. Returns the number of rows."""
    rows = _export_rows()
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def export_json(filepath: str | Path) -> int:
    rows = _export_rows()
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    return len(rows)


def backup_db(dest: str | Path) -> None:
    """Write a consistent copy of the live database (WAL contents included)."""
    dest = Path(dest)
    if dest.exists():
        dest.unlink()
    target = sqlite3.connect(str(dest))
    try:
        db.get_connection().backup(target)
    finally:
        target.close()


class RestoreError(Exception):
    pass


def validate_backup(src: str | Path) -> None:
    """Raise RestoreError unless *src* looks like an AppTrackr database."""
    try:
        conn = sqlite3.connect(f"file:{Path(src).as_posix()}?mode=ro", uri=True)
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RestoreError("The backup file is damaged.")
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise RestoreError("The file is not a SQLite database.") from exc
    if not {"apps", "daily_rollup", "usage_sessions"} <= tables:
        raise RestoreError("The file is not an AppTrackr backup.")


def restore_db(src: str | Path) -> None:
    """Replace the live database with *src*, then migrate it to the current schema."""
    validate_backup(src)
    source = sqlite3.connect(str(src))
    try:
        source.backup(db.get_connection())
    finally:
        source.close()
    db.init_db()
