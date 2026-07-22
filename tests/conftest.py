"""Shared pytest fixtures.

Every test runs against a throwaway SQLite database in a temp directory so the
real user data at ``%APPDATA%/AppTrackr`` is never touched.
"""

from __future__ import annotations

import pytest

from apptrackr.data import db


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Point the app at an isolated database for the duration of a test."""
    monkeypatch.setenv("APPTRACKR_DATA_DIR", str(tmp_path))
    db.set_data_dir(tmp_path)
    db.init_db()
    try:
        yield db
    finally:
        db.close_connection()
