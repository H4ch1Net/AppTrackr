"""Export / import helpers for AppTrackr data."""

from __future__ import annotations

import csv
import io
import json
import shutil
from pathlib import Path

from . import db


def export_csv(filepath: str | Path) -> None:
    """Export daily_rollup joined with apps as CSV."""
    rows = db.fetchall(
        "SELECT r.day, a.exe_name, a.display_name, r.focused_ms, r.opens_count, r.clicks_count "
        "FROM daily_rollup r JOIN apps a ON a.app_id = r.app_id ORDER BY r.day, r.focused_ms DESC"
    )
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["day", "exe_name", "display_name", "focused_ms", "opens_count", "clicks_count"])
        for row in rows:
            writer.writerow([row["day"], row["exe_name"], row["display_name"],
                             row["focused_ms"], row["opens_count"], row["clicks_count"]])


def export_json(filepath: str | Path) -> None:
    """Export daily_rollup joined with apps as JSON."""
    rows = db.fetchall(
        "SELECT r.day, a.exe_name, a.display_name, r.focused_ms, r.opens_count, r.clicks_count "
        "FROM daily_rollup r JOIN apps a ON a.app_id = r.app_id ORDER BY r.day, r.focused_ms DESC"
    )
    data = [dict(r) for r in rows]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def backup_db(dest: str | Path) -> None:
    """Copy the entire SQLite file as a backup."""
    src = db._db_path()
    shutil.copy2(str(src), str(dest))


def restore_db(src: str | Path) -> None:
    """Replace the current database with a backup file. App must restart after."""
    dest = db._db_path()
    shutil.copy2(str(src), str(dest))
