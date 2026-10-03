"""Filesystem locations for AppTrackr data, logs and bundled assets."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_override: Path | None = None


def set_data_dir(path: str | os.PathLike[str] | None) -> None:
    """Override the data directory (used by --data-dir, --demo and tests)."""
    global _override
    _override = Path(path) if path else None


def data_dir() -> Path:
    """Directory holding the database, logs and other per-user state."""
    if _override is not None:
        return _override
    env = os.environ.get("APPTRACKR_DATA_DIR", "").strip()
    if env:
        return Path(env)
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA") or Path.home()) / "AppTrackr"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AppTrackr"
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else Path.home() / ".local" / "share") / "apptrackr"


def db_path() -> Path:
    return data_dir() / "data.sqlite"


def log_dir() -> Path:
    return data_dir() / "logs"


def assets_dir() -> Path:
    """Bundled assets, resolved for both source checkouts and PyInstaller builds."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "apptrackr" / "assets"
    return Path(__file__).with_name("assets")
